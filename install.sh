#!/usr/bin/env bash
# Remote Server Control - installer / updater / uninstaller.
#
#   bash install.sh                  install or update (asks what it needs)
#   bash install.sh --reconfigure    ask for the settings again
#   bash install.sh --uninstall      remove the service and code (keeps config)
#   bash install.sh --uninstall --purge   remove config and state too
#
# Non-interactive: --token T --admin ID[,ID] [--proxy socks5://u:p@host:port|none]
#                  [--tz Area/City] [--report HH:MM|off] [--services a,b,c] --yes
set -euo pipefail

APP=remote-server-control
DIR=/opt/$APP
CONF_DIR=/etc/$APP
CONF=$CONF_DIR/config.json
STATE_DIR=/var/lib/$APP
UNIT=/etc/systemd/system/$APP.service
REPO=https://github.com/Plus98ir/Remote-Server-Control

GREEN=$'\e[32m'; RED=$'\e[31m'; YELLOW=$'\e[33m'; RESET=$'\e[0m'
info() { echo "${GREEN}==>${RESET} $*"; }
warn() { echo "${YELLOW}warning:${RESET} $*"; }
die() { echo "${RED}error:${RESET} $*" >&2; exit 1; }

TOKEN=${RSC_TOKEN:-}; ADMIN=${RSC_ADMIN:-}; PROXY=${RSC_PROXY:-}; TZONE=${RSC_TZ:-}
REPORT=${RSC_REPORT:-}; SERVICES=${RSC_SERVICES:-}
RECONF=0; UNINSTALL=0; PURGE=0; YES=0
while [ $# -gt 0 ]; do
    case "$1" in
        --token) TOKEN=$2; shift ;;
        --admin) ADMIN=$2; shift ;;
        --proxy) PROXY=$2; shift ;;
        --tz) TZONE=$2; shift ;;
        --report) REPORT=$2; shift ;;
        --services) SERVICES=$2; shift ;;
        --reconfigure) RECONF=1 ;;
        --uninstall) UNINSTALL=1 ;;
        --purge) PURGE=1 ;;
        --yes|-y) YES=1 ;;
        -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
        *) die "unknown option: $1" ;;
    esac
    shift
done

[ "$(id -u)" -eq 0 ] || die "run as root"
command -v systemctl >/dev/null || die "systemd is required"

if [ "$UNINSTALL" -eq 1 ]; then
    info "Removing $APP"
    systemctl disable --now "$APP" 2>/dev/null || true
    rm -f "$UNIT"
    systemctl daemon-reload
    rm -rf "$DIR"
    if [ "$PURGE" -eq 1 ]; then
        rm -rf "$CONF_DIR" "$STATE_DIR"
        info "Removed code, config and state."
    else
        info "Removed. Config kept in $CONF (use --purge to delete it)."
    fi
    exit 0
fi

command -v python3 >/dev/null || { info "Installing python3"; apt-get update -y && apt-get install -y python3; }
python3 -c 'import sys; sys.exit(sys.version_info < (3, 8))' || die "Python 3.8 or newer is required"

ask() {  # ask VAR "question" "default"
    local answer
    if [ "$YES" -eq 1 ] || [ ! -r /dev/tty ]; then
        printf -v "$1" '%s' "$3"
        return
    fi
    read -r -p "$2${3:+ [$3]}: " answer </dev/tty || true
    printf -v "$1" '%s' "${answer:-$3}"
}

