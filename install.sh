#!/bin/bash

# ==========================================
# Auto Installer for Telegram Server Bot
# ==========================================

GREEN="\e[32m"
RED="\e[31m"
YELLOW="\e[33m"
RESET="\e[0m"

echo -e "${GREEN}======================================${RESET}"
echo -e "${GREEN}   Telegram Bot Auto Installer        ${RESET}"
echo -e "${GREEN}======================================${RESET}"
echo ""

read -p "Enter Telegram Bot Token (API): " BOT_TOKEN
read -p "Enter Admin Chat ID: " ADMIN_ID
read -p "Enter Proxy Port (e.g. 45248): " PROXY_PORT
read -p "Enter Proxy Username: " PROXY_USER
read -p "Enter Proxy Password: " PROXY_PASS

echo -e "\n${YELLOW}[1/4] Installing Required Packages...${RESET}"
apt-get update -y
apt-get install -y python3 python3-pip curl ipset iptables
pip3 install pyTelegramBotAPI --break-system-packages 2>/dev/null || pip3 install pyTelegramBotAPI

echo -e "${YELLOW}[2/4] Generating Python Script (/root/remote_bot.py)...${RESET}"

cat << 'EOF' > /root/remote_bot.py
#!/root/remote_bot.py
import telebot
from telebot import apihelper
import subprocess
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import urllib.request
import json
import time
import threading

# PROXY_PLACEHOLDER

TOKEN = 'REPLACE_TOKEN'
ADMIN_ID = REPLACE_ADMIN_ID
bot = telebot.TeleBot(TOKEN)

def is_admin(message):
    return message.chat.id == REPLACE_ADMIN_ID

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    if not is_admin(message): return
    try:
        bot.delete_message(message.chat.id, message.message_id)
    except:
        pass
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = KeyboardButton("1️⃣ Users Report")
    btn2 = KeyboardButton("➕ Add IP")
    btn3 = KeyboardButton("➖ Remove IP")
    btn4 = KeyboardButton("📦 Packets")
    btn5 = KeyboardButton("📊 Server Status")
    btn6 = KeyboardButton("🏓 Ping Test")
    btn7 = KeyboardButton("🌐 Active Ports")
    btn8 = KeyboardButton("🧹 Clear Cache")
    btn9 = KeyboardButton("🔍 IP Reader")
    btn10 = KeyboardButton("🚫 Blacklist")
    btn11 = KeyboardButton("💾 Bandwidth (Hajm)")
    btn12 = KeyboardButton("🌍 Geo IP Lookup")

    markup.add(btn1, btn11)
    markup.add(btn2, btn3)
    markup.add(btn5, btn6)
    markup.add(btn7, btn8)
    markup.add(btn4, btn9)
    markup.add(btn10, btn12)

    panel_text = "🎛 <b>SERVER USAGE PANEL - IRAN</b> 🇮🇷\n━━━━━━━━━━━━━━━━━━━━\n🤖 <i>Please select an option below:</i>"
    bot.send_message(message.chat.id, panel_text, parse_mode="HTML", reply_markup=markup)

