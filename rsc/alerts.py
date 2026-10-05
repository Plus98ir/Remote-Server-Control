"""Background checks that message the admins when something goes wrong.

A problem has to show up on `need` checks in a row before it alerts
(no noise from a one-second spike), reminds every `repeat_after_min`
while it lasts, and sends a recovery message when it clears.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import logging
import os
import threading
import time

from . import system

log = logging.getLogger("rsc.alerts")
E = lambda s: html.escape(str(s), quote=False)  # noqa: E731


def tz(name: str) -> dt.tzinfo:
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        return dt.timezone.utc


class Monitor(threading.Thread):
    def __init__(self, cfg: dict, api, dg, report=None):
        super().__init__(name="monitor", daemon=True)
        self.cfg = cfg
        self.api = api
        self.dg = dg
        self.report = report  # callable -> daily report text
        self.tz = tz(cfg["timezone"])
        self.path = cfg["state"]
        self.state = self._load()
        self.lock = threading.Lock()
        self.streak: dict[str, int] = {}
        self.active: dict[str, dict] = {}  # key -> since, last, text
        self.stop = threading.Event()

    # ---- state file -------------------------------------------------------

    def _load(self) -> dict:
        try:
            with open(self.path) as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return {}

    def save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w") as fh:
                json.dump(self.state, fh)
            os.replace(tmp, self.path)
        except OSError as exc:
            log.warning("cannot save state: %s", exc)

    # ---- mute ---------------------------------------------------------------

    def muted_until(self) -> float:
        until = self.state.get("muted_until", 0)
        return until if until > time.time() else 0

    def mute(self, minutes: int) -> None:
        with self.lock:
            self.state["muted_until"] = time.time() + minutes * 60 if minutes else 0
            self.save()

    # ---- sending ------------------------------------------------------------

    def notify(self, text: str, force: bool = False) -> None:
        if not force and self.muted_until():
            log.info("muted: %s", text.splitlines()[0])
            return
        for admin in self.cfg["admin_ids"]:
            try:
                self.api.send(admin, text)
            except Exception as exc:
                log.warning("alert to %s failed: %s", admin, exc)

    def condition(self, key: str, bad: bool, need: int, bad_text: str, ok_text: str) -> None:
        now = time.time()
        if not bad:
            self.streak[key] = 0
            gone = self.active.pop(key, None)
            if gone:
                self.notify(f"✅ {ok_text}\n<i>after {system.duration(now - gone['since'])}</i>")
            return
        self.streak[key] = self.streak.get(key, 0) + 1
        if self.streak[key] < need:
            return
        cur = self.active.get(key)
        if cur is None:
            self.active[key] = {"since": now, "last": now, "text": bad_text}
            self.notify(f"🚨 {bad_text}")
        else:
            cur["text"] = bad_text
            if now - cur["last"] >= self.cfg["alerts"]["repeat_after_min"] * 60:
                cur["last"] = now
                self.notify(f"⏰ Still: {bad_text}\n<i>for {system.duration(now - cur['since'])}</i>")

    def problems(self) -> list[str]:
        return [a["text"] for a in self.active.values()]

    # ---- checks -------------------------------------------------------------

    def startup(self) -> None:
        host = E(system.hostname())
        boot, prev = system.boot_id(), self.state.get("boot_id")
        if prev is None:
            self.notify(f"✅ <b>Monitor started</b> on <code>{host}</code>.\nSend /start for the menu.", force=True)
        elif prev != boot:
            self.notify(f"🔄 <b>{host} rebooted</b>\n<i>up for {system.duration(system.uptime())}</i>", force=True)
        self.state["boot_id"] = boot
        if "last_report" not in self.state:
            self.state["last_report"] = dt.datetime.now(self.tz).date().isoformat()
        if self.dg.installed() and "dg_last" not in self.state:
            self.state["dg_last"] = self.dg.last_ids()
        self.save()

    def check(self) -> None:
        a = self.cfg["alerts"]
        mem = system.memory()
        self.condition("ram", mem["pct"] >= a["ram_pct"], 3,
                       f"<b>RAM {mem['pct']:.0f}%</b> used, {system.human(mem['available'])} available",
                       f"RAM back to {mem['pct']:.0f}%")
        d = system.disk()
        self.condition("disk", d["pct"] >= a["disk_pct"], 1,
                       f"<b>Disk {d['pct']:.0f}%</b> full, {system.human(d['free'])} free",
                       f"Disk back to {d['pct']:.0f}%")
        load, cpus = os.getloadavg()[0], os.cpu_count() or 1
        self.condition("load", load > a["load_per_cpu"] * cpus, 3,
                       f"<b>High load {load:.2f}</b> on {cpus} core(s)", f"Load back to {load:.2f}")

        for svc in system.services(self.cfg["services"]):
            name = E(svc["name"])
            self.condition(f"svc:{svc['name']}", svc["state"] not in system.OK_STATES, 2,
                           f"Service <b>{name}</b> is {E(svc['state'])} ({E(svc['sub'])})",
                           f"Service <b>{name}</b> is running again")

        if self.dg.installed():
            self.check_dnsguard()
        self.daily()
        with self.lock:
            self.save()

    def check_dnsguard(self) -> None:
        ok, info = self.dg.health()
        self.condition("dg_health", not ok, 2, f"<b>DNSGuard /health</b> fails: {E(info)}",
                       "DNSGuard /health is OK again")
        last = self.state.setdefault("dg_last", self.dg.last_ids())
        for uid, name in self.dg.new_users(last.get("user", 0)):
            self.notify(f"👤 New DNSGuard user: <b>{E(name)}</b>")
            last["user"] = uid
        for rid, domain, name in self.dg.new_requests(last.get("request", 0)):
            self.notify(f"📝 Domain request: <code>{E(domain)}</code> from {E(name)}")
            last["request"] = rid

    def daily(self) -> None:
        at = self.cfg.get("daily_report") or ""
        if not at or not self.report:
            return
        now = dt.datetime.now(self.tz)
        today = now.date().isoformat()
        if now.strftime("%H:%M") >= at and self.state.get("last_report") != today:
            self.state["last_report"] = today
            self.notify(self.report())

    def run(self) -> None:
        try:
            self.startup()
        except Exception:
            log.exception("startup check failed")
        while not self.stop.wait(self.cfg["check_every"]):
            try:
                self.check()
            except Exception:
                log.exception("check failed")
