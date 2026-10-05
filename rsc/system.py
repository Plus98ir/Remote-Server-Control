"""Read server facts from /proc and standard tools (ss, ps, systemctl).

Every command runs with an argument list, never through a shell, so text
from Telegram can't inject commands.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import time
import urllib.request

from . import tg

HOST_RE = re.compile(
    r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)
OK_STATES = ("active", "activating", "reloading")


def run(args: list[str], timeout: float = 15) -> str:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return (proc.stdout or proc.stderr).strip()
    except FileNotFoundError:
        return f"{args[0]}: not installed"
    except subprocess.TimeoutExpired:
        return f"{args[0]}: timed out"


def human(n: float, unit: str = "B") -> str:
    n = float(n or 0)
    for prefix in ("", "K", "M", "G", "T"):
        if abs(n) < 1024 or prefix == "T":
            return f"{n:.0f} {prefix}{unit}" if prefix == "" or n >= 100 else f"{n:.1f} {prefix}{unit}"
        n /= 1024
    return ""


def rate(bytes_per_sec: float) -> str:
    bits = bytes_per_sec * 8
    for prefix in ("", "k", "M", "G"):
        if bits < 1000 or prefix == "G":
            return f"{bits:.0f} {prefix}bit/s" if bits >= 100 or prefix == "" else f"{bits:.1f} {prefix}bit/s"
        bits /= 1000
    return ""


def duration(seconds: float) -> str:
    seconds = int(max(seconds, 0))
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d}d {h}h"
    if h:
        return f"{h}h {m}m"
    return f"{m}m" if m else f"{seconds}s"


def short(n: float) -> str:
    """Compact size for monospace tables: 512B, 1.5K, 666M, 18.3G."""
    n = float(n or 0)
    for prefix in ("B", "K", "M", "G", "T"):
        if abs(n) < 1024 or prefix == "T":
            return f"{n:.0f}{prefix}" if prefix == "B" or n >= 100 else f"{n:.1f}{prefix}"
        n /= 1024
    return ""


def bar(pct: float, width: int = 10) -> str:
    """Block bar for <pre> text; these glyphs keep one width in monospace fonts."""
    full = int(round(max(0, min(pct, 100)) / 100 * width))
    return "█" * full + "░" * (width - full)


def parse_ping(out: str) -> dict:
    """Numbers from Linux ping output; missing parts are None."""
    res = {"sent": None, "received": None, "loss": None, "min": None, "avg": None, "max": None, "mdev": None}
    m = re.search(r"(\d+) packets transmitted, (\d+) (?:packets )?received", out)
    if m:
        res["sent"], res["received"] = int(m.group(1)), int(m.group(2))
    m = re.search(r"([\d.]+)% packet loss", out)
    if m:
        res["loss"] = float(m.group(1))
    m = re.search(r"= ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+) ms", out)
    if m:
        res["min"], res["avg"], res["max"], res["mdev"] = (float(x) for x in m.groups())
    return res


def valid_target(text: str) -> bool:
    try:
        ipaddress.ip_address(text)
        return True
    except ValueError:
        return bool(HOST_RE.match(text))


# ---- /proc readers -------------------------------------------------------

def hostname() -> str:
    return socket.gethostname()


def uptime() -> float:
    with open("/proc/uptime") as fh:
        return float(fh.read().split()[0])


def boot_id() -> str:
    try:
        with open("/proc/sys/kernel/random/boot_id") as fh:
            return fh.read().strip()
    except OSError:
        return str(int(time.time() - uptime()))


def _cpu_times() -> tuple[int, int]:
    with open("/proc/stat") as fh:
        vals = [int(v) for v in fh.readline().split()[1:]]
    idle = vals[3] + (vals[4] if len(vals) > 4 else 0)  # idle + iowait
    return sum(vals), idle


def memory() -> dict:
    info = {}
    with open("/proc/meminfo") as fh:
        for line in fh:
            key, value = line.split(":", 1)
            info[key] = int(value.split()[0]) * 1024
    total = info["MemTotal"]
    avail = info.get("MemAvailable", info.get("MemFree", 0))
    swap_total = info.get("SwapTotal", 0)
    return {
        "total": total, "available": avail, "used": total - avail,
        "pct": round(100 * (total - avail) / total, 1) if total else 0,
        "swap_total": swap_total, "swap_used": swap_total - info.get("SwapFree", 0),
    }


def disk(path: str = "/") -> dict:
    du = shutil.disk_usage(path)
    return {"total": du.total, "used": du.used, "free": du.free,
            "pct": round(100 * du.used / du.total, 1) if du.total else 0}


def default_iface() -> str | None:
    try:
        with open("/proc/net/route") as fh:
            for line in fh.readlines()[1:]:
                parts = line.split()
                if len(parts) > 1 and parts[1] == "00000000":
                    return parts[0]
    except OSError:
        pass
    return None


def net_counters(iface: str | None) -> tuple[int, int]:
    """(rx, tx) bytes of the default-route interface, or of all but lo."""
    rx = tx = 0
    with open("/proc/net/dev") as fh:
        for line in fh.readlines()[2:]:
            name, data = line.split(":", 1)
            name = name.strip()
            if (iface and name != iface) or (not iface and name == "lo"):
                continue
            fields = data.split()
            rx += int(fields[0])
            tx += int(fields[8])
    return rx, tx


def sample(interval: float = 1.0) -> dict:
    """CPU % and network rate measured over `interval` seconds."""
    iface = default_iface()
    c1, n1 = _cpu_times(), net_counters(iface)
    time.sleep(interval)
    c2, n2 = _cpu_times(), net_counters(iface)
    total, idle = c2[0] - c1[0], c2[1] - c1[1]
    return {
        "cpu": round(100 * (1 - idle / total), 1) if total > 0 else 0.0,
        "iface": iface or "all",
        "rx_rate": (n2[0] - n1[0]) / interval, "tx_rate": (n2[1] - n1[1]) / interval,
        "rx_total": n2[0], "tx_total": n2[1],
    }


def top_processes(n: int = 5) -> list[tuple[str, float, int]]:
    """[(name, cpu %, rss bytes)] by memory."""
    out = run(["ps", "-eo", "comm,%cpu,rss", "--sort=-rss", "--no-headers"])
    rows = []
    for line in out.splitlines()[:n]:
        parts = line.rsplit(None, 2)
        if len(parts) == 3:
            try:
                rows.append((parts[0], float(parts[1]), int(parts[2]) * 1024))
            except ValueError:
                pass
    return rows


# ---- services ------------------------------------------------------------

def services(names: list[str]) -> list[dict]:
    """State, uptime, memory and restart count of systemd units."""
    if not names:
        return []
    out = run(["systemctl", "show", *names, "-p",
               "Id,ActiveState,SubState,ActiveEnterTimestampMonotonic,MemoryCurrent,NRestarts"])
    blocks = [b for b in out.split("\n\n") if b.strip()]
    up = uptime()
    result = []
    for name, block in zip(names, blocks + [""] * len(names)):
        props = dict(line.split("=", 1) for line in block.splitlines() if "=" in line)
        try:
            mono = int(props.get("ActiveEnterTimestampMonotonic", "0"))
        except ValueError:
            mono = 0
        try:
            mem = int(props.get("MemoryCurrent", ""))
            mem = mem if mem < 1 << 60 else None
        except ValueError:
            mem = None
        state = props.get("ActiveState", "unknown")
        result.append({
            "name": name, "state": state, "sub": props.get("SubState", ""),
            "since": up - mono / 1e6 if mono and state == "active" else None,
            "memory": mem, "restarts": props.get("NRestarts", "0"),
        })
    return result


def service_logs(name: str, lines: int = 25) -> str:
    return run(["journalctl", "-u", name, "-n", str(lines), "--no-pager", "-o", "short"])


def restart_service(name: str) -> str:
    out = run(["systemctl", "restart", name], timeout=60)
    state = run(["systemctl", "is-active", name])
    return f"{state}{(': ' + out) if out else ''}"


# ---- network -------------------------------------------------------------

def port_table(ports: list[tuple[str, int, str, str]]) -> list[tuple[str, int, str, str]]:
    """Merge tcp+udp and several bind addresses of one port/process into one row."""
    merged: dict = {}
    for proto, port, addr, proc in ports:
        row = merged.setdefault((port, proc), [set(), set()])
        row[0].add(proto)
        row[1].add("local" if addr in ("127.0.0.1", "::1") else addr)
    out = []
    for (port, proc), (protos, addrs) in sorted(merged.items()):
        if "*" in addrs:
            where = ""
        elif len(addrs) == 1:
            where = next(iter(addrs))
        else:
            where = "local+" if "local" in addrs else ""
            where += f"{len(addrs - {'local'})} IPs" if addrs - {"local"} else ""
        out.append(("/".join(sorted(protos)), port, proc, where))
    return out


def listening_ports() -> list[tuple[str, int, str, str]]:
    """[(proto, port, bind address, process)] without duplicates."""
    out = run(["ss", "-tulnpH"])
    seen, rows = set(), []
    for line in out.splitlines():
        parts = line.split(None, 6)
        if len(parts) < 5:
            continue
        proto, local = parts[0], parts[4]
        addr, _, port = local.rpartition(":")
        if not port.isdigit():
            continue
        match = re.search(r'\(\("([^"]+)"', parts[6] if len(parts) > 6 else "")
        proc = match.group(1) if match else "?"
        addr = addr.strip("[]").split("%")[0]
        addr = "*" if addr in ("", "*", "0.0.0.0", "::") else addr
        key = (proto, int(port), addr, proc)
        if key not in seen:
            seen.add(key)
            rows.append(key)
    return sorted(rows, key=lambda r: (r[1], r[0]))


def connection_count() -> int:
    out = run(["ss", "-Htn", "state", "established"])
    return len([line for line in out.splitlines() if line.strip()])


def ping(target: str) -> str:
    return run(["ping", "-c", "4", "-W", "2", "--", target], timeout=25)


def geoip(target: str, proxy: str = "") -> dict:
    url = (f"http://ip-api.com/json/{target}"
           "?fields=status,message,query,country,countryCode,regionName,city,isp,org,as")
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url, timeout=5) as resp:
            return json.loads(resp.read())
    except (OSError, ValueError):
        if not proxy:
            raise
        _, body = tg.request(url, proxy=proxy, timeout=10)
        return json.loads(body)


def clean_up() -> dict:
    """Free disk (apt cache, old journal) and page cache. Returns what changed."""
    disk_before, mem_before = disk()["free"], memory()["available"]
    steps = [
        ("APT cache", ["apt-get", "clean"]),
        ("Journal older than 3 days", ["journalctl", "--vacuum-time=3d"]),
    ]
    done = []
    for label, args in steps:
        if shutil.which(args[0]):
            run(args, timeout=120)
            done.append(label)
    try:
        os.sync()
        with open("/proc/sys/vm/drop_caches", "w") as fh:
            fh.write("1\n")
        done.append("Page cache")
    except OSError:
        pass
    return {"steps": done, "disk_freed": disk()["free"] - disk_before,
            "ram_freed": memory()["available"] - mem_before}
