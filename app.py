import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, jsonify, request, send_from_directory
from backend.database import (
    init_db, get_conn, get_setting, set_setting,
    get_dashboard_stats, insert_incident
)
from backend.generator import generate_canary_file
from backend.monitor import start_monitoring, stop_monitoring, is_monitoring, simulate_trigger, update_file_content, read_file_content, suppress_file_events
from backend.encryption import make_encrypted_file, read_and_decrypt, generate_key, is_encrypted_file
from datetime import datetime

app = Flask(
    __name__,
    template_folder='frontend/templates',
    static_folder='frontend/static'
)

CANARY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'canary_files')
SNAPSHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'snapshots')

# ─── Pages ────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/files')
def files_page():
    return render_template('files.html')

@app.route('/incidents')
def incidents_page():
    return render_template('incidents.html')

@app.route('/settings')
def settings_page():
    return render_template('settings.html')

# Serve webcam snapshots
@app.route('/snapshots/<path:filename>')
def serve_snapshot(filename):
    return send_from_directory(SNAPSHOT_DIR, filename)

# ─── API: Dashboard ───────────────────────────────────────────────────
@app.route('/api/stats')
def api_stats():
    stats = get_dashboard_stats()
    stats['monitoring_active'] = is_monitoring()
    stats['watch_directory']   = get_setting('watch_directory') or CANARY_DIR
    return jsonify(stats)

# ─── API: Canary Files ────────────────────────────────────────────────
@app.route('/api/files', methods=['GET'])
def api_get_files():
    conn = get_conn()
    rows = conn.execute('SELECT * FROM canary_files ORDER BY created_at DESC').fetchall()
    conn.close()
    
    files = []
    for row in rows:
        file_data = dict(row)
        # Check if file exists on disk
        file_data['file_exists'] = os.path.exists(file_data['file_path'])
        files.append(file_data)
    
    return jsonify(files)


@app.route('/api/files', methods=['POST'])
def api_create_file():
    data      = request.json or {}
    filename  = data.get('filename', '').strip()
    file_type = data.get('file_type', 'txt').strip()
    risk_label = data.get('risk_label', 'HIGH').strip()
    custom_content = data.get('custom_content', '').strip()

    if not filename:
        return jsonify({'error': 'Filename required'}), 400

    encrypt = bool(data.get('encrypt', False))  # JS sends boolean

    try:
        result = generate_canary_file(filename, file_type, CANARY_DIR)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    # Suppress events for this file to prevent false OPENED on creation
    suppress_file_events(result['file_path'], 10)

    enc_key = None
    if encrypt:
        # Generate key and encrypt the file
        enc_key      = generate_key()
        plaintext    = custom_content or result['decoy_content']
        make_encrypted_file(plaintext, enc_key, result['file_path'])
    elif custom_content:
        with open(result['file_path'], 'w', encoding='utf-8') as f:
            f.write(custom_content)

    conn = get_conn()
    c    = conn.cursor()
    c.execute('''
        INSERT INTO canary_files
        (filename, file_type, file_path, decoy_content, custom_content,
         monitoring_enabled, created_at, risk_label, encryption_key, is_encrypted)
        VALUES (?,?,?,?,?,1,?,?,?,?)
    ''', (
        result['filename'], file_type, result['file_path'],
        result['decoy_content'], custom_content or None,
        datetime.now().strftime('%Y-%m-%d %H:%M:%S'), risk_label,
        enc_key, 1 if encrypt else 0,
    ))
    file_id = c.lastrowid
    conn.commit()
    conn.close()

    resp = {'success': True, 'id': file_id, 'filename': result['filename']}
    if enc_key:
        resp['encryption_key'] = enc_key  # show once to user!
    return jsonify(resp)


@app.route('/api/files/<int:fid>', methods=['GET'])
def api_get_file(fid):
    conn = get_conn()
    row  = conn.execute('SELECT * FROM canary_files WHERE id=?', (fid,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'Not found'}), 404
    d = dict(row)
    
    # Check if file exists on disk
    d['file_exists'] = os.path.exists(d['file_path'])
    
    # Read actual file content if it exists
    try:
        if d['file_exists']:
            with open(d['file_path'], 'r', encoding='utf-8', errors='replace') as f:
                d['file_content'] = f.read()
        else:
            d['file_content'] = ''
    except Exception:
        d['file_content'] = ''
    return jsonify(d)


@app.route('/api/files/<int:fid>/content', methods=['POST'])
def api_update_content(fid):
    """Update canary file content — uses monitor debounce to suppress false MODIFIED."""
    data    = request.json or {}
    content = data.get('content', '')
    result  = update_file_content(fid, content)
    if result.get('success'):
        conn = get_conn()
        conn.execute('UPDATE canary_files SET custom_content=? WHERE id=?', (content, fid))
        conn.commit()
        conn.close()
    return jsonify(result)


