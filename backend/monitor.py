import os
import time
import threading
import platform
import hashlib
from datetime import datetime

from backend.database import get_conn, insert_incident, get_setting, set_setting
from backend.alerter import dispatch_alerts, get_system_info

# ── Globals ────────────────────────────────────────────────────────────
_monitor_thread = None
_stop_event     = threading.Event()
_snapshots      = {}
_debounce       = {}
_moved_away     = set()   # watchdog fired MOVED — suppress DELETED in poll
_rename_paths   = {}      # src_path -> timestamp (suppress MODIFIED after rename)

POLL_INTERVAL  = 0.8
DEBOUNCE_SECS  = 2
SUPPRESS_SECS  = 3        # seconds to suppress poll events after watchdog fires


# ── Snapshot ───────────────────────────────────────────────────────────
def _snap(path):
    try:
        st = os.stat(path)
        try:
            with open(path, 'rb') as f:
                data = f.read()
                content_hash = hashlib.md5(data).hexdigest() if data else ''
        except Exception:
            content_hash = ''
        return {
            'exists':       True,
            'mtime':        st.st_mtime,
            'atime':        st.st_atime,
            'size':         st.st_size,
            'inode':        st.st_ino,
            'content_hash': content_hash,
        }
    except (FileNotFoundError, PermissionError):
        return {'exists': False, 'mtime': 0, 'atime': 0,
                'size': 0, 'inode': 0, 'content_hash': ''}


def _reset_debounce_for(filepath):
    for k in [k for k in list(_debounce.keys()) if k.startswith(filepath + ':')]:
        del _debounce[k]


def suppress_file_events(filepath, duration=5):
    """Suppress events for a file for a specified duration (used when creating files via app)."""
    now = time.time()
    _rename_paths[filepath] = now + duration
    _moved_away.add(filepath)
    # Clear any pending debounce
    for event_type in ['MODIFIED', 'OPENED', 'COPIED', 'DELETED']:
        _debounce.pop(f"{filepath}:{event_type}", None)


def _should_fire(filepath, event_type):
    key = f"{filepath}:{event_type}"
    now = time.time()
    if now - _debounce.get(key, 0) < DEBOUNCE_SECS:
        return False
    _debounce[key] = now
    return True


# ── Load monitored files ───────────────────────────────────────────────
def _load_files():
    conn = get_conn()
    rows = conn.execute(
        'SELECT id, file_path, filename FROM canary_files WHERE monitoring_enabled=1'
    ).fetchall()
    
    # Clean up any filenames that got corrupted with temp patterns
    for row in rows:
        filename = row['filename']
        if any(pattern in filename for pattern in ['.sb-', '.tmp', '~', '.swp', '.bak', '.goutputstream']):
            # Try to extract original name
            # Pattern: originalname.ext.sb-xxxxx or similar
            parts = filename.split('.sb-')[0].split('.tmp')[0].split('.bak')[0].split('.swp')[0]
            if parts and parts != filename:
                print(f"[Canary] 🔧 Fixing corrupted filename: {filename} → {parts}")
                conn.execute('UPDATE canary_files SET filename=? WHERE id=?', (parts, row['id']))
    
    conn.commit()
    rows = conn.execute(
        'SELECT id, file_path, filename FROM canary_files WHERE monitoring_enabled=1'
    ).fetchall()
    conn.close()
    return {row['file_path']: {'id': row['id'], 'filename': row['filename']} for row in rows}


# ── Accurate geolocation ───────────────────────────────────────────────
def _get_location_info():
    """Get city, region, country from IP with multiple fallback services."""
    services = [
        {
            'url': 'http://ipapi.co/json/',
            'parser': lambda d: (d.get('ip', ''), f"{d.get('city', '')}, {d.get('region', '')}, {d.get('country_name', '')}".strip(', '))
        },
        {
            'url': 'http://ip-api.com/json/',
            'parser': lambda d: (d.get('query', ''), f"{d.get('city', '')}, {d.get('regionName', '')}, {d.get('country', '')}".strip(', '))
        },
        {
            'url': 'https://ipinfo.io/json',
            'parser': lambda d: (d.get('ip', ''), f"{d.get('city', '')}, {d.get('region', '')}, {d.get('country', '')}".strip(', '))
        },
        {
            'url': 'https://api.ipify.org?format=json',
            'parser': lambda d: (d.get('ip', ''), 'Location unavailable')
        }
    ]
    
    for service in services:
        try:
            import requests
            r = requests.get(service['url'], timeout=8)
            if r.status_code == 200:
                data = r.json()
                ip, location = service['parser'](data)
                if ip and ip != 'Unknown':
                    # Clean up location string
                    location = ', '.join(filter(None, [part.strip() for part in location.split(',') if part.strip()]))
                    if not location or location == '':
                        location = 'Unknown Location'
                    return ip, location
        except Exception as e:
            print(f"[Canary] Location service failed: {e}")
            continue
    
    return 'Unknown', 'Unknown Location'

