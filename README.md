## 📖 About The Project

**Remote Server Control** is a powerful Telegram bot designed to help you monitor, manage, and control your Linux server remotely. It provides a user-friendly interface directly inside Telegram to handle network traffic, monitor active users, and execute essential system commands without needing an SSH connection.

### ✨ Key Features

* **📊 Server Monitoring:** Get real-time updates on CPU load, RAM, and Disk usage.
* **👥 User & IP Management:** Quickly Add or Remove client IP addresses using `ipset` to grant or revoke access.
* **💾 Traffic & Bandwidth Reports:** Track daily/monthly upload and download data, check remaining traffic, and view port-specific usage (Port 80, 443).
* **🌐 Network Utilities:** Built-in tools to run Ping tests, perform Geo-IP lookups, and scan active listening server ports.
* **🚨 Real-Time Alerts:** Automatically notifies the admin whenever a new, unknown IP address connects to the server.
* **🧹 System Maintenance:** Clear system cache, APT cache, and old journal logs with a single click.
* **🛑 Security:** View blacklisted IPs and monitor blocked traffic packets.

What this script does:

Installs required packages (python3, pip, ipset, iptables, etc.)

Prompts for your Bot Token, Admin ID, and Proxy credentials

Generates the Python bot script automatically

Creates and starts a systemd background service to keep the bot running 24/7

---

## 🚀 Auto Install

You can install and configure the bot automatically with a single command. Just run the following command in your Linux terminal (run as root):

```bash
bash <(curl -fsSL https://github.com/Plus98ir/Remote-Server-Control/releases/latest/download/install.sh)
