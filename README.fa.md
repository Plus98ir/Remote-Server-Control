<h1 align="center">Remote Server Control</h1>

<p align="center"><a href="https://hits.sh/github.com/Plus98ir/Remote-Server-Control/"><img src="https://hits.sh/github.com/Plus98ir/Remote-Server-Control.svg?style=for-the-badge&label=views&color=2563eb" alt="Views"></a> <a href="https://corenetbase.com/#support"><img src="https://img.shields.io/badge/support-buy%20me%20a%20coffee-e11d2a?style=for-the-badge&logo=buymeacoffee&logoColor=white" alt="Support"></a></p>

<details>
<summary><b>☕ Support · حمایت</b> — USDT (TRC20) / TRX</summary>
<br>
<p align="center"><img src="https://raw.githubusercontent.com/Plus98ir/.github/main/tron-qr.png" width="200" alt="TRON address QR"></p>

```
TA53aFyGNfSAcrCaJi9QmA9x5W47nPJcf7
```

> [!WARNING]
> **TRON network only.** Sending from ERC20 / BEP20 will lose the funds.<br>
> **فقط شبکه‌ی TRON.** ارسال از ERC20 یا BEP20 پول را از بین می‌برد.

</details>

<div align="center">

[<img src="https://flagcdn.com/w40/us.png" width="20" alt=""> &nbsp;**English**](README.md) &nbsp;&nbsp;|&nbsp;&nbsp; [<img src="https://flagcdn.com/w40/ir.png" width="20" alt=""> &nbsp;**فارسی**](README.fa.md)

</div>

<div dir="rtl">