@bot.message_handler(func=lambda message: True)
def handle_reply_buttons(message):
    if not is_admin(message): return
    try: bot.delete_message(message.chat.id, message.message_id)
    except: pass
    text = message.text

    if "Users Report" in text:
        loading_msg = bot.send_message(message.chat.id, "Fetching traffic and user information... ⏳")
        bash_script = """#!/bin/bash
echo "🌐 <b>Global Server Traffic</b>"
echo "━━━━━━━━━━━━━━━━━━━━"
get_traffic() {
    raw=$(iptables -t mangle -L -n -v -x 2>/dev/null | grep -i "$2" | grep -E "dpt:$1|spt:$1" | awk '{sum+=$2} END {print sum}')
    [ -z "$raw" ] && raw=0
    if [ "$raw" -lt 1048576 ]; then echo "$(($raw / 1024)) KB"
    elif [ "$raw" -lt 1073741824 ]; then echo "$(($raw / 1048576)) MB"
    else echo $(awk 'BEGIN {printf "%.2f GB", '$raw'/1073741824}'); fi
}
echo "   ├ 🌍 <b>PORT 80:</b> <code>$(get_traffic 80 tcp)</code>"
echo "   ├ 🔒 <b>PORT 443 (TCP):</b> <code>$(get_traffic 443 tcp)</code>"
echo "   └ 🚀 <b>PORT 443 (UDP):</b> <code>$(get_traffic 443 udp)</code>"
echo ""
echo "👥 <b>Active Users (IPSec)</b>"
echo "━━━━━━━━━━━━━━━━━━━━"
ipset_data=$(ipset list allowed_users 2>/dev/null | sed -n '/Members:/,$p' | tail -n +2)
if [ -z "$ipset_data" ]; then
    echo "⚠️ <i>No active users found in the list.</i>"
else
    while read -r line; do
        [ -z "$line" ] && continue
        ip=$(echo "$line" | awk '{print $1}')
        timeout=$(echo "$line" | awk '{print $3}')
        bytes=$(echo "$line" | grep -oP 'bytes \K[0-9]+')
        [ -z "$bytes" ] && bytes=0
        if [ "$bytes" -lt 1048576 ]; then u_traffic="$(($bytes / 1024)) KB"
        elif [ "$bytes" -lt 1073741824 ]; then u_traffic="$(($bytes / 1048576)) MB"
        else u_traffic=$(awk 'BEGIN {printf "%.2f GB", '$bytes'/1073741824}'); fi
        isp=$(curl -s --connect-timeout 2 "http://ip-api.com/line/$ip?fields=isp" | head -n 1)
        [[ -z "$isp" || "$isp" == *"{"* ]] && isp="Unknown" || isp=$(echo "$isp" | cut -c1-25)

        echo "▪️ <code>$ip</code>"
        echo "   ├ 💾 $u_traffic | ⏱ ${timeout}s"
        echo "   └ 🏢 $isp"
        echo ""
    done <<< "$ipset_data"
fi
"""
        with open("/root/tg_report_temp.sh", "w") as f:
            f.write(bash_script)
        result = subprocess.getoutput("bash /root/tg_report_temp.sh")
        try: bot.edit_message_text(result, message.chat.id, loading_msg.message_id, parse_mode="HTML")
        except: bot.send_message(message.chat.id, result, parse_mode="HTML")

    elif "Add IP" in text:
        msg = bot.send_message(message.chat.id, "➕ Please send the IP address you want to ADD:")
        bot.register_next_step_handler(msg, process_add_ip)

    elif "Remove IP" in text:
        msg = bot.send_message(message.chat.id, "➖ Please send the IP address you want to REMOVE:")
        bot.register_next_step_handler(msg, process_remove_ip)

    elif "Ping Test" in text:
        msg = bot.send_message(message.chat.id, "🏓 Please send the IP address or domain you want to ping:")
        bot.register_next_step_handler(msg, process_ping_test)

    elif "Server Status" in text:
        loading_msg = bot.send_message(message.chat.id, "Fetching server resources... ⏳")
        ram_info = subprocess.getoutput("free -m | awk 'NR==2{printf \"Total: %sMB | Used: %sMB (%.2f%%)\", $2, $3, $3*100/$2 }'")
        disk_info = subprocess.getoutput("df -h / | awk 'NR==2{printf \"Total: %s | Used: %s (%s)\", $2, $3, $5}'")
        cpu_load = subprocess.getoutput("uptime | awk -F'load average:' '{ print $2 }' | xargs")

        status_text = f"📊 <b>Server Resource Status</b>\n━━━━━━━━━━━━━━━━━━━━\n🧠 <b>RAM Usage:</b>\n   └ <code>{ram_info}</code>\n\n💾 <b>Disk Usage (/):</b>\n   └ <code>{disk_info}</code>\n\n⚡️ <b>CPU Load Average:</b>\n   └ <code>{cpu_load}</code>"
        try: bot.edit_message_text(status_text, message.chat.id, loading_msg.message_id, parse_mode="HTML")
        except: bot.send_message(message.chat.id, status_text, parse_mode="HTML")

    elif "Active Ports" in text:
        loading_msg = bot.send_message(message.chat.id, "Scanning active ports... ⏳")
        raw_output = subprocess.getoutput("ss -tuln")
        lines = raw_output.strip().split('\n')
        res_text = "🌐 <b>Active Listening Ports</b>\n━━━━━━━━━━━━━━━━━━━━\n"
        ports_count = 0
        for line in lines[1:]: 
            parts = line.split()
            if len(parts) >= 5:
                proto = parts[0].upper()
                local_addr = parts[4]
                if ":" in local_addr:
                    ip_part, port_part = local_addr.rsplit(":", 1)
                else:
                    port_part = local_addr
                res_text += f"▪️ <b>{proto} Port:</b> <code>{port_part}</code> (Bind: {ip_part})\n"
                ports_count += 1
                if ports_count >= 20: break
        if ports_count == 0: res_text += "⚠️ <i>No active ports found.</i>"
        try: bot.edit_message_text(res_text, message.chat.id, loading_msg.message_id, parse_mode="HTML")
        except: bot.send_message(message.chat.id, res_text, parse_mode="HTML")

    elif "Clear Cache" in text:
        loading_msg = bot.send_message(message.chat.id, "🧹 Clearing server cache and temp files... ⏳")
        subprocess.getoutput("apt-get clean")
        subprocess.getoutput("journalctl --vacuum-time=3d")
        subprocess.getoutput("sync; echo 1 > /proc/sys/vm/drop_caches")
        res_text = "✅ <b>System Cache Cleared!</b>\n━━━━━━━━━━━━━━━━━━━━\n▪️ APT cache cleared.\n▪️ Old journal logs removed.\n▪️ RAM PageCache dropped."
        try: bot.edit_message_text(res_text, message.chat.id, loading_msg.message_id, parse_mode="HTML")
        except: bot.send_message(message.chat.id, res_text, parse_mode="HTML")

    elif "Packets" in text:
        loading_msg = bot.send_message(message.chat.id, "Fetching Packets status... ⏳")
        raw_output = subprocess.getoutput("iptables -t nat -L PREROUTING -n -v --line-numbers")
        lines = raw_output.strip().split('\n')
        final_text = "📦 <b>Packets Status (PREROUTING)</b>\n━━━━━━━━━━━━━━━━━━━━\n"
        for line in lines:
            line = line.strip()
            if not line or line.startswith("num"): continue
            if line.startswith("Chain"):
                final_text += f"📌 <i>{line}</i>\n\n"
                continue
            parts = line.split()
            if len(parts) >= 10:
                num, pkts, _bytes, target, prot, dest = parts[0], parts[1], parts[2], parts[3], parts[4], parts[9]
                extra = " ".join(parts[10:])
                if prot == "0": prot_name = "ALL"
                elif prot == "6": prot_name = "TCP"
                elif prot == "17": prot_name = "UDP"
                else: prot_name = prot.upper()
                final_text += f"🔹 <b>Rule #{num}</b> [<code>{target}</code>]\n   ├ ⚡️ Proto: {prot_name} | 📦 {pkts} Pkts | 💾 {_bytes}\n"
                if extra: final_text += f"   └ 🎯 <code>{extra}</code>\n"
                elif dest != "0.0.0.0/0": final_text += f"   └ 🌐 Dest: <code>{dest}</code>\n"
                else: final_text += f"   └ 🌐 Any -> Any\n"
                final_text += "\n"
        try: bot.edit_message_text(final_text, message.chat.id, loading_msg.message_id, parse_mode="HTML")
        except: bot.send_message(message.chat.id, final_text, parse_mode="HTML")

    elif "IP Reader" in text:
        loading_msg = bot.send_message(message.chat.id, "Reading IP Reader logs... ⏳")
        raw_output = subprocess.getoutput("journalctl -u adguard-monitor.service -n 30 --no-pager")
        lines = raw_output.strip().split('\n')
        final_text = "🔍 <b>AdGuard Monitor Logs</b>\n━━━━━━━━━━━━━━━━━━━━\n"
        has_logs = False
        for line in lines:
            if "Processed IP:" in line:
                has_logs = True
                ip = line.split("Processed IP:")[-1].strip()
                date_time = " ".join(line.split()[:3])
                final_text += f"⏱ <code>{date_time}</code> 🟢 <code>{ip}</code>\n"
        if not has_logs: final_text += "⚠️ <i>No recent processed IPs found.</i>"
        try: bot.edit_message_text(final_text, message.chat.id, loading_msg.message_id, parse_mode="HTML")
        except: bot.send_message(message.chat.id, final_text, parse_mode="HTML")

    elif "Blacklist" in text:
        loading_msg = bot.send_message(message.chat.id, "Reading blacklist... ⏳")
        bash_script = """#!/bin/bash
count=$(ipset list blacklist 2>/dev/null | grep "Number of entries" | cut -d: -f2 | xargs)
if [ -z "$count" ] || [ "$count" = "0" ]; then
    echo "The blacklist is currently empty. 🟢"
else
    echo "🛑 <b>Blacklist (Blocked IPs: $count)</b>"
    echo "━━━━━━━━━━━━━━━━━━━━"
    ipset list blacklist | sed -n '/Members:/,$p' | tail -n +2 | while read -r line; do
        [ -z "$line" ] && continue
        ip=$(echo "$line" | awk '{print $1}')
        pkts=$(echo "$line" | grep -oP 'packets \K[0-9]+')
        bytes=$(echo "$line" | grep -oP 'bytes \K[0-9]+')
        [ -z "$pkts" ] && pkts=0
        [ -z "$bytes" ] && bytes=0
        if [ "$bytes" -lt 1024 ]; then vol="${bytes} B"
        elif [ "$bytes" -lt 1048576 ]; then vol="$((bytes/1024)) KB"
        else vol="$((bytes/1048576)) MB"; fi
        bl_isp=$(curl -s --connect-timeout 2 "http://ip-api.com/line/$ip?fields=isp" | head -n 1)
        if [ -z "$bl_isp" ] || echo "$bl_isp" | grep -q "{"; then
            bl_isp="Unknown"
        else
            bl_isp=$(echo "$bl_isp" | cut -c1-25)
        fi
        echo "▪️ <code>$ip</code>"
        echo "   ├ 📦 $pkts Pkts | 💾 $vol"
        echo "   └ 🏢 $bl_isp"
        echo ""
    done
fi
"""
        with open("/root/tg_bl_temp.sh", "w") as f: f.write(bash_script)
        result = subprocess.getoutput("bash /root/tg_bl_temp.sh")
        try: bot.edit_message_text(result, message.chat.id, loading_msg.message_id, parse_mode="HTML")
        except: bot.send_message(message.chat.id, result, parse_mode="HTML")

    elif "Bandwidth" in text:
        loading_msg = bot.send_message(message.chat.id, "Fetching bandwidth usage... ⏳")
        raw_output = subprocess.getoutput("echo '' | bash /root/traffic.sh | sed -r 's/\\x1B\\[[0-9;]*[mK]//g'")
        y_dl = y_ul = y_tot = t_dl = t_ul = t_tot = m_rx = m_tx = m_left = m_days = m_extra = "-"
        for line in raw_output.split('\n'):
            line = line.strip()
            if line.startswith("yesterday"):
                parts = line.split()
                if len(parts) >= 4: y_dl, y_ul, y_tot = parts[1], parts[2], parts[3]
            elif line.startswith("today"):
                parts = line.split()
                if len(parts) >= 4: t_dl, t_ul, t_tot = parts[1], parts[2], parts[3]
            elif "Download (RX):" in line: m_rx = line.split("Download (RX):")[-1].strip()
            elif "Upload (TX):" in line: m_tx = line.split("Upload (TX):")[-1].strip()
            elif "Traffic Remaining:" in line: m_left = line.split("Traffic Remaining:")[-1].strip()
            elif line.startswith("(Base Left:"): m_extra = line.strip()
            elif "Days Remaining:" in line: m_days = line.split("Days Remaining:")[-1].strip()

        final_text = "📊 <b>Server Traffic Usage Report</b>\n━━━━━━━━━━━━━━━━━━━━\n"
        final_text += f"📅 <b>Yesterday:</b>\n   ├ 📥 Download: <code>{y_dl}</code>\n   ├ 📤 Upload: <code>{y_ul}</code>\n   └ 🔄 Total: <code>{y_tot}</code>\n\n"
        final_text += f"📅 <b>Today:</b>\n   ├ 📥 Download: <code>{t_dl}</code>\n   ├ 📤 Upload: <code>{t_ul}</code>\n   └ 🔄 Total: <code>{t_tot}</code>\n\n"
        final_text += f"📊 <b>General Status:</b>\n   ├ 📉 Monthly Usage: <code>{m_rx} (DL) | {m_tx} (UL)</code>\n   ├ 🔋 Remaining Traffic: <code>{m_left}</code>\n"
        if m_extra != "-": final_text += f"   ├ 🎁 <i>{m_extra}</i>\n"
        final_text += f"   └ ⏳ Days Remaining: <code>{m_days}</code>"

        ikm = InlineKeyboardMarkup(row_width=2)
        ikm.add(
            InlineKeyboardButton("1️⃣ Add/Reduce Extra", callback_data="bw_1"),
            InlineKeyboardButton("2️⃣ Set Base GB", callback_data="bw_2"),
            InlineKeyboardButton("3️⃣ Set Expiry Date", callback_data="bw_3"),
            InlineKeyboardButton("4️⃣ Reset Extra", callback_data="bw_4"),
            InlineKeyboardButton("5️⃣ Reset Monthly", callback_data="bw_5"),
            InlineKeyboardButton("6️⃣ Sync Offset", callback_data="bw_6"),
            InlineKeyboardButton("7️⃣ Carry-Over", callback_data="bw_7"),
            InlineKeyboardButton("8️⃣ Calc Upload", callback_data="bw_8")
        )
        try: bot.edit_message_text(final_text, message.chat.id, loading_msg.message_id, parse_mode="HTML", reply_markup=ikm)
        except: bot.send_message(message.chat.id, final_text, parse_mode="HTML", reply_markup=ikm)

    elif "Geo IP Lookup" in text:
        msg = bot.send_message(message.chat.id, "🌐 Please send the IP address you want to check:")
        bot.register_next_step_handler(msg, process_ip_lookup)