# Cache location for session (don't hammer API on every event)
_location_cache = {'ip': None, 'location': None, 'ts': 0}

def _get_cached_location():
    global _location_cache
    if time.time() - _location_cache['ts'] > 120:  # refresh every 2 minutes for better accuracy
        ip, loc = _get_location_info()
        _location_cache = {'ip': ip, 'location': loc, 'ts': time.time()}
        print(f"[Canary] 🌍 Location updated: {ip} | {loc}")
    return _location_cache['ip'], _location_cache['location']


# ── Webcam capture ─────────────────────────────────────────────────────
def _capture_webcam(incident_id: int):
    snap_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'snapshots')
    os.makedirs(snap_dir, exist_ok=True)
    img_path = os.path.join(snap_dir, f"incident_{incident_id}_{int(time.time())}.jpg")

    # OpenCV
    try:
        import cv2
        cap = cv2.VideoCapture(0)
        if cap.isOpened():
            for _ in range(5): cap.read()
            ret, frame = cap.read()
            cap.release()
            if ret:
                cv2.imwrite(img_path, frame)
                print(f"[Canary] 📸 Snapshot: incident_{incident_id}")
                return img_path
    except Exception:
        pass

    # macOS fallback
    if platform.system() == 'Darwin':
        try:
            if os.system(f"imagesnap -q '{img_path}' 2>/dev/null") == 0 and os.path.exists(img_path):
                return img_path
        except Exception:
            pass

    return None


# ── WhatsApp ───────────────────────────────────────────────────────────
def send_whatsapp_callmebot(incident: dict) -> bool:
    try:
        import urllib.request, urllib.parse
        phone  = get_setting('whatsapp_phone')
        apikey = get_setting('whatsapp_apikey')
        if not phone or not apikey:
            return False
        msg = (
            f"🚨 CANARY ALERT\n"
            f"File: {incident.get('filename')}\n"
            f"Event: {incident.get('event_type')}\n"
            f"Severity: {incident.get('severity')}\n"
            f"User: {incident.get('username')}\n"
            f"Device: {incident.get('device_name')}\n"
            f"Location: {incident.get('location', 'Unknown')}\n"
            f"IP: {incident.get('public_ip')}\n"
            f"Time: {incident.get('timestamp')}"
        )
        url = (f"https://api.callmebot.com/whatsapp.php"
               f"?phone={phone}&text={urllib.parse.quote(msg)}&apikey={apikey}")
        with urllib.request.urlopen(urllib.request.Request(url), timeout=10) as resp:
            body = resp.read().decode()
            ok = 'Message Sent' in body or resp.status == 200
            print(f"[Canary] 📱 CallMeBot {'✓' if ok else 'failed: ' + body[:80]}")
            return ok
    except Exception as e:
        print(f"[Canary] WhatsApp error: {e}")
        return False


def send_whatsapp_twilio(incident: dict, snapshot_path=None) -> bool:
    try:
        from twilio.rest import Client
        sid, token = get_setting('twilio_sid'), get_setting('twilio_token')
        from_num, to_num = get_setting('twilio_from'), get_setting('twilio_to')
        if not all([sid, token, from_num, to_num]):
            return False
        client = Client(sid, token)
        msg = (
            f"🚨 *CANARY FILE TRIGGERED*\n\n"
            f"📄 File: {incident.get('filename')}\n"
            f"⚡ Event: {incident.get('event_type')}\n"
            f"🕐 Time: {incident.get('timestamp')}\n"
            f"💻 Device: {incident.get('device_name')}\n"
            f"👤 User: {incident.get('username')}\n"
            f"📍 Location: {incident.get('location', 'Unknown')}\n"
            f"🌐 IP: {incident.get('public_ip')}\n"
            f"🔴 Severity: {incident.get('severity')}"
        )
        kwargs = {'from_': from_num, 'to': to_num, 'body': msg}
        base_url = get_setting('snapshot_url_base')
        if snapshot_path and base_url:
            kwargs['media_url'] = [f"{base_url}/snapshots/{os.path.basename(snapshot_path)}"]
        client.messages.create(**kwargs)
        print("[Canary] 📱 Twilio WhatsApp ✓")
        return True
    except Exception as e:
        print(f"[Canary] Twilio error: {e}")
        return False


