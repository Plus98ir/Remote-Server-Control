"""Settings file: /etc/remote-server-control/config.json (mode 600).

Missing keys fall back to DEFAULTS, so an old config keeps working after
an update adds new options.
"""

import copy
import json
import os

PATH = os.environ.get("RSC_CONFIG", "/etc/remote-server-control/config.json")

DEFAULTS = {
    "token": "",
    "admin_ids": [],
    "proxy": "",  # socks5://user:pass@host:port, empty = direct
    "services": [],  # systemd units to watch
    "timezone": "UTC",  # for the daily report and timestamps
    "daily_report": "09:00",  # HH:MM, empty = off
    "check_every": 60,  # seconds between alert checks
    "alerts": {
        "ram_pct": 90,
        "disk_pct": 90,
        "load_per_cpu": 2.0,
        "repeat_after_min": 60,  # remind while a problem lasts
    },
    "dnsguard": {
        "db": "/opt/dnsguard/dnsguard.db",
        "health_url": "http://127.0.0.1:8000/health",
        "metrics": "/opt/dnsguard/metrics-24h.json",
        "nft_set": "inet dnsguard allowed_users",
        "expiry_days": 3,
    },
    "state": "/var/lib/remote-server-control/state.json",
}


def _merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load(path: str = PATH) -> dict:
    with open(path, encoding="utf-8") as fh:
        cfg = _merge(DEFAULTS, json.load(fh))
    if not cfg["token"]:
        raise ValueError(f"{path}: 'token' is empty")
    if not cfg["admin_ids"]:
        raise ValueError(f"{path}: 'admin_ids' is empty")
    cfg["admin_ids"] = [str(a).strip() for a in cfg["admin_ids"]]
    return cfg