@bot.callback_query_handler(func=lambda call: call.data.startswith('bw_'))
def handle_bandwidth_actions(call):
    if not is_admin(call.message): return
    action = call.data
    bot.answer_callback_query(call.id, f"You clicked on option: {action.replace('bw_', '')}\n(Need to link with CLI arguments in script)")
    bot.send_message(call.message.chat.id, f"⚙️ To execute option {action.replace('bw_', '')}, the `traffic.sh` script must support command-line arguments.")

def process_add_ip(message):
    if not is_admin(message): return
    target_ip = message.text.strip()
    try: bot.delete_message(message.chat.id, message.message_id)
    except: pass
    result = subprocess.getoutput(f"ipset add allowed_users {target_ip} 2>&1")
    if not result: res_text = f"✅ IP <code>{target_ip}</code> successfully <b>added</b> to allowed users."
    else: res_text = f"❌ Failed to add IP <code>{target_ip}</code>.\nError: <code>{result}</code>"
    bot.send_message(message.chat.id, res_text, parse_mode="HTML")

def process_remove_ip(message):
    if not is_admin(message): return
    target_ip = message.text.strip()
    try: bot.delete_message(message.chat.id, message.message_id)
    except: pass
    result = subprocess.getoutput(f"ipset del allowed_users {target_ip} 2>&1")
    if not result: res_text = f"✅ IP <code>{target_ip}</code> successfully <b>removed</b> from allowed users."
    else: res_text = f"❌ Failed to remove IP <code>{target_ip}</code>.\nError: <code>{result}</code>"
    bot.send_message(message.chat.id, res_text, parse_mode="HTML")