# ── Bump counters ──────────────────────────────────────────────────────
def _bump_stat(filepath, key):
    try:
        conn = get_conn()
        conn.execute(f'UPDATE canary_files SET {key}=COALESCE({key},0)+1 WHERE file_path=?', (filepath,))
        conn.commit()
        conn.close()
    except Exception:
        pass


def _proc(filepath):
    try:
        import psutil
        for p in psutil.process_iter(['name', 'open_files']):
            try:
                for f in (p.info['open_files'] or []):
                    if os.path.abspath(f.path) == os.path.abspath(filepath):
                        return p.info['name']
            except Exception:
                pass
    except Exception:
        pass
    return 'Finder' if platform.system() == 'Darwin' else 'Unknown'


# ── Fire incident ──────────────────────────────────────────────────────
def _fire(event_type, filepath, info, dest=None):
    # Skip webcam for CREATED events or when just deploying files
    if event_type == 'CREATED':
        return
        
    if not _should_fire(filepath, event_type):
        return

    sys_info         = get_system_info()
    pub_ip, location = _get_cached_location()
    timestamp        = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    severity         = 'HIGH' if event_type in (
        'OPENED', 'COPIED', 'DELETED', 'MOVED', 'RENAMED', 'USB_TRANSFER'
    ) else 'MEDIUM'

    if event_type == 'OPENED':
        _bump_stat(filepath, 'open_count')
    elif event_type == 'MODIFIED':
        _bump_stat(filepath, 'modify_count')

    incident = {
        'canary_file_id': info['id'],
        'filename':       info['filename'],
        'event_type':     event_type,
        'timestamp':      timestamp,
        'username':       sys_info['username'],
        'device_name':    sys_info['device_name'],
        'public_ip':      pub_ip,
        'location':       location,
        'os_info':        sys_info['os_info'],
        'process_name':   _proc(filepath),
        'destination':    dest or filepath,
        'severity':       severity,
        'alert_sent':     0,
    }

    iid = insert_incident(incident)
    print(f"[Canary] ⚡ {event_type} — {info['filename']} (#{iid}) | {location}")

    def _alert():
        # Webcam for file access events (not creation)
        snapshot_path = None
        if get_setting('webcam_enabled') == '1':
            snapshot_path = _capture_webcam(iid)
            if snapshot_path:
                c = get_conn()
                c.execute('UPDATE incidents SET snapshot_path=? WHERE id=?', (snapshot_path, iid))
                c.commit()
                c.close()

        # Telegram + Email
        res = dispatch_alerts(incident)

        # WhatsApp
        wa_ok = False
        if get_setting('whatsapp_apikey') and get_setting('whatsapp_phone'):
            wa_ok = send_whatsapp_callmebot(incident)
        elif get_setting('twilio_sid') and get_setting('twilio_token'):
            wa_ok = send_whatsapp_twilio(incident, snapshot_path)
        res['whatsapp'] = wa_ok

        if any(res.values()):
            c = get_conn()
            c.execute('UPDATE incidents SET alert_sent=1 WHERE id=?', (iid,))
            c.commit()
            c.close()

    threading.Thread(target=_alert, daemon=True).start()


