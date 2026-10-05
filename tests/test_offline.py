"""Offline tests: fake Telegram, fake SOCKS5 proxy, throwaway DNSGuard DB.

Run on Linux (needs /proc):  python3 -m unittest discover -s tests -v
Touches nothing outside a temp folder and never restarts real services.
"""

import datetime as dt
import http.server
import json
import os
import socket
import sqlite3
import struct
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rsc import alerts, bot, config, system, tg  # noqa: E402
from rsc.dnsguard import DNSGuard  # noqa: E402

ADMIN = "111"


class FakeAPI:
    def __init__(self):
        self.sent, self.edited, self.calls = [], [], []

    def send(self, chat, text, **kw):
        self.sent.append((str(chat), text, kw))
        return {"message_id": len(self.sent)}

    def edit(self, chat, mid, text, **kw):
        self.edited.append((str(chat), mid, text, kw))

    def call(self, method, **kw):
        self.calls.append((method, kw))
        return True


def make_db(path):
    con = sqlite3.connect(path)
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    fmt = lambda d: d.strftime("%Y-%m-%d %H:%M:%S.%f")  # noqa: E731
    today = now.date().isoformat()
    con.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, telegram_id TEXT, email TEXT, username TEXT,
            tg_username TEXT, is_active BOOLEAN);
        CREATE TABLE tokens (id INTEGER PRIMARY KEY, user_id INT, token TEXT, label TEXT,
            is_active BOOLEAN, expires_at DATETIME);
        CREATE TABLE allowed_ips (id INTEGER PRIMARY KEY, token_id INT, ip TEXT, expires_at DATETIME);
        CREATE TABLE query_stats (id INTEGER PRIMARY KEY, token_id INT, day DATE, query_count INT, blocked_count INT);
        CREATE TABLE traffic_stats (id INTEGER PRIMARY KEY, token_id INT, day DATE, bytes_up INT, bytes_down INT, connections INT);
        CREATE TABLE domain_requests (id INTEGER PRIMARY KEY, user_id INT, domain TEXT, status TEXT);
    """)
    con.executemany("INSERT INTO users VALUES (?,?,?,?,?,?)", [
        (1, "500", None, "admin", "sadeq", 1), (2, "600", "b@x.ir", None, None, 1), (3, None, None, None, None, 0)])
    con.executemany("INSERT INTO tokens VALUES (?,?,?,?,?,?)", [
        (1, 1, "t1", "main", 1, fmt(now + dt.timedelta(days=30))),
        (2, 2, "t2", "phone", 1, fmt(now + dt.timedelta(days=1))),
        (3, 3, "t3", "old", 1, fmt(now - dt.timedelta(days=1)))])
    con.executemany("INSERT INTO allowed_ips VALUES (?,?,?,?)", [(1, 1, "1.2.3.4", None), (2, 2, "5.6.7.8", None)])
    con.executemany("INSERT INTO query_stats VALUES (?,?,?,?,?)", [
        (1, 1, today, 1000, 10), (2, 2, today, 500, 5), (3, 1, "2020-01-01", 9, 9)])
    con.executemany("INSERT INTO traffic_stats VALUES (?,?,?,?,?,?)", [
        (1, 1, today, 100, 5000, 1), (2, 2, today, 10, 20, 1)])
    con.execute("INSERT INTO domain_requests VALUES (1, 2, 'example.com', 'pending')")
    con.commit()
    con.close()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "dnsguard.db")
        make_db(self.db)
        cfg = config._merge(config.DEFAULTS, {
            "token": "1:x", "admin_ids": [ADMIN], "services": ["fake-a", "fake-b"],
            "timezone": "Asia/Tehran", "state": os.path.join(self.tmp, "state.json"),
            "dnsguard": {"db": self.db, "health_url": "", "metrics": os.path.join(self.tmp, "m.json"),
                         "nft_set": ""},
        })
        self.api = FakeAPI()
        self.bot = bot.Bot(cfg, api=self.api)

    def msg(self, text, uid=ADMIN, chat_type="private"):
        self.bot.handle({"update_id": 1, "message": {
            "message_id": 1, "from": {"id": int(uid)}, "chat": {"id": int(uid), "type": chat_type}, "text": text}})


class TextTests(unittest.TestCase):
    def test_split_keeps_lines(self):
        text = "\n".join(f"line {i} " + "x" * 50 for i in range(300))
        parts = tg.split_text(text)
        self.assertTrue(all(len(p) <= tg.MAX_TEXT for p in parts))
        self.assertEqual("\n".join(parts), text)
        self.assertEqual(tg.split_text("a" * 9000), ["a" * 4096, "a" * 4096, "a" * 808])

    def test_valid_target(self):
        for ok in ("1.1.1.1", "2001:4860::8888", "google.com", "a-b.example.ir", "localhost"):
            self.assertTrue(system.valid_target(ok), ok)
        for bad in ("; rm -rf /", "-c 1000", "a b", "$(id)", "x..y", "", "-flood"):
            self.assertFalse(system.valid_target(bad), bad)

    def test_formats(self):
        self.assertEqual(system.human(512), "512 B")
        self.assertEqual(system.human(1536), "1.5 KB")
        self.assertEqual(system.human(5 * 1024 ** 3), "5.0 GB")
        self.assertEqual(system.rate(125000), "1.0 Mbit/s")
        self.assertEqual(system.duration(90061), "1d 1h")
        self.assertEqual(system.bar(50), "█████░░░░░")
        self.assertEqual(system.short(696254464), "664M")
        self.assertEqual(system.short(19.6e9), "18.3G")

    def test_parse_ping(self):
        p = system.parse_ping("4 packets transmitted, 3 received, 25% packet loss, time 3011ms\n"
                              "rtt min/avg/max/mdev = 80.367/83.290/84.303/1.687 ms")
        self.assertEqual((p["sent"], p["received"], p["loss"], p["avg"]), (4, 3, 25.0, 83.29))
        self.assertIsNone(system.parse_ping("ping: nohost: Name or service not known")["sent"])

    def test_port_table(self):
        rows = system.port_table([("tcp", 22, "*", "sshd"), ("tcp", 22, "*", "sshd"),
                                  ("tcp", 53, "1.1.1.1", "dns"), ("udp", 53, "2.2.2.2", "dns"),
                                  ("tcp", 2222, "127.0.0.1", "sshd"), ("tcp", 2222, "::1", "sshd")])
        self.assertEqual(rows, [("tcp", 22, "sshd", ""), ("tcp/udp", 53, "dns", "2 IPs"),
                                ("tcp", 2222, "sshd", "local")])

    def test_config_merge(self):
        path = os.path.join(tempfile.mkdtemp(), "c.json")
        with open(path, "w") as fh:
            json.dump({"token": "1:x", "admin_ids": [12345678], "alerts": {"ram_pct": 80}}, fh)
        cfg = config.load(path)
        self.assertEqual(cfg["admin_ids"], ["12345678"])
        self.assertEqual(cfg["alerts"]["ram_pct"], 80)
        self.assertEqual(cfg["alerts"]["disk_pct"], 90)


class SystemTests(unittest.TestCase):
    def test_proc_readers(self):
        m = system.memory()
        self.assertGreater(m["total"], 0)
        s = system.sample(0.2)
        self.assertTrue(0 <= s["cpu"] <= 100)
        self.assertGreater(system.uptime(), 0)
        self.assertTrue(system.boot_id())

    def test_services_parsing(self):
        out = ("Id=a.service\nActiveState=active\nSubState=running\nActiveEnterTimestampMonotonic=1000000\n"
               "MemoryCurrent=1048576\nNRestarts=2\n\nId=b.service\nActiveState=failed\nSubState=failed\n"
               "ActiveEnterTimestampMonotonic=0\nMemoryCurrent=[not set]\nNRestarts=0\n")
        with mock.patch.object(system, "run", return_value=out):
            a, b = system.services(["a", "b"])
        self.assertEqual((a["state"], a["memory"], a["restarts"]), ("active", 1048576, "2"))
        self.assertIsNotNone(a["since"])
        self.assertEqual((b["state"], b["memory"], b["since"]), ("failed", None, None))

    def test_ports_parsing(self):
        out = ('tcp LISTEN 0 4096 127.0.0.1:8000 0.0.0.0:* users:(("uvicorn",pid=723,fd=27))\n'
               'udp UNCONN 0 0 [::]:443 [::]:* users:(("hysteria",pid=9,fd=3))\n'
               'tcp LISTEN 0 4096 [::]:443 [::]:* users:(("caddy",pid=8,fd=3))\n')
        with mock.patch.object(system, "run", return_value=out):
            rows = system.listening_ports()
        self.assertEqual(rows[0], ("tcp", 443, "*", "caddy"))
        self.assertIn(("tcp", 8000, "127.0.0.1", "uvicorn"), rows)


class SocksTests(unittest.TestCase):
    def test_request_through_socks5_with_auth(self):
        class H(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                out = b'{"ok":true,"result":' + body + b"}"
                self.send_response(200)
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def log_message(self, *a):
                pass

        web = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=web.serve_forever, daemon=True).start()
        seen = {}
        proxy = socket.socket()
        proxy.bind(("127.0.0.1", 0))
        proxy.listen(1)

        def serve():
            c, _ = proxy.accept()
            seen["greeting"] = c.recv(4)
            c.sendall(b"\x05\x02")
            ver, ulen = c.recv(2)
            user = c.recv(ulen)
            plen = c.recv(1)[0]
            seen["auth"] = (user, c.recv(plen))
            c.sendall(b"\x01\x00")
            head = c.recv(5)
            seen["host"] = c.recv(head[4])
            port = struct.unpack(">H", c.recv(2))[0]
            c.sendall(b"\x05\x00\x00\x01" + b"\x00" * 6)
            up = socket.create_connection(("127.0.0.1", port))
            for a, b in ((c, up), (up, c)):
                threading.Thread(target=lambda a=a, b=b: [b.sendall(d) for d in iter(lambda: a.recv(65536), b"")],
                                 daemon=True).start()

        threading.Thread(target=serve, daemon=True).start()
        status, body = tg.request(f"http://localhost:{web.server_port}/x", data=b'{"a":1}',
                                  proxy=f"socks5://us%40r:p%3Ass@127.0.0.1:{proxy.getsockname()[1]}", timeout=5)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["result"], {"a": 1})
        self.assertEqual(seen["auth"], (b"us@r", b"p:ss"))
        self.assertEqual(seen["greeting"], b"\x05\x02\x00\x02")
        self.assertEqual(seen["host"], b"localhost")


class DNSGuardTests(Base):
    def test_summary(self):
        s = self.bot.dg.summary()
        self.assertEqual(s["users"], (3, 2))
        self.assertEqual(s["tokens"], 2)
        self.assertEqual(s["ips"], 2)
        self.assertEqual(s["queries"], (1500, 15))
        self.assertEqual(s["traffic_today"], (5020, 110))
        self.assertEqual(s["top"], [("@sadeq", 5100), ("b@x.ir", 30)])
        self.assertEqual([e[0] for e in s["expiring"]], ["b@x.ir"])
        self.assertEqual(s["pending"], 1)

    def test_read_only(self):
        con = self.bot.dg._db()
        with self.assertRaises(sqlite3.OperationalError):
            con.execute("DELETE FROM users")
        con.close()

    def test_missing_table_is_na(self):
        con = sqlite3.connect(self.db)
        con.execute("DROP TABLE traffic_stats")
        con.commit()
        con.close()
        s = self.bot.dg.summary()
        self.assertIsNone(s["traffic_today"])
        self.assertIsNone(s["top"])
        self.assertEqual(s["users"], (3, 2))
        self.assertIn("Users", self.bot.dnsguard_text())

    def test_metrics(self):
        now = int(time.time() // 60)
        with open(self.bot.dg.metrics_path, "w") as fh:
            json.dump([[now - 2000, 9, 9], [now - 100, 5, 50], [now - 1, 3, 30]], fh)
        m = self.bot.dg.metrics()
        self.assertEqual((m["q_1h"], m["q_24h"], m["b_24h"]), (3, 8, 80))

    def test_not_installed(self):
        dg = DNSGuard({"db": "/nonexistent/x.db"})
        self.assertFalse(dg.installed())
        self.assertIsNone(dg.summary()["users"])


class BotTests(Base):
    def test_ignores_strangers_and_groups(self):
        self.msg("/start", uid="999")
        self.msg("/start", chat_type="group")
        self.assertEqual(self.api.sent, [])

    def test_start_menu(self):
        self.msg("/start")
        kb = self.api.sent[0][2]["reply_markup"]["keyboard"]
        labels = [b["text"] for row in kb for b in row]
        self.assertIn(bot.B_DNSG, labels)
        self.assertEqual(len(labels), 8)

    def test_ping_rejects_injection(self):
        self.msg(bot.B_PING)
        with mock.patch.object(system, "ping") as p:
            self.msg("8.8.8.8; reboot")
            p.assert_not_called()
        self.assertIn("Not a valid", self.api.sent[-1][1])

    def test_ping_ok(self):
        self.msg(bot.B_PING)
        out = "4 packets transmitted, 4 received, 0% packet loss\nrtt min/avg/max/mdev = 1/2/3/0 ms"
        with mock.patch.object(system, "ping", return_value=out) as p:
            self.msg("1.1.1.1")
            p.assert_called_once_with("1.1.1.1")
        self.assertIn("✅", self.api.sent[-1][1])
        self.assertIn("Avg      2.0 ms", self.api.sent[-1][1])
        self.msg(bot.B_PING)
        with mock.patch.object(system, "ping", return_value="ping: x.invalid: Name or service not known"):
            self.msg("x.invalid")
        self.assertIn("❌", self.api.sent[-1][1])
        self.msg("1.1.1.1")  # waiting state is cleared after one use
        self.assertIn("menu buttons", self.api.sent[-1][1])

    def test_views_render(self):
        svc = [{"name": "fake-a", "state": "active", "sub": "running", "since": 100, "memory": 1 << 20,
                "restarts": "0"},
               {"name": "fake-b", "state": "failed", "sub": "failed", "since": None, "memory": None,
                "restarts": "3"}]
        with mock.patch.object(system, "services", return_value=svc):
            for b in (bot.B_STATUS, bot.B_SERVICES, bot.B_DNSG, bot.B_NET, bot.B_ALERTS):
                self.msg(b)
            report = self.bot.daily_report()
        texts = [t for _, t, _ in self.api.sent]
        self.assertIn("RAM", texts[0])
        self.assertIn("🔴 fake-b", texts[1])
        self.assertIn("🔴 1 down", texts[1])
        self.assertIn("@sadeq", texts[2])
        self.assertRegex(texts[2], r"Requests +1  pending")
        self.assertIn("Down: fake-b", report)
        for t in texts + [report]:  # every <pre> is closed, no tags inside it
            self.assertEqual(t.count("<pre>"), t.count("</pre>"))

    def test_restart_needs_confirm(self):
        with mock.patch.object(system, "restart_service", return_value="active") as r, \
                mock.patch.object(system, "services", return_value=[]):
            cb = lambda data, uid=ADMIN: self.bot.handle({"update_id": 2, "callback_query": {  # noqa: E731
                "id": "q", "from": {"id": int(uid)}, "data": data,
                "message": {"message_id": 5, "chat": {"id": int(uid)}}}})
            cb("sv:r:1")
            r.assert_not_called()
            self.assertIn("Restart <code>fake-b</code>?", self.api.edited[-1][2])
            cb("sv:R:1", uid="999")
            r.assert_not_called()
            cb("sv:R:9")
            r.assert_not_called()
            cb("sv:R:1")
            r.assert_called_once_with("fake-b")
        self.assertEqual(self.api.calls[-1], ("answerCallbackQuery", {"callback_query_id": "q",
                                                                      "text": "fake-b: active"}))

    def test_mute(self):
        self.bot.route("al:m:60", 111, 5)
        self.assertTrue(self.bot.monitor.muted_until())
        self.bot.monitor.notify("x")
        self.assertEqual(self.api.sent, [])
        self.bot.route("al:m:0", 111, 5)
        self.assertFalse(self.bot.monitor.muted_until())


class MonitorTests(Base):
    def test_condition_streak_repeat_recover(self):
        m = self.bot.monitor
        m.condition("k", True, 3, "bad", "good")
        m.condition("k", True, 3, "bad", "good")
        self.assertEqual(self.api.sent, [])
        m.condition("k", True, 3, "bad", "good")
        self.assertIn("🚨 bad", self.api.sent[-1][1])
        m.condition("k", True, 3, "bad", "good")
        self.assertEqual(len(self.api.sent), 1)  # no repeat before repeat_after_min
        m.active["k"]["last"] -= 3601
        m.condition("k", True, 3, "bad", "good")
        self.assertIn("Still", self.api.sent[-1][1])
        m.condition("k", False, 3, "bad", "good")
        self.assertIn("✅ good", self.api.sent[-1][1])

    def test_startup_and_news(self):
        m = self.bot.monitor
        m.startup()
        self.assertIn("Monitor started", self.api.sent[-1][1])
        self.assertEqual(m.state["dg_last"], {"user": 3, "request": 1})
        con = sqlite3.connect(self.db)
        con.execute("INSERT INTO users (id, tg_username, is_active) VALUES (4, 'newbie', 1)")
        con.execute("INSERT INTO domain_requests VALUES (2, 4, 'game.example', 'pending')")
        con.commit()
        con.close()
        m.check_dnsguard()
        texts = [t for _, t, _ in self.api.sent]
        self.assertTrue(any("@newbie" in t and "New DNSGuard user" in t for t in texts))
        self.assertTrue(any("game.example" in t for t in texts))
        m.check_dnsguard()
        self.assertEqual(len(self.api.sent), len(texts))  # each news item only once

        m2 = alerts.Monitor(self.bot.cfg, self.api, self.bot.dg)
        m2.state["boot_id"] = "different"
        m2.startup()
        self.assertIn("rebooted", self.api.sent[-1][1])

    def test_daily_once(self):
        m = self.bot.monitor
        m.state["last_report"] = "2000-01-01"
        m.cfg["daily_report"] = "00:00"
        m.daily()
        m.daily()
        self.assertEqual(sum("Daily report" in t for _, t, _ in self.api.sent), 1)

    def test_full_check_runs(self):
        with mock.patch.object(system, "services", return_value=[]):
            self.bot.monitor.check()
        self.assertTrue(os.path.exists(self.bot.cfg["state"]))


if __name__ == "__main__":
    unittest.main()
