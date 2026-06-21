# Canary-File — Cyber Theft Detection & Alert System

A deception-based cybersecurity tool that places strategically crafted decoy files
in your directories. Any unauthorized access, copy, or move attempt triggers an
instant Telegram/Email alert with full evidence collection.

---

## Quick Start (Windows)

1. Install Python 3.11+ from python.org
2. Double-click `start.bat`
3. Open http://127.0.0.1:5000 in browser

## Quick Start (Manual)

```bash
pip install -r requirements.txt
python app.py
```

---

## Setup Guide

### Step 1 — Configure Telegram Bot (Recommended)

1. Open Telegram → search `@BotFather`
2. Send `/newbot` → follow prompts → copy Bot Token
3. Start a chat with your new bot
4. Get your Chat ID from `@userinfobot`
5. Paste both in Settings → Save

### Step 2 — Deploy Canary Files

1. Go to **Files** page
2. Enter filename (e.g. `passwords.txt`, `salary_data.csv`)
3. Click **Deploy →**
4. Files are created in the `canary_files/` folder

### Step 3 — Start Monitoring

1. Click **Start** in the top right corner
2. Status turns green → monitoring is live
3. Any file access triggers an alert

### Step 4 — Test It

1. Go to **Files** page
2. Click **Simulate** on any file
3. Choose event type → **Trigger →**
4. Check your Telegram for the alert
5. Check **Incidents** page for the log

---

## Project Structure

```
canary-file/
├── app.py                  # Flask app + all API routes
├── start.bat               # Windows one-click startup
├── requirements.txt
├── backend/
│   ├── database.py         # SQLite DB + queries
│   ├── generator.py        # Canary file content generator
│   ├── monitor.py          # Watchdog file system monitor
│   └── alerter.py          # Telegram + Email alert engine
├── frontend/
│   ├── templates/          # Jinja2 HTML pages
│   │   ├── dashboard.html
│   │   ├── files.html
│   │   ├── incidents.html
│   │   ├── settings.html
│   │   └── sidebar.html
│   └── static/
│       ├── css/main.css
│       └── js/main.js
├── canary_files/           # Deployed canary files stored here
├── data/
│   └── canary.db           # SQLite database
└── logs/
```

---

## Alert Example (Telegram)

```
CANARY FILE TRIGGERED 

Severity: HIGH

File: passwords.txt
Event: COPIED
Time: 2026-05-31 14:35:22

💻 Device: DESKTOP-PC01
👤 User: john.doe
🌐 IP: 192.168.1.50
🖥️ OS: Windows 11
⚙️ Process: explorer.exe

Destination: D:/USB/passwords.txt
```

---

## Tech Stack

| Component    | Technology              |
|-------------|-------------------------|
| Backend     | Python 3.9+, Flask      |
| Monitoring  | Watchdog library        |
| Database    | SQLite3                 |
| Alerts      | Telegram Bot API, SMTP  |
| Frontend    | HTML, CSS, JavaScript   |
| System Info | psutil, requests        |

---

## ⚠️ Important

This tool is designed for use on **your own systems only**.
Authorized use: personal computers, lab environments, college projects.

---

*Canary-File v1.0.0 — Deception-Based Cybersecurity*