def process_ping_test(message):
    if not is_admin(message): return
    target = message.text.strip()
    try: bot.delete_message(message.chat.id, message.message_id)
    except: pass
    loading_msg = bot.send_message(message.chat.id, f"🏓 Pinging <code>{target}</code>... ⏳", parse_mode="HTML")
    ping_output = subprocess.getoutput(f"ping -c 4 -W 3 {target} 2>&1")
    ping_result = f"🏓 <b>Ping Test Report</b>\n━━━━━━━━━━━━━━━━━━━━\n▪️ Target: <code>{target}</code>\n\n"
    if "bytes from" in ping_output:
        lines = ping_output.strip().split('\n')
        summary = lines[-1] if "rtt" in lines[-1] or "min/avg" in lines[-1] or "packet loss" in lines[-2] else ""
        loss_line = lines[-2] if "packet loss" in lines[-2] else lines[-3] if len(lines) > 2 else ""
        ping_result += f"✅ <b>Status:</b> Success\n📦 <code>{loss_line}</code>\n"
        if summary: ping_result += f"⏱ <code>{summary}</code>\n"
    else:
        ping_result += f"❌ <b>Status:</b> Failed / Timeout\n<pre>{ping_output[:300]}</pre>"
    try: bot.edit_message_text(ping_result, message.chat.id, loading_msg.message_id, parse_mode="HTML")
    except: bot.send_message(message.chat.id, ping_result, parse_mode="HTML")

