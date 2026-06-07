// ── Toast ────────────────────────────────────────────────────────────
function showToast(msg, type = 'ok') {
  let container = document.querySelector('.toast-container');
  if (!container) {
    container = document.createElement('div');
    container.className = 'toast-container';
    document.body.appendChild(container);
  }
  const icons = { ok: '✓', err: '✕', warn: '⚠' };
  const t = document.createElement('div');
  t.className = `toast toast-${type}`;
  t.innerHTML = `<span>${icons[type] || '•'}</span><span>${msg}</span>`;
  container.appendChild(t);
  setTimeout(() => { t.style.opacity = '0'; t.style.transform = 'translateX(20px)'; t.style.transition = '.2s'; setTimeout(() => t.remove(), 200); }, 3000);
}

// ── Monitor Toggle ───────────────────────────────────────────────────
function updateMonitorUI(active) {
  const dot  = document.getElementById('statusDot');
  const text = document.getElementById('statusText');
  const btn  = document.getElementById('toggleMonitor');
  if (!dot) return;
  if (active) {
    dot.className  = 'status-dot active';
    text.textContent = 'MONITORING';
    btn.textContent  = 'Stop';
    btn.className    = 'btn btn-stop';
  } else {
    dot.className  = 'status-dot inactive';
    text.textContent = 'INACTIVE';
    btn.textContent  = 'Start';
    btn.className    = 'btn btn-primary';
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const btn = document.getElementById('toggleMonitor');
  if (!btn) return;

  // Load initial status
  fetch('/api/monitor/status').then(r => r.json()).then(d => updateMonitorUI(d.monitoring));

  btn.addEventListener('click', async () => {
    const isActive = btn.textContent.trim() === 'Stop';
    const url = isActive ? '/api/monitor/stop' : '/api/monitor/start';
    try {
      const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
      const d = await r.json();
      updateMonitorUI(d.monitoring);
      showToast(d.monitoring ? 'Monitoring started' : 'Monitoring stopped', d.monitoring ? 'ok' : 'warn');
    } catch (e) {
      showToast('Request failed', 'err');
    }
  });
});
