# Remote Server Control

A lightweight Telegram bot to **monitor and manage a Linux server** from your phone: live resources, systemd services, open ports, ping / Geo IP tools and automatic alerts. If [DNSGuard](#dnsguard-read-only) runs on the same server, the bot also shows its users, queries and relay traffic, **read-only**.

- **Zero dependencies**: Python standard library only, no `pip`. That's useful on servers where PyPI is slow or blocked.
- **Tiny**: about 15 MB of RAM. The service is capped at 80 MB.
- **Works behind filtering**: optional SOCKS5 proxy for the Telegram API, with remote DNS.
- **Private**: answers only the admin ids you set, and only in private chat.

## Features

| Menu | What you get |
|---|---|
| 📊 **Status** | CPU, RAM, swap and disk bars, load, network speed and totals, top processes by memory |
| ⚙️ **Services** | State, uptime, memory and restart count of every watched unit. Shows the last log lines, and restarts a service after you confirm. |
| 🛡 **DNSGuard** | Health, users, live tokens, registered and firewall IPs, queries today and in the last hour, relay traffic (today and this month), top users, expiring tokens, pending domain requests |
| 🌐 **Network** | Listening ports with process and bind address, established TCP connections |
| 🏓 **Ping** / 🌍 **Geo IP** | Ping summary (loss, avg/min/max, jitter), and country / ISP / AS of any IP or host |
| 🔔 **Alerts** | Thresholds, open problems, mute for 1 h or 8 h, send the report now |
| 🧹 **Clean up** | APT cache, journal older than 3 days and the RAM page cache, after you confirm |

### Automatic alerts

Checked every 60 seconds. A problem must show up on several checks in a row before it alerts, so short spikes don't cause noise. While a problem lasts you get a reminder every hour, and a ✅ message when it clears.

- RAM or disk ≥ 90 %, load > 2 × CPU cores
- A watched service stops or fails
- DNSGuard `/health` stops answering
- Server rebooted
- New DNSGuard user or new domain request
- **Daily report** at a time you choose (default 09:00, in your timezone)

## Install

Run as root on the server (Ubuntu / Debian or any distro with systemd and Python ≥ 3.8):

```bash
bash <(curl -fsSL https://github.com/Plus98ir/Remote-Server-Control/releases/latest/download/install.sh)
```

The installer asks for:

1. **Bot token**: create a bot with [@BotFather](https://t.me/BotFather). Use a new bot: two programs polling the same token steal each other's messages.
2. **Admin user id(s)**: your numeric Telegram id ([@userinfobot](https://t.me/userinfobot) shows it). Separate several ids with commas.
3. **SOCKS5 proxy** (optional): `socks5://user:pass@127.0.0.1:1080`. Leave it empty if the server reaches Telegram directly. If DNSGuard is installed, its bot proxy is offered as the default.
4. **Timezone** and **daily report time**.
5. **Services to watch**: common ones that are running are detected for you (DNSGuard, Caddy, Nginx, x-ui, Xray, sing-box, Hysteria, Docker, databases, fail2ban, …).

It then tests the Telegram connection, installs a systemd service and starts it. Send `/start` to your bot.

### Non-interactive

```bash
RSC_TOKEN='123456:ABC...' bash install.sh --admin 11111111 --proxy none \
    --tz Asia/Tehran --report 09:00 --services nginx,docker --yes
```

Passing the token through `RSC_TOKEN` keeps it out of the process list.

### Update, reconfigure, remove

```bash
bash install.sh                 # update the code, keep the settings
bash install.sh --reconfigure   # ask for every setting again
bash install.sh --uninstall     # remove service and code, keep settings
bash install.sh --uninstall --purge   # remove settings and state too
```

## Settings

`/etc/remote-server-control/config.json` (mode `600`, it holds the token). Restart the service after editing it: `systemctl restart remote-server-control`.

```json
{
  "token": "123456:ABC...",
  "admin_ids": ["11111111"],
  "proxy": "socks5://user:pass@127.0.0.1:1080",
  "services": ["nginx", "docker"],
  "timezone": "Asia/Tehran",
  "daily_report": "09:00",
  "check_every": 60,
  "alerts": { "ram_pct": 90, "disk_pct": 90, "load_per_cpu": 2.0, "repeat_after_min": 60 },
  "dnsguard": { "db": "/opt/dnsguard/dnsguard.db", "health_url": "http://127.0.0.1:8000/health",
                "metrics": "/opt/dnsguard/metrics-24h.json", "nft_set": "inet dnsguard allowed_users",
                "expiry_days": 3 }
}
```

You can leave out any key; the defaults above are used.

| Path | Purpose |
|---|---|
| `/opt/remote-server-control/rsc/` | Code |
| `/etc/remote-server-control/config.json` | Settings |
| `/var/lib/remote-server-control/state.json` | Alert state (mute, last report, reboot detection) |
| `journalctl -u remote-server-control -f` | Logs |

## DNSGuard (read-only)

When the DNSGuard database exists, the 🛡 menu and the DNSGuard alerts turn on automatically. The bot **never changes DNSGuard**:

- the SQLite database is opened with `mode=ro`
- `/health` is a plain GET on localhost
- the firewall set is only listed (`nft -j list set …`)
- `metrics-24h.json` is only read

Each figure is read on its own. If a DNSGuard update changes its schema, the affected line shows `n/a` and the rest keeps working. Without DNSGuard, the menu is hidden and the bot is a plain server monitor.

## Security

- Updates from anyone who isn't in `admin_ids`, and from groups, are ignored without a reply.
- Ping and Geo IP input must be a valid IP or host name, and commands run without a shell, so nothing typed in Telegram can inject commands.
- Restart and Clean up ask for confirmation.
- The service runs as root, because it needs `systemctl`, `journalctl` and `nft`. Keep your Telegram account secure (2FA).

## Development

```
rsc/
  tg.py        Telegram Bot API client with a built-in SOCKS5 client
  system.py    /proc, ss, ps, systemctl, ping, Geo IP
  dnsguard.py  read-only DNSGuard view
  alerts.py    background checks and the daily report
  bot.py       menu, views, button callbacks, polling loop
tests/test_offline.py   offline tests (fake Telegram, fake SOCKS5, temp database)
install.sh              install / update / uninstall
```

Run the tests on Linux: `python3 -m unittest discover -s tests -v`

## Changelog

### v2.0.0
- Rewritten as a Python package that uses only the standard library, with a new installer (update, reconfigure, uninstall, non-interactive mode).
- New: services view with logs and restart, automatic alerts, daily report, mute, read-only DNSGuard dashboard, network view, clean-up with before/after numbers.
- The proxy is now optional, and SOCKS5 with username/password is supported natively.
- Security: inputs are validated, no shell commands, admin-only and private chat only.
- Removed the ipset / `traffic.sh` / AdGuard-monitor features of v1, which depended on files the installer did not provide.

### v1.0.0
- First release: single install script generating a pyTelegramBotAPI bot.