def process_ip_lookup(message):
    if not is_admin(message): return
    target_ip = message.text.strip()
    try: bot.delete_message(message.chat.id, message.message_id)
    except: pass
    loading_msg = bot.send_message(message.chat.id, f"🔍 Checking IP: <code>{target_ip}</code>... ⏳", parse_mode="HTML")
    try:
        url = f"http://ip-api.com/json/{target_ip}?fields=status,message,country,countryCode,regionName,city,isp,org,as"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json.loads(response.read().decode())
        if data.get("status") == "success":
            country, code, region, city, isp, org = data.get("country", "Unknown"), data.get("countryCode", ""), data.get("regionName", "Unknown"), data.get("city", "Unknown"), data.get("isp", "Unknown"), data.get("org", "Unknown")
            result_text = f"🌍 <b>IP Information Report</b>\n━━━━━━━━━━━━━━━━━━━━\n▪️ IP: <code>{target_ip}</code>\n▪️ Country: <b>{country} ({code})</b>\n▪️ Region/State: <code>{region}</code>\n▪️ City: <code>{city}</code> 🏙\n▪️ ISP: <code>{isp}</code> 🏢\n▪️ Organization: <code>{org}</code>"
        else:
            result_text = f"❌ Failed to lookup IP: <code>{target_ip}</code>\nReason: {data.get('message', 'Invalid IP')}"
    except Exception as e:
        result_text = f"❌ Error connecting to IP lookup service: {str(e)}"
    try: bot.edit_message_text(result_text, message.chat.id, loading_msg.message_id, parse_mode="HTML")
    except: bot.send_message(message.chat.id, result_text, parse_mode="HTML")

