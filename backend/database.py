import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'canary.db')


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_conn()
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS canary_files (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            filename        TEXT NOT NULL,
            file_type       TEXT NOT NULL,
            file_path       TEXT NOT NULL,
            decoy_content   TEXT,
            custom_content  TEXT,
            monitoring_enabled INTEGER DEFAULT 1,
            created_at      TEXT NOT NULL,
            last_triggered  TEXT,
            trigger_count   INTEGER DEFAULT 0,
            open_count      INTEGER DEFAULT 0,
            modify_count    INTEGER DEFAULT 0,
            risk_label      TEXT DEFAULT 'HIGH',
            encryption_key  TEXT,
            is_encrypted    INTEGER DEFAULT 0
        )
    ''')

    # Safe column upgrades for existing DBs
    safe_cols = [
        ('canary_files', 'custom_content',  'TEXT'),
        ('canary_files', 'open_count',      'INTEGER DEFAULT 0'),
        ('canary_files', 'modify_count',    'INTEGER DEFAULT 0'),
        ('canary_files', 'encryption_key',  'TEXT'),
        ('canary_files', 'is_encrypted',    'INTEGER DEFAULT 0'),
        ('incidents',    'location',        'TEXT'),
    ]
    for tbl, col, defn in safe_cols:
        try:
            c.execute(f'ALTER TABLE {tbl} ADD COLUMN {col} {defn}')
        except Exception:
            pass

    c.execute('''
        CREATE TABLE IF NOT EXISTS incidents (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            canary_file_id  INTEGER,
            filename        TEXT NOT NULL,
            event_type      TEXT NOT NULL,
            timestamp       TEXT NOT NULL,
            username        TEXT,
            device_name     TEXT,
            public_ip       TEXT,
            os_info         TEXT,
            process_name    TEXT,
            destination     TEXT,
            severity        TEXT DEFAULT 'HIGH',
            alert_sent      INTEGER DEFAULT 0,
            snapshot_path   TEXT,
            location        TEXT,
            notes           TEXT,
            FOREIGN KEY(canary_file_id) REFERENCES canary_files(id)
        )
    ''')

    try:
        c.execute('ALTER TABLE incidents ADD COLUMN snapshot_path TEXT')
    except Exception:
        pass

    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    defaults = {
        'telegram_token':       '',
        'telegram_chat_id':     '',
        'smtp_host':            '',
        'smtp_port':            '587',
        'smtp_user':            '',
        'smtp_pass':            '',
        'alert_email':          '',
        'monitoring_active':    '0',
        'watch_directory':      '',
        'alert_telegram':       '1',
        'alert_email_enabled':  '0',
        'webcam_enabled':       '0',
        'twilio_sid':           '',
        'twilio_token':         '',
        'twilio_from':          '',
        'twilio_to':            '',
        'snapshot_url_base':    '',
        'whatsapp_phone':       '',
        'whatsapp_apikey':      '',
    }
    for k, v in defaults.items():
        c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (k, v))

    conn.commit()
    conn.close()


def get_setting(key):
    conn = get_conn()
    row  = conn.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
    conn.close()
    return row['value'] if row else None


def set_setting(key, value):
    conn = get_conn()
    conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
    conn.commit()
    conn.close()


def insert_incident(data: dict):
    conn = get_conn()
    c    = conn.cursor()
    c.execute('''
        INSERT INTO incidents
        (canary_file_id, filename, event_type, timestamp, username, device_name,
         public_ip, os_info, process_name, destination, severity, alert_sent, snapshot_path, location, notes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    ''', (
        data.get('canary_file_id'),
        data.get('filename'),
        data.get('event_type'),
        data.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        data.get('username'),
        data.get('device_name'),
        data.get('public_ip'),
        data.get('os_info'),
        data.get('process_name'),
        data.get('destination'),
        data.get('severity', 'HIGH'),
        data.get('alert_sent', 0),
        data.get('snapshot_path'),
        data.get('location'),
        data.get('notes'),
    ))
    incident_id = c.lastrowid

    if data.get('canary_file_id'):
        c.execute('''
            UPDATE canary_files
            SET trigger_count = trigger_count + 1,
                last_triggered = ?
            WHERE id = ?
        ''', (data.get('timestamp'), data.get('canary_file_id')))

    conn.commit()
    conn.close()
    return incident_id


def get_dashboard_stats():
    conn  = get_conn()
    stats = {}
    stats['total_alerts']       = conn.execute('SELECT COUNT(*) as c FROM incidents').fetchone()['c']
    stats['total_canary_files'] = conn.execute('SELECT COUNT(*) as c FROM canary_files').fetchone()['c']
    stats['active_monitors']    = conn.execute(
        'SELECT COUNT(*) as c FROM canary_files WHERE monitoring_enabled=1').fetchone()['c']
    stats['high_severity']      = conn.execute(
        "SELECT COUNT(*) as c FROM incidents WHERE severity='HIGH'").fetchone()['c']
    stats['recent_incidents']   = [dict(r) for r in conn.execute(
        'SELECT * FROM incidents ORDER BY timestamp DESC LIMIT 10').fetchall()]
    stats['canary_files']       = [dict(r) for r in conn.execute(
        'SELECT * FROM canary_files ORDER BY created_at DESC').fetchall()]

    rows = conn.execute(
        'SELECT event_type, COUNT(*) as cnt FROM incidents GROUP BY event_type'
    ).fetchall()
    stats['events_by_type'] = {r['event_type']: r['cnt'] for r in rows}

    rows = conn.execute('''
        SELECT DATE(timestamp) as day, COUNT(*) as cnt
        FROM incidents
        WHERE timestamp >= DATE('now', '-7 days')
        GROUP BY day ORDER BY day
    ''').fetchall()
    stats['daily_counts'] = [{'day': r['day'], 'cnt': r['cnt']} for r in rows]

    conn.close()
    return stats