@app.route('/api/files/<int:fid>', methods=['DELETE'])
def api_delete_file(fid):
    conn = get_conn()
    row  = conn.execute('SELECT * FROM canary_files WHERE id=?', (fid,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Not found'}), 404

    try:
        if os.path.exists(row['file_path']):
            os.remove(row['file_path'])
    except Exception:
        pass

    # Reset/delete associated incidents
    conn.execute('DELETE FROM incidents WHERE canary_file_id=?', (fid,))
    conn.execute('DELETE FROM canary_files WHERE id=?', (fid,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/files/<int:fid>/toggle', methods=['POST'])
def api_toggle_file(fid):
    conn = get_conn()
    row  = conn.execute('SELECT monitoring_enabled FROM canary_files WHERE id=?', (fid,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    new_val = 0 if row['monitoring_enabled'] else 1
    conn.execute('UPDATE canary_files SET monitoring_enabled=? WHERE id=?', (new_val, fid))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'monitoring_enabled': new_val})


@app.route('/api/files/<int:fid>/reset', methods=['POST'])
def api_reset_file(fid):
    """Reset incident history and counters for a canary file."""
    conn = get_conn()
    conn.execute('DELETE FROM incidents WHERE canary_file_id=?', (fid,))
    conn.execute('''
        UPDATE canary_files
        SET trigger_count=0, open_count=0, modify_count=0, last_triggered=NULL
        WHERE id=?
    ''', (fid,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/files/<int:fid>/restore', methods=['POST'])
def api_restore_file(fid):
    """Restore a missing canary file by recreating it with original content."""
    conn = get_conn()
    row = conn.execute('SELECT * FROM canary_files WHERE id=?', (fid,)).fetchone()
    conn.close()
    
    if not row:
        return jsonify({'error': 'File not found'}), 404
    
    # Check if file already exists
    if os.path.exists(row['file_path']):
        return jsonify({'error': 'File already exists'}), 400
    
    try:
        # Create directory if needed
        os.makedirs(os.path.dirname(row['file_path']), exist_ok=True)
        
        # Restore with custom content if available, otherwise decoy content
        content_to_restore = row['custom_content'] or row['decoy_content'] or "Restored canary file content"
        
        if row['is_encrypted'] and row['encryption_key']:
            # Restore encrypted file
            from backend.encryption import make_encrypted_file
            make_encrypted_file(content_to_restore, row['encryption_key'], row['file_path'])
        else:
            # Restore plain text file
            with open(row['file_path'], 'w', encoding='utf-8') as f:
                f.write(content_to_restore)
        
        # Suppress monitoring events for this restoration
        suppress_file_events(row['file_path'], 10)
        
        return jsonify({'success': True, 'message': f'File {row["filename"]} restored'})
        
    except Exception as e:
        return jsonify({'error': f'Restore failed: {str(e)}'}), 500




# ─── API: Decrypt File ────────────────────────────────────────────────
@app.route('/api/files/<int:fid>/decrypt', methods=['POST'])
def api_decrypt_file(fid):
    """Try to decrypt a canary file with provided key."""
    key = (request.json or {}).get('key', '').strip()
    if not key:
        return jsonify({'success': False, 'error': 'Key required'}), 400

    conn = get_conn()
    row  = conn.execute('SELECT * FROM canary_files WHERE id=?', (fid,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'Not found'}), 404

    if not row['is_encrypted']:
        # Not encrypted — just return content
        try:
            with open(row['file_path'], 'r', encoding='utf-8', errors='replace') as f:
                return jsonify({'success': True, 'content': f.read(), 'encrypted': False})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})

    ok, content = read_and_decrypt(row['file_path'], key)
    return jsonify({'success': ok, 'content': content if ok else '', 'encrypted': True})

# ─── API: Incidents ───────────────────────────────────────────────────
@app.route('/api/incidents', methods=['GET'])
def api_incidents():
    page     = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    severity = request.args.get('severity', '')
    offset   = (page - 1) * per_page

    conn   = get_conn()
    query  = 'SELECT * FROM incidents'
    params = []
    if severity:
        query += ' WHERE severity=?'
        params.append(severity)
    query += ' ORDER BY timestamp DESC LIMIT ? OFFSET ?'
    params += [per_page, offset]

    rows  = conn.execute(query, params).fetchall()
    total = conn.execute('SELECT COUNT(*) as c FROM incidents').fetchone()['c']
    conn.close()

    return jsonify({
        'incidents': [dict(r) for r in rows],
        'total': total, 'page': page, 'per_page': per_page
    })


@app.route('/api/incidents/clear', methods=['POST'])
def api_clear_incidents():
    """Clear ALL incidents."""
    conn = get_conn()
    conn.execute('DELETE FROM incidents')
    conn.execute('UPDATE canary_files SET trigger_count=0, open_count=0, modify_count=0, last_triggered=NULL')
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/incidents/<int:iid>', methods=['DELETE'])
def api_delete_incident(iid):
    conn = get_conn()
    conn.execute('DELETE FROM incidents WHERE id=?', (iid,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ─── API: Monitoring Control ──────────────────────────────────────────
@app.route('/api/monitor/start', methods=['POST'])
def api_monitor_start():
    watch_dir = (request.json or {}).get('watch_dir', CANARY_DIR)
    ok = start_monitoring(watch_dir)
    return jsonify({'success': ok, 'monitoring': is_monitoring()})


@app.route('/api/monitor/stop', methods=['POST'])
def api_monitor_stop():
    ok = stop_monitoring()
    return jsonify({'success': ok, 'monitoring': is_monitoring()})


@app.route('/api/monitor/status')
def api_monitor_status():
    return jsonify({
        'monitoring': is_monitoring(),
        'watch_directory': get_setting('watch_directory') or CANARY_DIR
    })


# ─── API: Simulate ────────────────────────────────────────────────────
@app.route('/api/simulate', methods=['POST'])
def api_simulate():
    data       = request.json or {}
    file_id    = data.get('file_id')
    event_type = data.get('event_type', 'OPENED')
    if not file_id:
        return jsonify({'error': 'file_id required'}), 400
    result = simulate_trigger(int(file_id), event_type)
    return jsonify(result)


# ─── API: Snapshots ───────────────────────────────────────────────────
@app.route('/api/snapshots')
def api_snapshots():
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    files = sorted(
        [f for f in os.listdir(SNAPSHOT_DIR) if f.endswith('.jpg')],
        reverse=True
    )[:20]
    return jsonify([{'filename': f, 'url': f'/snapshots/{f}'} for f in files])


@app.route('/api/files/<int:fid>/snapshots')
def api_file_snapshots(fid):
    """Get all snapshots for a specific canary file."""
    conn = get_conn()
    # Get incidents with snapshots for this file
    rows = conn.execute('''
        SELECT id, timestamp, event_type, snapshot_path, severity, username, device_name
        FROM incidents 
        WHERE canary_file_id=? AND snapshot_path IS NOT NULL 
        ORDER BY timestamp DESC
    ''', (fid,)).fetchall()
    conn.close()
    
    snapshots = []
    for row in rows:
        if row['snapshot_path'] and os.path.exists(row['snapshot_path']):
            filename = os.path.basename(row['snapshot_path'])
            snapshots.append({
                'incident_id': row['id'],
                'filename': filename,
                'url': f'/snapshots/{filename}',
                'timestamp': row['timestamp'],
                'event_type': row['event_type'],
                'severity': row['severity'],
                'username': row['username'],
                'device_name': row['device_name']
            })
    
    return jsonify(snapshots)


# ─── API: Settings ────────────────────────────────────────────────────
@app.route('/api/settings', methods=['GET'])
def api_get_settings():
    keys = [
        'telegram_token', 'telegram_chat_id',
        'smtp_host', 'smtp_port', 'smtp_user', 'alert_email',
        'alert_telegram', 'alert_email_enabled',
        'watch_directory', 'webcam_enabled',
        'twilio_sid', 'twilio_token', 'twilio_from', 'twilio_to',
        'snapshot_url_base',
        'whatsapp_phone', 'whatsapp_apikey',
    ]
    result = {}
    for k in keys:
        v = get_setting(k) or ''
        if any(x in k for x in ['token', 'pass', 'secret', 'sid', 'apikey']):
            result[k] = ('*' * (len(v) - 4) + v[-4:]) if len(v) > 4 else ('*' * len(v))
        else:
            result[k] = v
    return jsonify(result)


@app.route('/api/settings', methods=['POST'])
def api_save_settings():
    data    = request.json or {}
    allowed = [
        'telegram_token', 'telegram_chat_id',
        'smtp_host', 'smtp_port', 'smtp_user', 'smtp_pass', 'alert_email',
        'alert_telegram', 'alert_email_enabled', 'watch_directory',
        'webcam_enabled', 'twilio_sid', 'twilio_token',
        'twilio_from', 'twilio_to', 'snapshot_url_base',
        'whatsapp_phone', 'whatsapp_apikey',
    ]
    for k in allowed:
        if k in data:
            val = data[k]
            if val is not None and not (isinstance(val, str) and all(c == '*' for c in val)):
                set_setting(k, str(val))
    return jsonify({'success': True})


@app.route('/api/test-telegram', methods=['POST'])
def api_test_telegram():
    from backend.alerter import send_telegram_alert
    ok = send_telegram_alert({
        'filename': 'TEST_canary.txt', 'event_type': 'TEST',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'username': 'TestUser', 'device_name': 'TEST-DEVICE',
        'public_ip': '0.0.0.0', 'os_info': 'Test OS',
        'process_name': 'test', 'destination': '/test/path', 'severity': 'LOW',
    })
    return jsonify({'success': ok})


if __name__ == '__main__':
    init_db()
    os.makedirs(CANARY_DIR, exist_ok=True)
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    print("\n" + "═" * 50)
    print("  🪤  CANARY-FILE  |  Cyber Theft Detection")
    print("═" * 50)
    print(f"  Dashboard  →  http://127.0.0.1:5001")
    print("═" * 50 + "\n")
    app.run(debug=False, host='0.0.0.0', port=5001, use_reloader=False)