def watch_new_ips():
    known_ips = set()
    initial_data = subprocess.getoutput("ipset list allowed_users 2>/dev/null | sed -n '/Members:/,$p' | tail -n +2")
    for line in initial_data.split('\n'):
        if line.strip():
            known_ips.add(line.strip().split()[0])
    while True:
        try:
            time.sleep(10)
            current_data = subprocess.getoutput("ipset list allowed_users 2>/dev/null | sed -n '/Members:/,$p' | tail -n +2")
            current_ips = set()
            for line in current_data.split('\n'):
                line = line.strip()
                if line: current_ips.add(line.split()[0])
            new_ips = current_ips - known_ips
            for new_ip in new_ips:
                try:
                    url = f"http://ip-api.com/json/{new_ip}?fields=status,country,city,isp"
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=3) as resp:
                        geo = json.loads(resp.read().decode())
                        country, city, isp = geo.get("country", "Unknown"), geo.get("city", "Unknown"), geo.get("isp", "Unknown")
                except:
                    country, city, isp = "Unknown", "Unknown", "Unknown"
                notif_text = f"🚨 <b>New IP Connected to Server!</b>\n━━━━━━━━━━━━━━━━━━━━\n▪️ IP: <code>{new_ip}</code>\n▪️ Country: <b>{country}</b> ({city})\n▪️ ISP: <code>{isp}</code>"
                bot.send_message(ADMIN_ID, notif_text, parse_mode="HTML")
            known_ips = current_ips
        except Exception:
            pass

threading.Thread(target=watch_new_ips, daemon=True).start()

if __name__ == '__main__':
    bot.polling(none_stop=True, interval=0, timeout=20)
EOF

echo -e "${YELLOW}[3/4] Injecting Variables into Script...${RESET}"

sed -i "s/REPLACE_TOKEN/$BOT_TOKEN/g" /root/remote_bot.py
sed -i "s/REPLACE_ADMIN_ID/$ADMIN_ID/g" /root/remote_bot.py

PROXY_STRING="apihelper.proxy = {'https': 'socks5h://${PROXY_USER}:${PROXY_PASS}@127.0.0.1:${PROXY_PORT}'}"
sed -i "s|# PROXY_PLACEHOLDER|$PROXY_STRING|g" /root/remote_bot.py

echo -e "${YELLOW}[4/4] Creating and Starting Systemd Service...${RESET}"

cat << EOF > /etc/systemd/system/remote_bot.service
[Unit]
Description=Telegram Remote Server Bot
After=network.target

[Service]
User=root
WorkingDirectory=/root
ExecStart=/usr/bin/python3 /root/remote_bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable remote_bot.service
systemctl restart remote_bot.service

echo -e "${GREEN}====================================================${RESET}"
echo -e "${GREEN} ✅ Installation Completed Successfully!${RESET}"
echo -e "${GREEN} 🤖 Your bot is now running in the background.${RESET}"
echo -e "${GREEN} 💡 To check bot logs, run: ${YELLOW}journalctl -u remote_bot.service -f${RESET}"
echo -e "${GREEN}====================================================${RESET}"