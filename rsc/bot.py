"""Telegram front end: menu, views and button callbacks.

Only user ids listed in admin_ids get an answer, and only in a private
chat. Everybody else is ignored without a reply.
"""

from __future__ import annotations

import datetime as dt
import html
import logging
import os
import re
import sys
import time

from . import __version__, config, system, tg
from .alerts import Monitor
from .dnsguard import DNSGuard

log = logging.getLogger("rsc")
E = lambda s: html.escape(str(s), quote=False)  # noqa: E731

B_STATUS, B_SERVICES = "📊 Status", "⚙️ Services"
B_DNSG, B_NET = "🛡 DNSGuard", "🌐 Network"
B_PING, B_GEO = "🏓 Ping", "🌍 Geo IP"
B_ALERTS, B_CLEAN = "🔔 Alerts", "🧹 Clean up"


def ikb(*rows) -> dict:
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in rows]}


def num(n) -> str:
    return "n/a" if n is None else f"{n:,}"


def pre(rows: list[str]) -> str:
    return "<pre>" + E("\n".join(rows)) + "</pre>"


class Bot:
    def __init__(self, cfg: dict, api=None):
        self.cfg = cfg
        self.api = api or tg.Telegram(cfg["token"], cfg.get("proxy", ""))
        self.admins = set(cfg["admin_ids"])
        self.dg = DNSGuard(cfg["dnsguard"])
        self.monitor = Monitor(cfg, self.api, self.dg, report=self.daily_report)
        self.waiting: dict = {}  # chat id -> "ping" | "geo"

    # ---- helpers ------------------------------------------------------------

    def clock(self) -> str:
        return dt.datetime.now(self.monitor.tz).strftime("%H:%M")

    def keyboard(self) -> dict:
        if self.dg.installed():
            rows = [[B_STATUS, B_SERVICES], [B_DNSG, B_NET], [B_PING, B_GEO], [B_ALERTS, B_CLEAN]]
        else:
            rows = [[B_STATUS, B_SERVICES], [B_NET, B_PING], [B_GEO, B_ALERTS], [B_CLEAN]]
        return {"keyboard": [[{"text": t} for t in row] for row in rows],
                "resize_keyboard": True, "is_persistent": True}

    def show(self, chat, mid, text: str, markup: dict | None = None) -> None:
        """Edit the message when called from a button, else send a new one."""
        kw = {"reply_markup": markup} if markup else {}
        if mid:
            try:
                self.api.edit(chat, mid, text, **kw)
                return
            except tg.TelegramError as exc:
                log.info("edit failed, sending instead: %s", exc)
        self.api.send(chat, text, **kw)

    # ---- views --------------------------------------------------------------
    # Figures go in <pre> blocks: Telegram shows them in a monospace font, so
    # columns and the █░ bars line up. Plain text is proportional and doesn't.

    def footer(self) -> str:
        return f"<i>Updated {self.clock()}</i>"

    def status_text(self) -> str:
        s = system.sample(1.0)
        mem, d = system.memory(), system.disk()
        l1 = os.getloadavg()[0]
        sh = system.short
        rows = [f"CPU  {system.bar(s['cpu'])} {s['cpu']:>3.0f}%  load {l1:.2f}",
                f"RAM  {system.bar(mem['pct'])} {mem['pct']:>3.0f}%  {sh(mem['used'])}/{sh(mem['total'])}"]
        if mem["swap_total"]:
            swap_pct = 100 * mem["swap_used"] / mem["swap_total"]
            rows.append(f"Swap {system.bar(swap_pct)} {swap_pct:>3.0f}%  {sh(mem['swap_used'])}/{sh(mem['swap_total'])}")
        rows += [f"Disk {system.bar(d['pct'])} {d['pct']:>3.0f}%  {sh(d['used'])}/{sh(d['total'])}",
                 "",
                 f"Net  ↓ {system.rate(s['rx_rate']):<12} ↑ {system.rate(s['tx_rate'])}",
                 f"     ↓ {sh(s['rx_total']) + ' total':<12} ↑ {sh(s['tx_total'])} total"]
        parts = [f"🖥 <b>{E(system.hostname())}</b> · up {system.duration(system.uptime())}"
                 f" · {E(s['iface'])}", pre(rows)]
        top = system.top_processes(5)
        if top:
            parts += ["<b>Top memory</b>",
                      pre([f"{n[:16]:<16} {sh(rss):>6} {cpu:>4.0f}%" for n, cpu, rss in top])]
        problems = self.monitor.problems()
        if problems:
            parts.append("🚨 <b>Open alerts</b>\n" + "\n".join(f"• {p}" for p in problems))
        parts.append(self.footer())
        return "\n".join(parts)

    def services_view(self) -> tuple[str, dict]:
        svcs = system.services(self.cfg["services"])
        rows, buttons = [], []
        for i, svc in enumerate(svcs):
            ok = svc["state"] == "active"
            icon = "🟢" if ok else "🟡" if svc["state"] in system.OK_STATES else "🔴"
            if ok:
                up = system.duration(svc["since"]) if svc["since"] is not None else ""
                mem = system.short(svc["memory"]) if svc["memory"] else ""
                detail = f"{up:>7} {mem:>5}"
            else:
                detail = f"{svc['state'][:13]:>13}"
            restarts = f" ↻{svc['restarts']}" if svc["restarts"] not in ("", "0") else ""
            rows.append(f"{icon} {svc['name'][:15]:<15} {detail}{restarts}")
            buttons.append([(f"📜 {svc['name'][:20]}", f"sv:l:{i}"), ("🔄 Restart", f"sv:r:{i}")])
        down = sum(s["state"] not in system.OK_STATES for s in svcs)
        summary = f"{len(svcs)} watched · " + ("all running" if not down else f"🔴 {down} down")
        parts = [f"⚙️ <b>Services</b> · {summary}"]
        parts.append(pre(rows) if rows else "<i>No services configured (\"services\" in config.json).</i>")
        parts.append(self.footer())
        buttons.append([("↻ Refresh", "sv")])
        return "\n".join(parts), ikb(*buttons)

    def dnsguard_text(self) -> str:
        if not self.dg.installed():
            return "🛡 DNSGuard is not installed on this server."
        ok, info = self.dg.health()
        s = self.dg.summary()
        fw = self.dg.firewall_ips()
        m = self.dg.metrics()
        sh = system.short
        health = "🟢 healthy" if ok else f"🔴 {E(info)}"
        users, q = s.get("users"), s.get("queries")
        exp = s.get("expiring")
        rows = [
            f"Users     {num(users[0]) if users else 'n/a':>6}  {num(users[1]) if users else '?'} active",
            f"Tokens    {num(s.get('tokens')):>6}  live",
            f"IPs       {num(s.get('ips')):>6}" + (f"  firewall {num(fw)}" if fw is not None else ""),
            f"Requests  {num(s.get('pending')):>6}  pending",
            f"Expiring  {num(len(exp)) if exp is not None else 'n/a':>6}  within {self.dg.expiry_days}d",
        ]
        parts = [f"🛡 <b>DNSGuard</b> · {health}", pre(rows), "<b>Traffic</b> · today, UTC"]
        rows = [f"Queries   {num(q[0]) if q else 'n/a':>7}  blocked {num(q[1]) if q else '?'}"]
        if m:
            stale = "  (stale)" if (m["age_min"] or 0) > 30 else ""
            rows.append(f"Last 1h   {num(m['q_1h']):>7}  24h {num(m['q_24h'])}{stale}")
        for key, label in (("traffic_today", "Relay"), ("traffic_month", "Month")):
            t = s.get(key)
            if t:
                rows.append(f"{label:<9} ↓ {sh(t[0]):>6}  ↑ {sh(t[1])}")
        parts.append(pre(rows))
        top = s.get("top")
        if top:
            parts += ["<b>Top users today</b>", pre([f"{n[:20]:<20} {sh(b):>6}" for n, b in top])]
        if exp:
            parts += ["<b>Expiring soon</b> · UTC",
                      pre([f"{n[:16]:<16} {w[5:16]}" for n, _, w in exp[:10]])]
        parts.append(f"{self.footer()} · <i>read-only</i>")
        return "\n".join(parts)

    def network_text(self) -> str:
        raw = system.listening_ports()
        # High UDP ports on all addresses are outgoing sockets (xray, DNS clients), not services.
        listen = [r for r in raw if not (r[0] == "udp" and r[1] >= 32768 and r[2] == "*")]
        hidden = len(system.port_table(raw)) - len(system.port_table(listen))
        ports = [(proto, port, re.sub(r"-linux-.*$", "", proc), where)
                 for proto, port, proc, where in system.port_table(listen)]
        short_proto = {"tcp": "tcp", "udp": "udp", "tcp/udp": "t+u"}
        rows = [f"{'PORT':>5} {'':3} {'PROCESS':<14} BIND"]
        rows += [f"{port:>5} {short_proto.get(proto, proto[:3]):<3} {proc[:14]:<14} {where}".rstrip()
                 for proto, port, proc, where in ports[:45]]
        if len(ports) > 45:
            rows.append(f"… {len(ports) - 45} more")
        if hidden:
            rows.append(f"(+{hidden} outgoing UDP sockets hidden)")
        return "\n".join([
            f"🌐 <b>Network</b> · {system.connection_count()} TCP connections",
            f"<b>Listening ports</b> · {len(ports)}", pre(rows), self.footer()])

    def alerts_view(self) -> tuple[str, dict]:
        a = self.cfg["alerts"]
        until = self.monitor.muted_until()
        state = (f"🔇 muted until {dt.datetime.fromtimestamp(until, self.monitor.tz):%H:%M}"
                 if until else "🔊 on")
        report = self.cfg.get("daily_report") or "off"
        rows = [
            f"RAM      ≥ {a['ram_pct']}%",
            f"Disk     ≥ {a['disk_pct']}%",
            f"Load     > {a['load_per_cpu']} × cores",
            f"Check    every {self.cfg['check_every']}s",
            f"Remind   every {a['repeat_after_min']} min",
            f"Report   {report} {self.cfg['timezone']}",
        ]
        extra = "reboots" + (", DNSGuard health, new users, domain requests" if self.dg.installed() else "")
        parts = [f"🔔 <b>Alerts</b> · {state}", pre(rows),
                 f"<b>Services</b>: {E(', '.join(self.cfg['services']) or 'none')}",
                 f"<b>Also</b>: {extra}", ""]
        problems = self.monitor.problems()
        parts += ["🚨 <b>Open now</b>"] + [f"• {p}" for p in problems] if problems else ["✅ No open problems."]
        markup = ikb([("🔇 1 hour", "al:m:60"), ("🔇 8 hours", "al:m:480")],
                     [("🔊 Unmute", "al:m:0"), ("📅 Report now", "al:r")])
        return "\n".join(parts), markup

    def daily_report(self) -> str:
        mem, d = system.memory(), system.disk()
        svcs = system.services(self.cfg["services"])
        down = [s["name"] for s in svcs if s["state"] not in system.OK_STATES]
        rows = [f"Uptime    {system.duration(system.uptime())}",
                f"Load      {os.getloadavg()[0]:.2f}",
                f"RAM       {mem['pct']:.0f}%  {system.short(mem['available'])} free",
                f"Disk      {d['pct']:.0f}%  {system.short(d['free'])} free",
                f"Services  {'all ' + str(len(svcs)) + ' running' if not down else str(len(down)) + ' down'}"]
        parts = [f"📅 <b>Daily report</b> · {E(system.hostname())}", pre(rows)]
        if down:
            parts.append(f"🔴 Down: {E(', '.join(down))}")
        if self.dg.installed():
            ok, _ = self.dg.health()
            s = self.dg.summary()
            q, users, t = s.get("queries"), s.get("users"), s.get("traffic_month")
            rows = [f"Users     {num(users[0]) if users else 'n/a'}",
                    f"Queries   {num(q[0]) if q else 'n/a'} today"]
            if t:
                rows.append(f"Month     ↓ {system.short(t[0])}  ↑ {system.short(t[1])}")
            if s.get("pending"):
                rows.append(f"Requests  {s['pending']} pending")
            parts += [f"🛡 <b>DNSGuard</b> · {'🟢 healthy' if ok else '🔴 not healthy'}", pre(rows)]
            exp = s.get("expiring") or []
            if exp:
                parts.append(f"⏳ Expiring soon: {E(', '.join(n for n, _, _ in exp[:8]))}")
        return "\n".join(parts)

    # ---- actions --------------------------------------------------------------

    def do_ping(self, chat, target: str) -> None:
        if not system.valid_target(target):
            self.api.send(chat, "❌ Not a valid IP or host name.")
            return
        out = system.ping(target)
        p = system.parse_ping(out)
        if p["sent"] is None:  # unknown host, no network, ...
            self.api.send(chat, f"🏓 <b>Ping</b> · <code>{E(target)}</code> ❌\n{pre(out.splitlines()[-4:])}")
            return
        loss = p["loss"] if p["loss"] is not None else 100.0
        icon = "✅" if loss == 0 else "❌ no reply" if p["received"] == 0 else "⚠️ packet loss"
        rows = [f"Packets  {p['received']}/{p['sent']} received", f"Loss     {loss:g}%"]
        if p["avg"] is not None:
            rows += [f"Avg      {p['avg']:.1f} ms",
                     f"Min/Max  {p['min']:.1f} / {p['max']:.1f} ms",
                     f"Jitter   {p['mdev']:.1f} ms"]
        self.api.send(chat, f"🏓 <b>Ping</b> · <code>{E(target)}</code>  {icon}\n{pre(rows)}")

    def do_geo(self, chat, target: str) -> None:
        if not system.valid_target(target):
            self.api.send(chat, "❌ Not a valid IP or host name.")
            return
        try:
            g = system.geoip(target, self.cfg.get("proxy", ""))
        except Exception as exc:
            self.api.send(chat, f"❌ Lookup failed: {E(exc)}")
            return
        if g.get("status") != "success":
            self.api.send(chat, f"❌ {E(g.get('message', 'lookup failed'))}")
            return
        cc = str(g.get("countryCode") or "")
        flag = "".join(chr(0x1F1E6 + ord(c) - 65) for c in cc.upper()) if len(cc) == 2 and cc.isalpha() else "🌍"
        rows = [f"Region  {g.get('regionName') or '-'}", f"City    {g.get('city') or '-'}",
                f"ISP     {g.get('isp') or '-'}", f"Org     {g.get('org') or '-'}",
                f"AS      {g.get('as') or '-'}"]
        self.api.send(chat, f"{flag} <b>{E(g.get('query', target))}</b> · {E(g.get('country'))}\n{pre(rows)}")

    # ---- update routing ---------------------------------------------------------

    def handle(self, update: dict) -> None:
        if "callback_query" in update:
            self.on_callback(update["callback_query"])
            return
        msg = update.get("message")
        if not msg or msg.get("chat", {}).get("type") != "private":
            return
        if str(msg.get("from", {}).get("id")) not in self.admins:
            log.info("ignored message from %s", msg.get("from", {}).get("id"))
            return
        chat, text = msg["chat"]["id"], (msg.get("text") or "").strip()
        cmd = text.split("@")[0].lower()
        mode = self.waiting.pop(chat, None)

        if cmd in ("/start", "/help", "/menu"):
            self.api.send(chat, f"🎛 <b>Remote Server Control</b> · <code>{E(system.hostname())}</code>\n"
                                "Choose an option below.", reply_markup=self.keyboard())
        elif text == B_STATUS or cmd == "/status":
            self.api.send(chat, self.status_text(), reply_markup=ikb([("↻ Refresh", "st")]))
        elif text == B_SERVICES or cmd == "/services":
            body, markup = self.services_view()
            self.api.send(chat, body, reply_markup=markup)
        elif text == B_DNSG or cmd == "/dnsguard":
            self.api.send(chat, self.dnsguard_text(), reply_markup=ikb([("↻ Refresh", "dg")]))
        elif text == B_NET or cmd == "/network":
            self.api.send(chat, self.network_text(), reply_markup=ikb([("↻ Refresh", "net")]))
        elif text == B_PING:
            self.waiting[chat] = "ping"
            self.api.send(chat, "🏓 Send an IP or host name to ping:")
        elif text == B_GEO:
            self.waiting[chat] = "geo"
            self.api.send(chat, "🌍 Send an IP or host name to look up:")
        elif text == B_ALERTS or cmd == "/alerts":
            body, markup = self.alerts_view()
            self.api.send(chat, body, reply_markup=markup)
        elif text == B_CLEAN:
            self.api.send(chat, "🧹 Clean APT cache, journal logs older than 3 days and the RAM page cache?",
                          reply_markup=ikb([("✅ Yes, clean", "cl:ok"), ("✖️ Cancel", "cl:no")]))
        elif mode == "ping":
            self.do_ping(chat, text)
        elif mode == "geo":
            self.do_geo(chat, text)
        else:
            self.api.send(chat, "Use the menu buttons below.", reply_markup=self.keyboard())

    def on_callback(self, cq: dict) -> None:
        note = ""
        try:
            if str(cq.get("from", {}).get("id")) in self.admins:
                msg = cq.get("message") or {}
                note = self.route(cq.get("data", ""), msg.get("chat", {}).get("id"), msg.get("message_id"))
        finally:
            try:
                self.api.call("answerCallbackQuery", callback_query_id=cq["id"], text=note or "")
            except Exception as exc:
                log.info("answerCallbackQuery failed: %s", exc)

    def route(self, data: str, chat, mid) -> str:
        parts = data.split(":")
        if data == "st":
            self.show(chat, mid, self.status_text(), ikb([("↻ Refresh", "st")]))
        elif data == "dg":
            self.show(chat, mid, self.dnsguard_text(), ikb([("↻ Refresh", "dg")]))
        elif data == "net":
            self.show(chat, mid, self.network_text(), ikb([("↻ Refresh", "net")]))
        elif data == "sv":
            self.show(chat, mid, *self.services_view())
        elif parts[0] == "sv" and len(parts) == 3:
            try:
                name = self.cfg["services"][int(parts[2])]
            except (ValueError, IndexError):
                return "Unknown service"
            if parts[1] == "l":
                logs = system.service_logs(name)[-3500:]
                self.api.send(chat, f"📜 <b>{E(name)}</b>\n<pre>{E(logs or 'no log lines')}</pre>")
            elif parts[1] == "r":
                self.show(chat, mid, f"🔄 Restart <code>{E(name)}</code>?",
                          ikb([("✅ Yes, restart", f"sv:R:{parts[2]}"), ("✖️ Cancel", "sv")]))
            elif parts[1] == "R":
                log.info("restart %s requested", name)
                result = system.restart_service(name)
                self.show(chat, mid, *self.services_view())
                return f"{name}: {result}"[:190]
        elif data == "cl:ok":
            self.show(chat, mid, "🧹 Cleaning… ⏳")
            r = system.clean_up()
            self.show(chat, mid, "🧹 <b>Clean-up done</b>\n" + pre(
                [f"✓ {step}" for step in r["steps"]] + [
                    "", f"Disk freed  {system.human(max(r['disk_freed'], 0))}",
                    f"RAM freed   {system.human(max(r['ram_freed'], 0))}"]))
        elif data == "cl:no":
            self.show(chat, mid, "✖️ Cancelled.")
        elif parts[0] == "al" and len(parts) == 3 and parts[1] == "m":
            self.monitor.mute(int(parts[2]))
            self.show(chat, mid, *self.alerts_view())
            return "Muted" if int(parts[2]) else "Alerts on"
        elif data == "al:r":
            self.api.send(chat, self.daily_report())
        return ""

    # ---- main loop --------------------------------------------------------------

    def poll(self) -> None:
        offset, backoff = None, 5
        while True:
            try:
                params = {"offset": offset} if offset else {}
                updates = self.api.call("getUpdates", http_timeout=65, timeout=50,
                                        allowed_updates=["message", "callback_query"], **params)
                backoff = 5
            except Exception as exc:
                log.warning("getUpdates failed: %s (retry in %ss)", exc, backoff)
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue
            for update in updates:
                offset = update["update_id"] + 1
                try:
                    self.handle(update)
                except Exception:
                    log.exception("update %s failed", update.get("update_id"))


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(levelname)s %(name)s: %(message)s")
    cfg = config.load()
    bot = Bot(cfg)
    if "--check" in argv:
        me = bot.api.call("getMe")
        print(f"OK: v{__version__} connected to Telegram as @{me.get('username')}")
        return 0
    try:
        bot.api.call("setMyCommands", commands=[
            {"command": "start", "description": "Menu"},
            {"command": "status", "description": "Server status"},
            {"command": "services", "description": "Services"},
            {"command": "alerts", "description": "Alerts"},
        ])
    except Exception as exc:
        log.warning("setMyCommands failed: %s", exc)
    bot.monitor.start()
    log.info("started for admins %s, watching %s", ", ".join(cfg["admin_ids"]), ", ".join(cfg["services"]) or "no services")
    bot.poll()
    return 0