# ---- settings ---------------------------------------------------------------
if [ ! -f "$CONF" ] || [ "$RECONF" -eq 1 ]; then
    [ -n "$TOKEN" ] || ask TOKEN "Telegram bot token (from @BotFather)" ""
    [[ "$TOKEN" =~ ^[0-9]+:[A-Za-z0-9_-]{30,}$ ]] || die "that does not look like a bot token"
    [ -n "$ADMIN" ] || ask ADMIN "Admin Telegram user id(s), comma separated" ""
    [[ "$ADMIN" =~ ^[0-9]+(,[0-9]+)*$ ]] || die "admin ids must be numbers, e.g. 12345 or 12345,67890"

    if [ -z "$PROXY" ]; then
        detected=""
        # A DNSGuard install on the same server already has a working proxy (read only).
        if [ -f /opt/dnsguard/.env ]; then
            detected=$(sed -n 's/^BOT_PROXY=//p' /opt/dnsguard/.env | tail -n 1 | tr -d '"'"'"' ')
            [[ "$detected" == socks5* ]] || detected=""
        fi
        [ -n "$detected" ] && info "Found the DNSGuard bot proxy, using it unless you enter another."
        ask PROXY "SOCKS5 proxy for Telegram (socks5://user:pass@host:port, 'none' = direct)" "$detected"
    fi
    [ "$PROXY" = "none" ] && PROXY=""
    [ -z "$PROXY" ] || [[ "$PROXY" =~ ^socks5h?:// ]] || die "only socks5:// proxies are supported"

    sys_tz=$(timedatectl show -p Timezone --value 2>/dev/null || echo UTC)
    [ -n "$TZONE" ] || ask TZONE "Timezone for times and the daily report" "${sys_tz:-UTC}"
    [ -f "/usr/share/zoneinfo/$TZONE" ] || [ "$TZONE" = "UTC" ] || die "unknown timezone: $TZONE"
    [ -n "$REPORT" ] || ask REPORT "Daily report time HH:MM ('off' = none)" "09:00"
    [ "$REPORT" = "off" ] && REPORT=""
    [ -z "$REPORT" ] || [[ "$REPORT" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]] || die "report time must be HH:MM"

    if [ -z "$SERVICES" ]; then
        found=()
        for s in dnsguard dnsguard-bot dnsguard-accel AdGuardHome caddy nginx apache2 haproxy \
                 x-ui xray v2ray sing-box hysteria-server marzban docker mysql mariadb postgresql \
                 redis-server fail2ban wg-quick@wg0 gameping smart-caddy-ui; do
            systemctl is-active --quiet "$s" 2>/dev/null && found+=("$s")
        done
        SERVICES=$(IFS=,; echo "${found[*]:-}")
        ask SERVICES "Services to watch, comma separated" "$SERVICES"
    fi

    mkdir -p "$CONF_DIR"
    umask 077
    RSC_TOKEN=$TOKEN RSC_ADMIN=$ADMIN RSC_PROXY=$PROXY RSC_TZ=$TZONE RSC_REPORT=$REPORT \
    RSC_SERVICES=$SERVICES RSC_CONF=$CONF RSC_STATE=$STATE_DIR/state.json python3 - <<'EOF'
import json, os
path = os.environ["RSC_CONF"]
old = {}
if os.path.exists(path):
    with open(path) as fh:
        old = json.load(fh)
split = lambda s: [x.strip() for x in s.split(",") if x.strip()]
old.update({
    "token": os.environ["RSC_TOKEN"],
    "admin_ids": split(os.environ["RSC_ADMIN"]),
    "proxy": os.environ["RSC_PROXY"],
    "services": split(os.environ["RSC_SERVICES"]),
    "timezone": os.environ["RSC_TZ"],
    "daily_report": os.environ["RSC_REPORT"],
    "state": os.environ["RSC_STATE"],
})
with open(path, "w") as fh:
    json.dump(old, fh, indent=2)
EOF
    chmod 600 "$CONF"
    umask 022
    info "Saved settings to $CONF"
else
    info "Keeping settings in $CONF (use --reconfigure to change them)"
fi

# ---- code -------------------------------------------------------------------
SRC=""
here=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)
if [ -n "$here" ] && [ -f "$here/rsc/bot.py" ]; then
    SRC=$here
else
    tmp=$(mktemp -d)
    trap 'rm -rf "$tmp"' EXIT
    info "Downloading code from $REPO"
    proxy_arg=()
    cfg_proxy=$(python3 -c "import json;print(json.load(open('$CONF')).get('proxy',''))")
    [ -n "$cfg_proxy" ] && proxy_arg=(--proxy "${cfg_proxy/socks5:/socks5h:}")
    curl -fsSL "${proxy_arg[@]}" "$REPO/archive/refs/heads/main.tar.gz" | tar -xz -C "$tmp" \
        || curl -fsSL "$REPO/archive/refs/heads/main.tar.gz" | tar -xz -C "$tmp" \
        || die "download failed"
    SRC=$(find "$tmp" -maxdepth 2 -name rsc -type d -printf '%h\n' | head -n 1)
    [ -n "$SRC" ] || die "downloaded archive has no rsc/ folder"
fi
mkdir -p "$DIR" "$STATE_DIR"
rm -rf "$DIR/rsc"
cp -r "$SRC/rsc" "$DIR/rsc"
find "$DIR/rsc" -name '__pycache__' -prune -exec rm -rf {} +
info "Installed code to $DIR"

# ---- service ----------------------------------------------------------------
cat >"$UNIT" <<EOF
[Unit]
Description=Remote Server Control (Telegram monitor bot)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$DIR
Environment=PYTHONUNBUFFERED=1
Environment=RSC_CONFIG=$CONF
ExecStart=$(command -v python3) -m rsc
Restart=always
RestartSec=10
MemoryMax=80M
Nice=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload

info "Testing the Telegram connection"
if (cd "$DIR" && RSC_CONFIG=$CONF timeout 40 python3 -m rsc --check); then
    :
else
    warn "could not reach Telegram now; the service keeps retrying. Check the proxy setting."
fi

systemctl enable "$APP" >/dev/null 2>&1
systemctl restart "$APP"
sleep 2
if systemctl is-active --quiet "$APP"; then
    info "Done. The bot is running. Send /start to it in Telegram."
    echo "    logs:     journalctl -u $APP -f"
    echo "    settings: $CONF (then: systemctl restart $APP)"
else
    die "service did not start; see: journalctl -u $APP -n 50"
fi
