import requests
import smtplib
import socket
import os
import platform
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from backend.database import get_setting


def get_public_ip():
    try:
        r = requests.get('https://api.ipify.org?format=json', timeout=4)
        return r.json().get('ip', 'Unknown')
    except Exception:
        return 'Unknown'


def get_system_info():
    return {
        'username': os.getenv('USERNAME') or os.getenv('USER') or 'Unknown',
        'device_name': socket.gethostname(),
        'os_info': f"{platform.system()} {platform.release()}",
        'public_ip': get_public_ip(),
    }


def send_telegram_alert(incident: dict) -> bool:
    token = get_setting('telegram_token')
    chat_id = get_setting('telegram_chat_id')

    if not token or not chat_id:
        return False

    severity = incident.get('severity', 'HIGH')
    emoji = '🔴' if severity == 'HIGH' else ('🟡' if severity == 'MEDIUM' else '🟢')

    msg = f"""🚨 *CANARY FILE TRIGGERED* 🚨

{emoji} *Severity:* `{severity}`

📄 *File:* `{incident.get('filename', 'Unknown')}`
⚡ *Event:* `{incident.get('event_type', 'Unknown')}`
🕐 *Time:* `{incident.get('timestamp', 'Unknown')}`

💻 *Device:* `{incident.get('device_name', 'Unknown')}`
👤 *User:* `{incident.get('username', 'Unknown')}`
🌐 *IP:* `{incident.get('public_ip', 'Unknown')}`
🖥️ *OS:* `{incident.get('os_info', 'Unknown')}`
⚙️ *Process:* `{incident.get('process_name', 'Unknown')}`

📍 *Destination:* `{incident.get('destination', 'N/A')}`

⚠️ _Canary-File Detection System | Unauthorized Access Detected_"""

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(url, json={
            'chat_id': chat_id,
            'text': msg,
            'parse_mode': 'Markdown'
        }, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"[AlertEngine] Telegram error: {e}")
        return False


def send_email_alert(incident: dict) -> bool:
    if get_setting('alert_email_enabled') != '1':
        return False

    smtp_host = get_setting('smtp_host')
    smtp_port = int(get_setting('smtp_port') or 587)
    smtp_user = get_setting('smtp_user')
    smtp_pass = get_setting('smtp_pass')
    alert_email = get_setting('alert_email')

    if not all([smtp_host, smtp_user, smtp_pass, alert_email]):
        return False

    severity = incident.get('severity', 'HIGH')

    html = f"""
    <html><body style="font-family:monospace;background:#0a0a0a;color:#00ff41;padding:20px;">
    <div style="border:1px solid #00ff41;padding:20px;max-width:600px;">
    <h2 style="color:#ff0040;">🚨 CANARY FILE TRIGGERED</h2>
    <table style="width:100%;border-collapse:collapse;">
    <tr><td style="padding:8px;color:#888;">File</td><td style="padding:8px;color:#00ff41;">{incident.get('filename')}</td></tr>
    <tr><td style="padding:8px;color:#888;">Event</td><td style="padding:8px;color:#ff9500;">{incident.get('event_type')}</td></tr>
    <tr><td style="padding:8px;color:#888;">Time</td><td style="padding:8px;">{incident.get('timestamp')}</td></tr>
    <tr><td style="padding:8px;color:#888;">Device</td><td style="padding:8px;">{incident.get('device_name')}</td></tr>
    <tr><td style="padding:8px;color:#888;">User</td><td style="padding:8px;">{incident.get('username')}</td></tr>
    <tr><td style="padding:8px;color:#888;">IP</td><td style="padding:8px;">{incident.get('public_ip')}</td></tr>
    <tr><td style="padding:8px;color:#888;">Severity</td><td style="padding:8px;color:#ff0040;font-weight:bold;">{severity}</td></tr>
    </table>
    </div></body></html>
    """

    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"[CANARY ALERT] {severity} - {incident.get('filename')} Triggered"
    msg['From'] = smtp_user
    msg['To'] = alert_email
    msg.attach(MIMEText(html, 'html'))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, alert_email, msg.as_string())
        return True
    except Exception as e:
        print(f"[AlertEngine] Email error: {e}")
        return False


def dispatch_alerts(incident: dict) -> dict:
    results = {}
    if get_setting('alert_telegram') == '1':
        results['telegram'] = send_telegram_alert(incident)
    if get_setting('alert_email_enabled') == '1':
        results['email'] = send_email_alert(incident)
    return results