یک ربات تلگرام سبک برای **نظارت و مدیریت سرور لینوکس** از روی گوشی: منابع به‌صورت زنده، سرویس‌های systemd، پورت‌های باز، ابزار پینگ و Geo IP و هشدارهای خودکار. اگر [DNSGuard](#dnsguard-فقط-خواندنی) روی همان سرور باشد، ربات کاربرها، کوئری‌ها و ترافیک رله‌ی آن را هم نشان می‌دهد، **فقط به‌صورت خواندنی**.

- **بدون وابستگی**: فقط کتابخانه‌ی استاندارد Python، بدون `pip`. روی سرورهایی که PyPI کند یا بسته است به کار می‌آید.
- **سبک**: حدود ۱۵ مگابایت رم. سقف سرویس ۸۰ مگابایت است.
- **کار پشت فیلترینگ**: پروکسی SOCKS5 اختیاری برای API تلگرام، با DNS از راه دور.
- **خصوصی**: فقط به آیدی ادمین‌هایی که تعیین می‌کنید جواب می‌دهد، آن هم فقط در چت خصوصی.

## امکانات

| منو | چه چیزی می‌گیرید |
|---|---|
| 📊 **وضعیت** | نوار CPU، رم، swap و دیسک، بار سیستم، سرعت و مجموع ترافیک شبکه، پرمصرف‌ترین پروسه‌ها از نظر حافظه |
| ⚙️ **سرویس‌ها** | وضعیت، مدت روشن بودن، حافظه و تعداد ری‌استارت هر سرویس تحت نظر. آخرین خطوط لاگ را نشان می‌دهد و بعد از تأیید شما سرویس را ری‌استارت می‌کند. |
| 🛡 **DNSGuard** | سلامت، کاربرها، توکن‌های فعال، IPهای ثبت‌شده و فایروال، کوئری‌های امروز و یک ساعت اخیر، ترافیک رله (امروز و این ماه)، کاربران پرمصرف، توکن‌های رو به انقضا، درخواست‌های دامنه‌ی در انتظار |
| 🌐 **شبکه** | پورت‌های در حال گوش دادن با پروسه و آدرس bind، اتصال‌های TCP برقرار |
| 🏓 **پینگ** / 🌍 **Geo IP** | خلاصه‌ی پینگ (loss، میانگین/کمینه/بیشینه، jitter) و کشور / ISP / AS هر IP یا هاست |
| 🔔 **هشدارها** | آستانه‌ها، مشکلات باز، بی‌صدا کردن برای ۱ یا ۸ ساعت، ارسال فوری گزارش |
| 🧹 **پاک‌سازی** | کش APT، ژورنال قدیمی‌تر از ۳ روز و page cache رم، بعد از تأیید شما |

### هشدارهای خودکار

هر ۶۰ ثانیه بررسی می‌شود. یک مشکل باید در چند بررسی پشت‌سرهم دیده شود تا هشدار بدهد، پس جهش‌های کوتاه پیام الکی نمی‌سازند. تا وقتی مشکل ادامه دارد هر ساعت یادآوری می‌گیرید و وقتی برطرف شد یک پیام ✅.

- رم یا دیسک ≥ ۹۰٪، بار سیستم > ۲ × تعداد هسته‌ها
- توقف یا خرابی یک سرویس تحت نظر
- جواب ندادن `/health` در DNSGuard
- ری‌استارت شدن سرور
- کاربر جدید یا درخواست دامنه‌ی جدید در DNSGuard
- **گزارش روزانه** در ساعتی که انتخاب می‌کنید (پیش‌فرض ۰۹:۰۰، به وقت منطقه‌ی شما)

## نصب

روی سرور با کاربر root اجرا کنید (Ubuntu / Debian یا هر توزیعی با systemd و Python ≥ 3.8):

</div>

```bash
bash <(curl -fsSL https://github.com/Plus98ir/Remote-Server-Control/releases/latest/download/install.sh)
```

<div dir="rtl">

نصب‌کننده این‌ها را می‌پرسد:

۱. **توکن ربات**: با [@BotFather](https://t.me/BotFather) یک ربات بسازید. ربات جدید بسازید: دو برنامه که با یک توکن پیام می‌گیرند، پیام‌های هم را می‌دزدند.
۲. **آیدی ادمین(ها)**: آیدی عددی تلگرام شما ([@userinfobot](https://t.me/userinfobot) نشانش می‌دهد). چند آیدی را با کاما جدا کنید.
۳. **پروکسی SOCKS5** (اختیاری): `socks5://user:pass@127.0.0.1:1080`. اگر سرور مستقیم به تلگرام وصل می‌شود خالی بگذارید. اگر DNSGuard نصب باشد، پروکسی ربات آن به‌عنوان پیش‌فرض پیشنهاد می‌شود.
۴. **منطقه‌ی زمانی** و **ساعت گزارش روزانه**.
۵. **سرویس‌های تحت نظر**: سرویس‌های رایجی که در حال اجرا هستند خودکار پیدا می‌شوند (DNSGuard، Caddy، Nginx، x-ui، Xray، sing-box، Hysteria، Docker، دیتابیس‌ها، fail2ban و …).

بعد اتصال به تلگرام را تست می‌کند، سرویس systemd را نصب و اجرا می‌کند. به ربات خودتان `/start` بفرستید.

### نصب بدون سؤال

</div>

```bash
RSC_TOKEN='123456:ABC...' bash install.sh --admin 11111111 --proxy none \
    --tz Asia/Tehran --report 09:00 --services nginx,docker --yes
```

<div dir="rtl">

دادن توکن از طریق `RSC_TOKEN` باعث می‌شود در لیست پروسه‌ها دیده نشود.

### به‌روزرسانی، تنظیم دوباره، حذف

</div>

```bash
bash install.sh                 # update the code, keep the settings
bash install.sh --reconfigure   # ask for every setting again
bash install.sh --uninstall     # remove service and code, keep settings
bash install.sh --uninstall --purge   # remove settings and state too
```

<div dir="rtl">

## تنظیمات

`/etc/remote-server-control/config.json` (با مجوز `600`، چون توکن داخلش است). بعد از ویرایش، سرویس را ری‌استارت کنید: `systemctl restart remote-server-control`.

</div>

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

<div dir="rtl">

هر کلیدی را می‌توانید حذف کنید؛ مقدار پیش‌فرض بالا استفاده می‌شود.

| مسیر | کاربرد |
|---|---|
| `/opt/remote-server-control/rsc/` | کد |
| `/etc/remote-server-control/config.json` | تنظیمات |
| `/var/lib/remote-server-control/state.json` | وضعیت هشدارها (بی‌صدا، آخرین گزارش، تشخیص ری‌استارت) |
| `journalctl -u remote-server-control -f` | لاگ‌ها |

## DNSGuard (فقط خواندنی)

وقتی دیتابیس DNSGuard وجود داشته باشد، منوی 🛡 و هشدارهای DNSGuard خودکار فعال می‌شوند. ربات **هیچ‌وقت DNSGuard را تغییر نمی‌دهد**:

- دیتابیس SQLite با `mode=ro` باز می‌شود
- `/health` فقط یک درخواست GET روی localhost است
- مجموعه‌ی فایروال فقط فهرست می‌شود (`nft -j list set …`)
- `metrics-24h.json` فقط خوانده می‌شود

هر عدد جدا خوانده می‌شود. اگر یک آپدیت DNSGuard ساختار دیتابیسش را عوض کند، فقط همان خط `n/a` نشان می‌دهد و بقیه کار می‌کنند. بدون DNSGuard، این منو پنهان است و ربات یک مانیتور ساده‌ی سرور است.

## امنیت

- پیام‌های هر کسی که در `admin_ids` نیست، و پیام‌های گروه‌ها، بدون جواب نادیده گرفته می‌شوند.
- ورودی پینگ و Geo IP باید IP یا اسم هاست معتبر باشد و دستورها بدون shell اجرا می‌شوند، پس هیچ متنی که در تلگرام تایپ شود نمی‌تواند دستور تزریق کند.
- ری‌استارت و پاک‌سازی قبل از اجرا تأیید می‌خواهند.
- سرویس با root اجرا می‌شود، چون به `systemctl`، `journalctl` و `nft` نیاز دارد. حساب تلگرامتان را امن نگه دارید (تأیید دومرحله‌ای).

## توسعه

</div>

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

<div dir="rtl">

اجرای تست‌ها روی لینوکس: `python3 -m unittest discover -s tests -v`

## تغییرات

### v2.0.0
- بازنویسی به‌صورت یک پکیج Python که فقط از کتابخانه‌ی استاندارد استفاده می‌کند، با نصب‌کننده‌ی جدید (به‌روزرسانی، تنظیم دوباره، حذف، حالت بدون سؤال).
- جدید: نمای سرویس‌ها با لاگ و ری‌استارت، هشدار خودکار، گزارش روزانه، بی‌صدا کردن، داشبورد فقط‌خواندنی DNSGuard، نمای شبکه، پاک‌سازی با نمایش اعداد قبل و بعد.
- پروکسی حالا اختیاری است و SOCKS5 با نام کاربری و رمز مستقیم پشتیبانی می‌شود.
- امنیت: ورودی‌ها بررسی می‌شوند، بدون دستور shell، فقط ادمین و فقط چت خصوصی.
- امکانات ipset / `traffic.sh` / مانیتور AdGuard نسخه‌ی ۱ حذف شد، چون به فایل‌هایی وابسته بودند که نصب‌کننده نمی‌ساخت.

### v1.0.0
- اولین نسخه: یک اسکریپت نصب که ربات pyTelegramBotAPI می‌ساخت.

</div>