# ── Poll loop ──────────────────────────────────────────────────────────
def _poll_loop():
    global _snapshots
    print("[Canary] 🟢 Poll loop started")

    for fp in _load_files():
        _snapshots[fp] = _snap(fp)

    while not _stop_event.is_set():
        files = _load_files()
        now   = time.time()

        for fp, info in files.items():
            prev = _snapshots.get(fp)
            curr = _snap(fp)

            if prev is None:
                # First time seeing this file - just record snapshot, don't fire event
                _snapshots[fp] = curr
                continue

            # Skip if watchdog recently handled this path (rename/move)
            # Also check if any path variation is in moved_away set
            abs_fp = os.path.abspath(fp)
            if (now - _rename_paths.get(fp, 0) < SUPPRESS_SECS or
                    now - _rename_paths.get(abs_fp, 0) < SUPPRESS_SECS or
                    fp in _moved_away or
                    abs_fp in _moved_away):
                _snapshots[fp] = curr
                # Clean up moved_away after suppress period
                if now - _rename_paths.get(fp, 0) >= SUPPRESS_SECS:
                    _moved_away.discard(fp)
                    _moved_away.discard(abs_fp)
                continue

            # ── DELETED ──────────────────────────────────────────────
            if prev['exists'] and not curr['exists']:
                _snapshots[fp] = curr
                _fire('DELETED', fp, info)
                _reset_debounce_for(fp)
                continue

            # ── RESTORED ─────────────────────────────────────────────
            if not prev['exists'] and curr['exists']:
                _snapshots[fp] = curr
                _reset_debounce_for(fp)
                _fire('COPIED', fp, info)
                continue

            if not curr['exists']:
                continue

            # ── MODIFIED — content hash changed ──────────────────────
            if (curr['content_hash'] and prev.get('content_hash') and
                    curr['content_hash'] != prev['content_hash'] and
                    curr['content_hash'] != ''):
                _snapshots[fp] = curr
                _fire('MODIFIED', fp, info)
                continue

            # ── OPENED — atime changed, content same ─────────────────
            if (curr['exists'] and prev.get('exists') and 
                    curr['atime'] != prev.get('atime', 0) and
                    curr['content_hash'] == prev.get('content_hash') and
                    curr['atime'] > prev.get('atime', 0) + 1):  # Significant time difference
                _snapshots[fp]['atime'] = curr['atime']
                _fire('OPENED', fp, info)
                continue

        for fp in list(_snapshots.keys()):
            if fp not in files:
                del _snapshots[fp]

        _stop_event.wait(POLL_INTERVAL)

    print("[Canary] 🔴 Poll loop stopped")


# ── Watchdog — accurate RENAMED vs MOVED vs COPIED ────────────────────
_observer = None

