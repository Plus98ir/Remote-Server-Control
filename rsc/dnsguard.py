"""Read-only view of a DNSGuard install on the same server.

Nothing here writes to DNSGuard: the database is opened with
mode=ro, /health is a plain GET, the nft set is only listed and the
metrics file is only read. Each figure is read on its own, so a schema
change in DNSGuard turns one line into "n/a" instead of breaking the bot.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import subprocess
import time
import urllib.request
from urllib.parse import quote


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def _ts(value: dt.datetime) -> str:
    """Same text form SQLAlchemy stores DateTime in, so strings compare."""
    return value.strftime("%Y-%m-%d %H:%M:%S")


class DNSGuard:
    def __init__(self, cfg: dict):
        self.db_path = cfg.get("db", "")
        self.health_url = cfg.get("health_url", "")
        self.metrics_path = cfg.get("metrics", "")
        self.nft_set = cfg.get("nft_set", "").split()
        self.expiry_days = int(cfg.get("expiry_days", 3))
        self._user_cols: list[str] | None = None

    def installed(self) -> bool:
        return bool(self.db_path) and os.path.isfile(self.db_path)

    def _db(self) -> sqlite3.Connection:
        con = sqlite3.connect(f"file:{quote(self.db_path)}?mode=ro", uri=True, timeout=5)
        con.row_factory = sqlite3.Row
        return con

    def _all(self, sql: str, *args) -> list | None:
        try:
            con = self._db()
        except sqlite3.Error:
            return None
        try:
            return con.execute(sql, args).fetchall()
        except sqlite3.Error:
            return None
        finally:
            con.close()

    def _one(self, sql: str, *args):
        rows = self._all(sql, *args)
        return rows[0] if rows else None

    # ---- users ------------------------------------------------------------

    def _name_cols(self) -> str:
        if self._user_cols is None:
            rows = self._all("PRAGMA table_info(users)") or []
            have = {r["name"] for r in rows}
            self._user_cols = [c for c in ("tg_username", "username", "email", "telegram_id") if c in have]
        return "".join(f", u.{c} AS {c}" for c in self._user_cols)

    @staticmethod
    def name(row) -> str:
        keys = row.keys()
        if "tg_username" in keys and row["tg_username"]:
            return "@" + str(row["tg_username"]).lstrip("@")
        for col in ("username", "email", "telegram_id"):
            if col in keys and row[col]:
                return str(row[col])
        return f"user #{row['uid']}"

    # ---- live checks ------------------------------------------------------

    def health(self) -> tuple[bool, str]:
        if not self.health_url:
            return True, "not checked"
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(self.health_url, timeout=4) as resp:
                data = json.loads(resp.read() or b"{}")
            ok = data.get("status") == "ok"
            return ok, "OK" if ok else f"status={data.get('status')}"
        except Exception as exc:  # any failure means "not healthy"
            return False, type(exc).__name__ + (f": {exc}" if str(exc) else "")

    def firewall_ips(self) -> int | None:
        if len(self.nft_set) != 3:
            return None
        try:
            proc = subprocess.run(["nft", "-j", "list", "set", *self.nft_set],
                                  capture_output=True, text=True, timeout=10)
            for item in json.loads(proc.stdout).get("nftables", []):
                if "set" in item:
                    return len(item["set"].get("elem", []))
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
        return None

    def metrics(self) -> dict | None:
        """Queries and relay bytes over the last hour and 24 h."""
        try:
            with open(self.metrics_path) as fh:
                rows = json.load(fh)
        except (OSError, ValueError):
            return None
        now = int(time.time() // 60)
        out = {"q_1h": 0, "b_1h": 0, "q_24h": 0, "b_24h": 0, "age_min": None}
        for row in rows:
            if not (isinstance(row, list) and len(row) == 3):
                continue
            minute, queries, relay = row
            if minute > now - 60:
                out["q_1h"] += queries
                out["b_1h"] += relay
            if minute > now - 1440:
                out["q_24h"] += queries
                out["b_24h"] += relay
        if rows and isinstance(rows[-1], list):
            out["age_min"] = now - rows[-1][0]
        return out

    # ---- summary ----------------------------------------------------------

    def summary(self) -> dict:
        now = _utcnow()
        today = now.date().isoformat()
        month = now.date().replace(day=1).isoformat()
        s: dict = {}

        row = self._one("SELECT COUNT(*) AS n, SUM(is_active) AS active FROM users")
        s["users"] = (row["n"], row["active"] or 0) if row else None

        row = self._one("SELECT COUNT(*) AS n FROM tokens WHERE is_active = 1 "
                        "AND (expires_at IS NULL OR expires_at > ?)", _ts(now))
        s["tokens"] = row["n"] if row else None

        row = self._one("SELECT COUNT(*) AS n FROM allowed_ips "
                        "WHERE expires_at IS NULL OR expires_at > ?", _ts(now))
        s["ips"] = row["n"] if row else None

        row = self._one("SELECT COALESCE(SUM(query_count), 0) AS q, COALESCE(SUM(blocked_count), 0) AS b "
                        "FROM query_stats WHERE day = ?", today)
        s["queries"] = (row["q"], row["b"]) if row else None

        for key, since in (("traffic_today", today), ("traffic_month", month)):
            row = self._one("SELECT COALESCE(SUM(bytes_down), 0) AS d, COALESCE(SUM(bytes_up), 0) AS u "
                            "FROM traffic_stats WHERE day >= ?", since)
            s[key] = (row["d"], row["u"]) if row else None

        cols = self._name_cols()
        rows = self._all(
            f"SELECT u.id AS uid{cols}, SUM(ts.bytes_up + ts.bytes_down) AS total "
            "FROM traffic_stats ts JOIN tokens t ON t.id = ts.token_id JOIN users u ON u.id = t.user_id "
            "WHERE ts.day = ? GROUP BY u.id ORDER BY total DESC LIMIT 5", today)
        s["top"] = [(self.name(r), r["total"] or 0) for r in rows if r["total"]] if rows is not None else None

        rows = self._all(
            f"SELECT u.id AS uid{cols}, t.label AS label, t.expires_at AS expires_at "
            "FROM tokens t JOIN users u ON u.id = t.user_id WHERE t.is_active = 1 "
            "AND t.expires_at > ? AND t.expires_at <= ? ORDER BY t.expires_at",
            _ts(now), _ts(now + dt.timedelta(days=self.expiry_days)))
        s["expiring"] = [(self.name(r), r["label"], str(r["expires_at"])[:16]) for r in rows] \
            if rows is not None else None

        row = self._one("SELECT COUNT(*) AS n FROM domain_requests WHERE status = 'pending'")
        s["pending"] = row["n"] if row else None
        return s

    # ---- news since last check -------------------------------------------

    def last_ids(self) -> dict:
        out = {}
        for key, table in (("user", "users"), ("request", "domain_requests")):
            row = self._one(f"SELECT COALESCE(MAX(id), 0) AS n FROM {table}")
            out[key] = row["n"] if row else 0
        return out

    def new_users(self, after: int) -> list[tuple[int, str]]:
        rows = self._all(f"SELECT u.id AS uid{self._name_cols()} FROM users u WHERE u.id > ? ORDER BY u.id", after)
        return [(r["uid"], self.name(r)) for r in rows or []]

    def new_requests(self, after: int) -> list[tuple[int, str, str]]:
        rows = self._all(
            f"SELECT r.id AS rid, r.domain AS domain, u.id AS uid{self._name_cols()} "
            "FROM domain_requests r LEFT JOIN users u ON u.id = r.user_id "
            "WHERE r.id > ? AND r.status = 'pending' ORDER BY r.id", after)
        return [(r["rid"], r["domain"], self.name(r)) for r in rows or []]