def _start_watchdog(watch_dir):
    global _observer
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        class CanaryHandler(FileSystemEventHandler):

            def on_moved(self, event):
                if event.is_directory:
                    return
                files = _load_files()
                src   = os.path.abspath(event.src_path)
                dst   = os.path.abspath(event.dest_path)
                
                src_base = os.path.basename(src)
                dst_base = os.path.basename(dst)

                for fp, info in files.items():
                    abs_fp = os.path.abspath(fp)

                    # ── CASE 1: Temp file moved TO canary path (editor save) ──
                    if dst == abs_fp and any(pattern in src_base for pattern in 
                        ['.sb-', '.tmp', '~', '.swp', '.bak', '.goutputstream']):
                        
                        # This is MODIFICATION - suppress other events and fire MODIFIED
                        now = time.time()
                        _rename_paths[fp]  = now
                        _rename_paths[dst] = now
                        _moved_away.add(fp)
                        
                        # Clear debounce for this file
                        for event_type in ['MODIFIED', 'OPENED', 'COPIED', 'DELETED']:
                            _debounce.pop(f"{fp}:{event_type}", None)
                        
                        _fire('MODIFIED', fp, info)
                        _snapshots[fp] = _snap(fp)
                        return

                    # ── CASE 2: Canary file moved to temp location (editor start) ──
                    if src == abs_fp and any(pattern in dst_base for pattern in 
                        ['.sb-', '.tmp', '~', '.swp', '.bak', '.goutputstream']):
                        
                        # Editor workflow - suppress but don't fire event yet
                        now = time.time()
                        _rename_paths[fp]  = now
                        _rename_paths[src] = now
                        _rename_paths[dst] = now
                        _moved_away.add(fp)
                        return

                    # ── CASE 3: Normal rename/move ──
                    if src == abs_fp:
                        # Skip temp files
                        if any(pattern in dst_base for pattern in 
                            ['.sb-', '.tmp', '~', '.swp', '.bak', '.goutputstream']):
                            return
                        
                        src_dir = os.path.dirname(src)
                        dst_dir = os.path.dirname(dst)
                        evt = 'RENAMED' if src_dir == dst_dir else 'MOVED'

                        now = time.time()
                        _moved_away.add(fp)
                        _moved_away.add(src)
                        _moved_away.add(dst)
                        _rename_paths[fp]  = now
                        _rename_paths[src] = now
                        _rename_paths[dst] = now
                        
                        for event_type in ['MODIFIED', 'OPENED', 'COPIED', 'DELETED']:
                            _debounce.pop(f"{fp}:{event_type}", None)
                            _debounce.pop(f"{src}:{event_type}", None)
                            _debounce.pop(f"{dst}:{event_type}", None)

                        _fire(evt, fp, info, dest=dst)
                        _update_file_path(info['id'], dst, os.path.basename(dst))
                        if fp in _snapshots:
                            _snapshots[dst] = _snap(dst)
                            del _snapshots[fp]
                        return

                    # ── CASE 4: Copy operation ──
                    if dst == abs_fp:
                        if not any(pattern in src_base for pattern in 
                            ['.sb-', '.tmp', '~', '.swp', '.bak', '.goutputstream']):
                            _fire('COPIED', fp, info)
                            _snapshots[fp] = _snap(fp)
                        return

            def on_modified(self, event):
                """macOS FSEvents: metadata-only change = file was opened."""
                if event.is_directory:
                    return
                files    = _load_files()
                abs_path = os.path.abspath(event.src_path)
                now      = time.time()

                for fp, info in files.items():
                    if os.path.abspath(fp) != abs_path:
                        continue
                    # Skip if this path was recently renamed/moved
                    # Check all possible path variations
                    if (now - _rename_paths.get(fp, 0) < SUPPRESS_SECS or
                            now - _rename_paths.get(abs_path, 0) < SUPPRESS_SECS or
                            fp in _moved_away or
                            abs_path in _moved_away):
                        return
                    
                    curr = _snap(fp)
                    prev = _snapshots.get(fp)
                    
                    # No previous snapshot, create one
                    if prev is None:
                        _snapshots[fp] = curr
                        return
                    
                    # mtime/size/hash unchanged = metadata only = OPENED
                    if (prev.get('mtime') == curr['mtime'] and
                            prev.get('size') == curr['size'] and
                            prev.get('content_hash') == curr['content_hash']):
                        _fire('OPENED', fp, info)
                    # Content changed = MODIFIED — let poll loop handle it
                    return

        _observer = Observer()
        _observer.schedule(CanaryHandler(), watch_dir, recursive=True)
        _observer.start()
        print(f"[Canary] 👁  Watchdog on: {watch_dir}")
    except Exception as e:
        print(f"[Canary] Watchdog error: {e}")


def _update_file_path(file_id, new_path, new_filename):
    """Update file path in database - only if it's NOT a temp file being restored."""
    try:
        conn = get_conn()
        # Get current filename from DB
        row = conn.execute('SELECT filename FROM canary_files WHERE id=?', (file_id,)).fetchone()
        if not row:
            conn.close()
            return
        
        original_name = row['filename']
        
        # Don't update if new_filename looks like a temp file
        # (contains patterns like .sb-, .tmp, ~, .swp, etc.)
        if any(pattern in new_filename for pattern in ['.sb-', '.tmp', '~', '.swp', '.bak', '.goutputstream']):
            print(f"[Canary] 🚫 Ignoring temp file pattern: {new_filename}")
            conn.close()
            return
        
        # Don't update if going back to original name (editor restore operation)
        if new_filename == original_name:
            conn.execute('UPDATE canary_files SET file_path=? WHERE id=?', (new_path, file_id))
        else:
            conn.execute('UPDATE canary_files SET file_path=?, filename=? WHERE id=?',
                        (new_path, new_filename, file_id))
            print(f"[Canary] 📝 DB → {new_filename}")
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Canary] DB error: {e}")


# ── Public API ─────────────────────────────────────────────────────────
def start_monitoring(watch_dir: str):
    global _monitor_thread
    if _monitor_thread and _monitor_thread.is_alive():
        return True
    if not os.path.isdir(watch_dir):
        os.makedirs(watch_dir, exist_ok=True)

    _stop_event.clear()
    _snapshots.clear()
    _debounce.clear()
    _moved_away.clear()
    _rename_paths.clear()
    _location_cache['ts'] = 0  # force refresh

    _monitor_thread = threading.Thread(target=_poll_loop, daemon=True)
    _monitor_thread.start()
    _start_watchdog(watch_dir)
    set_setting('monitoring_active', '1')
    set_setting('watch_directory', watch_dir)
    return True


def stop_monitoring():
    global _observer
    _stop_event.set()
    if _observer and _observer.is_alive():
        _observer.stop()
        _observer.join(timeout=2)
        _observer = None
    set_setting('monitoring_active', '0')
    return True


def is_monitoring():
    return (_monitor_thread is not None and
            _monitor_thread.is_alive() and
            not _stop_event.is_set())


def reset_incidents_for_file(canary_file_id: int) -> dict:
    try:
        conn = get_conn()
        conn.execute('DELETE FROM incidents WHERE canary_file_id=?', (canary_file_id,))
        conn.execute('UPDATE canary_files SET open_count=0, modify_count=0, trigger_count=0 WHERE id=?',
                     (canary_file_id,))
        conn.commit()
        conn.close()
        return {'success': True}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def update_file_content(canary_file_id: int, new_content: str) -> dict:
    """Write new content — suppresses false MODIFIED via debounce pre-set."""
    try:
        conn = get_conn()
        row  = conn.execute('SELECT file_path, filename FROM canary_files WHERE id=?',
                            (canary_file_id,)).fetchone()
        conn.close()
        if not row:
            return {'success': False, 'error': 'File not found'}
        fp = row['file_path']
        # Suppress modification detection for 5 seconds to avoid false positives
        now = time.time()
        _debounce[f"{fp}:MODIFIED"] = now + 5
        _rename_paths[fp] = now
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, 'w', encoding='utf-8') as fh:
            fh.write(new_content)
        # Wait a moment for file system to settle, then update snapshot
        time.sleep(0.1)
        _snapshots[fp] = _snap(fp)
        return {'success': True, 'filename': row['filename'], 'bytes': len(new_content)}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def read_file_content(canary_file_id: int) -> dict:
    try:
        conn = get_conn()
        row  = conn.execute('SELECT file_path, filename FROM canary_files WHERE id=?',
                            (canary_file_id,)).fetchone()
        conn.close()
        if not row:
            return {'success': False, 'error': 'File not found'}
        fp = row['file_path']
        if not os.path.exists(fp):
            return {'success': True, 'content': '', 'exists': False}
        with open(fp, 'r', encoding='utf-8', errors='replace') as fh:
            return {'success': True, 'content': fh.read(), 'exists': True}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def simulate_trigger(canary_file_id: int, event_type: str = 'OPENED') -> dict:
    conn = get_conn()
    row  = conn.execute('SELECT * FROM canary_files WHERE id=?', (canary_file_id,)).fetchone()
    conn.close()
    if not row:
        return {'error': 'File not found'}

    pub_ip, location = _get_cached_location()
    sys_info         = get_system_info()
    timestamp        = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    severity         = 'HIGH' if event_type in (
        'OPENED', 'COPIED', 'DELETED', 'MOVED', 'RENAMED', 'USB_TRANSFER'
    ) else 'MEDIUM'

    incident = {
        'canary_file_id': canary_file_id,
        'filename':       row['filename'],
        'event_type':     event_type.upper(),
        'timestamp':      timestamp,
        'username':       sys_info['username'],
        'device_name':    sys_info['device_name'],
        'public_ip':      pub_ip,
        'location':       location,
        'os_info':        sys_info['os_info'],
        'process_name':   'Finder',
        'destination':    row['file_path'],
        'severity':       severity,
        'alert_sent':     0,
        'notes':          'SIMULATED TRIGGER',
    }

    iid = insert_incident(incident)

    snapshot_path = None
    if get_setting('webcam_enabled') == '1':
        snapshot_path = _capture_webcam(iid)
        if snapshot_path:
            c = get_conn()
            c.execute('UPDATE incidents SET snapshot_path=? WHERE id=?', (snapshot_path, iid))
            c.commit()
            c.close()

    res = dispatch_alerts(incident)
    wa_ok = False
    if get_setting('whatsapp_apikey') and get_setting('whatsapp_phone'):
        wa_ok = send_whatsapp_callmebot(incident)
    elif get_setting('twilio_sid') and get_setting('twilio_token'):
        wa_ok = send_whatsapp_twilio(incident, snapshot_path)
    res['whatsapp'] = wa_ok

    if any(res.values()):
        c = get_conn()
        c.execute('UPDATE incidents SET alert_sent=1 WHERE id=?', (iid,))
        c.commit()
        c.close()

    incident['incident_id']   = iid
    incident['alert_results'] = res
    return incident
