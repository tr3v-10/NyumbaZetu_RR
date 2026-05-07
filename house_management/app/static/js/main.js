/* ─────────────────────────────────────────────────────────────────
   NyumbaManager — Main JS
   Theme toggle, sidebar, alerts, modals, fingerprint collection,
   chart helpers, notifications, and misc UI interactions.
───────────────────────────────────────────────────────────────── */

/* ═══════════════ THEME MANAGEMENT ═══════════════ */
const ThemeManager = (() => {
  const KEY = 'nyumba_theme';
  const HTML = document.documentElement;

  function get() { return localStorage.getItem(KEY) || 'dark'; }
  function set(theme) {
    HTML.setAttribute('data-theme', theme === 'light' ? 'light' : '');
    localStorage.setItem(KEY, theme);
    _updateToggle(theme);
    _updateCharts(theme);
  }
  function toggle() { set(get() === 'light' ? 'dark' : 'light'); }
  function init() {
    const saved = get();
    HTML.setAttribute('data-theme', saved === 'light' ? 'light' : '');
    _updateToggle(saved);
  }
  function _updateToggle(theme) {
    document.querySelectorAll('.theme-toggle-btn').forEach(btn => {
      const isLight = btn.dataset.theme === 'light';
      btn.classList.toggle('active', (theme === 'light') === isLight);
    });
    // Update toggle icon in topbar
    const icon = document.getElementById('themeIcon');
    if (icon) icon.textContent = theme === 'light' ? '☀️' : '🌙';
  }
  function _updateCharts(theme) {
    if (window.Chart) {
      const isDark = theme !== 'light';
      Chart.defaults.color = isDark ? '#8fb88f' : '#4a3f20';
      Chart.defaults.borderColor = isDark ? 'rgba(40,160,40,0.18)' : 'rgba(184,130,10,0.18)';
      // Re-render visible charts
      Object.values(Chart.instances || {}).forEach(c => c.update());
    }
  }
  return { init, set, get, toggle };
})();

/* ═══════════════ SIDEBAR ═══════════════ */
const Sidebar = (() => {
  let sidebar, overlay;
  function init() {
    sidebar = document.querySelector('.sidebar');
    overlay = document.querySelector('.sidebar-overlay');
    if (!sidebar) return;
    if (overlay) overlay.addEventListener('click', close);
    // Persist sidebar state on desktop
    if (window.innerWidth > 768) {
      const collapsed = localStorage.getItem('sidebar_collapsed') === '1';
      if (collapsed) sidebar.classList.add('collapsed');
    }
  }
  function open() {
    if (!sidebar) return;
    sidebar.classList.add('open');
    overlay && overlay.classList.add('show');
    document.body.style.overflow = 'hidden';
  }
  function close() {
    if (!sidebar) return;
    sidebar.classList.remove('open');
    overlay && overlay.classList.remove('show');
    document.body.style.overflow = '';
  }
  function toggle() {
    if (!sidebar) return;
    if (window.innerWidth <= 768) {
      sidebar.classList.contains('open') ? close() : open();
    } else {
      sidebar.classList.toggle('collapsed');
      localStorage.setItem('sidebar_collapsed', sidebar.classList.contains('collapsed') ? '1' : '0');
    }
  }
  return { init, open, close, toggle };
})();

/* ═══════════════ MODALS ═══════════════ */
const Modal = (() => {
  function open(id) {
    const bd = document.getElementById(id);
    if (bd) { bd.classList.add('open'); document.body.style.overflow = 'hidden'; }
  }
  function close(id) {
    const bd = document.getElementById(id);
    if (bd) { bd.classList.remove('open'); document.body.style.overflow = ''; }
  }
  function init() {
    // Close on backdrop click
    document.querySelectorAll('.modal-backdrop').forEach(bd => {
      bd.addEventListener('click', e => {
        if (e.target === bd) close(bd.id);
      });
    });
    // Close button
    document.querySelectorAll('[data-modal-close]').forEach(btn => {
      btn.addEventListener('click', () => close(btn.closest('.modal-backdrop').id));
    });
    // Open buttons
    document.querySelectorAll('[data-modal-open]').forEach(btn => {
      btn.addEventListener('click', () => open(btn.dataset.modalOpen));
    });
    // ESC key
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') {
        document.querySelectorAll('.modal-backdrop.open').forEach(bd => close(bd.id));
      }
    });
  }
  return { open, close, init };
})();

/* ═══════════════ ALERTS (auto-dismiss) ═══════════════ */
const Alerts = (() => {
  function init() {
    document.querySelectorAll('.alert').forEach(el => {
      // Auto-dismiss after 6s
      const timer = setTimeout(() => dismiss(el), 6000);
      const btn = el.querySelector('.alert-dismiss');
      if (btn) btn.addEventListener('click', () => { clearTimeout(timer); dismiss(el); });
    });
  }
  function dismiss(el) {
    el.style.transition = 'opacity 0.3s, transform 0.3s';
    el.style.opacity = '0'; el.style.transform = 'translateX(20px)';
    setTimeout(() => el.remove(), 300);
  }
  return { init };
})();

/* ═══════════════ TOASTS ═══════════════ */
const Toast = (() => {
  let container;
  function _getContainer() {
    if (!container) {
      container = document.querySelector('.toast-container');
      if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
      }
    }
    return container;
  }
  const ICONS = { success: '✓', danger: '✕', warning: '⚠', info: 'ℹ' };
  function show(type, title, msg, duration = 4000) {
    const c = _getContainer();
    const t = document.createElement('div');
    t.className = `toast ${type}`;
    t.innerHTML = `
      <span class="toast-icon">${ICONS[type] || 'ℹ'}</span>
      <div class="toast-text">
        <div class="toast-title">${title}</div>
        ${msg ? `<div class="toast-msg">${msg}</div>` : ''}
      </div>
      <button onclick="this.closest('.toast').remove()" style="background:none;border:none;cursor:pointer;color:var(--text-muted);font-size:1.1rem;padding:0 0 0 8px;">×</button>`;
    c.appendChild(t);
    if (duration > 0) {
      setTimeout(() => {
        t.classList.add('removing');
        setTimeout(() => t.remove(), 300);
      }, duration);
    }
  }
  return { show, success: (t,m,d) => show('success',t,m,d), danger: (t,m,d) => show('danger',t,m,d),
    warning: (t,m,d) => show('warning',t,m,d), info: (t,m,d) => show('info',t,m,d) };
})();

/* ═══════════════ NOTIFICATIONS PANEL ═══════════════ */
const NotifPanel = (() => {
  let panel, count = 0;
  function init() {
    panel = document.querySelector('.notif-panel');
    fetchCount();
    setInterval(fetchCount, 60000);
  }
  function toggle() {
    if (!panel) return;
    panel.classList.toggle('open');
    if (panel.classList.contains('open')) fetchNotifs();
  }
  function fetchCount() {
    fetch('/api/notifications', { credentials: 'same-origin' })
      .then(r => r.json())
      .then(d => {
        count = d.count || 0;
        const badge = document.querySelector('.notif-count');
        if (badge) { badge.textContent = count; badge.style.display = count > 0 ? '' : 'none'; }
      }).catch(() => {});
  }
  function fetchNotifs() {
    fetch('/api/notifications', { credentials: 'same-origin' })
      .then(r => r.json())
      .then(d => {
        const list = document.querySelector('.notif-list');
        if (!list) return;
        if (!d.notifications || d.notifications.length === 0) {
          list.innerHTML = '<div class="empty-state" style="padding:30px;"><div class="empty-state-icon">🔔</div><div class="empty-state-title">All caught up!</div></div>';
          return;
        }
        list.innerHTML = d.notifications.map(n => `
          <div class="notif-item unread" onclick="NotifPanel.markRead(${n.id}, this)">
            <div class="notif-item-title">${n.title}</div>
            <div class="notif-item-msg">${n.message}</div>
            <div class="notif-item-time">${timeAgo(n.created_at)}</div>
          </div>`).join('');
      }).catch(() => {});
  }
  function markRead(id, el) {
    fetch(`/api/notifications/${id}/read`, { method: 'POST', credentials: 'same-origin',
      headers: {'X-CSRFToken': getCSRF()} })
      .then(() => { el && el.classList.remove('unread'); fetchCount(); });
  }
  return { init, toggle, markRead };
})();

/* ═══════════════ BROWSER FINGERPRINT COLLECTION ═══════════════ */
const Fingerprint = (() => {
  function collect() {
    try {
      const data = {
        screenWidth: screen.width,
        screenHeight: screen.height,
        colorDepth: screen.colorDepth,
        devicePixelRatio: window.devicePixelRatio,
        timezoneOffset: new Date().getTimezoneOffset(),
        language: navigator.language,
        platform: navigator.platform,
        doNotTrack: navigator.doNotTrack,
        cookieEnabled: navigator.cookieEnabled,
        javaEnabled: navigator.javaEnabled ? navigator.javaEnabled() : false,
        fingerprint: _generateFingerprint(),
      };
      // Send to backend
      fetch('/api/fingerprint', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
        credentials: 'same-origin',
      }).catch(() => {});
    } catch (e) { /* silent */ }
  }
  function _generateFingerprint() {
    try {
      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');
      ctx.textBaseline = 'top';
      ctx.font = '14px Arial';
      ctx.fillStyle = '#f60'; ctx.fillRect(125, 1, 62, 20);
      ctx.fillStyle = '#069'; ctx.fillText('NyumbaFP', 2, 15);
      ctx.fillStyle = 'rgba(102,204,0,0.7)'; ctx.fillText('NyumbaFP', 4, 17);
      const s = canvas.toDataURL();
      let hash = 0;
      for (let i = 0; i < s.length; i++) { hash = ((hash << 5) - hash) + s.charCodeAt(i); hash |= 0; }
      return Math.abs(hash).toString(36) + '_' + navigator.userAgent.length + '_' + screen.width;
    } catch (e) { return 'nofp'; }
  }
  return { collect };
})();

/* ═══════════════ DROPDOWN ═══════════════ */
const Dropdown = (() => {
  function init() {
    document.querySelectorAll('[data-dropdown-toggle]').forEach(btn => {
      btn.addEventListener('click', e => {
        e.stopPropagation();
        const menu = document.getElementById(btn.dataset.dropdownToggle);
        if (!menu) return;
        // Close all other dropdowns
        document.querySelectorAll('.dropdown-menu.open').forEach(m => { if (m !== menu) m.classList.remove('open'); });
        menu.classList.toggle('open');
      });
    });
    document.addEventListener('click', () => {
      document.querySelectorAll('.dropdown-menu.open').forEach(m => m.classList.remove('open'));
    });
  }
  return { init };
})();

/* ═══════════════ FILE UPLOAD UX ═══════════════ */
const FileUpload = (() => {
  function init() {
    document.querySelectorAll('.file-upload-area').forEach(area => {
      const input = area.querySelector('input[type="file"]') || area.nextElementSibling;
      area.addEventListener('click', () => input && input.click());
      area.addEventListener('dragover', e => { e.preventDefault(); area.classList.add('drag-over'); });
      area.addEventListener('dragleave', () => area.classList.remove('drag-over'));
      area.addEventListener('drop', e => {
        e.preventDefault(); area.classList.remove('drag-over');
        if (input && e.dataTransfer.files.length) {
          input.files = e.dataTransfer.files;
          _updateLabel(area, e.dataTransfer.files);
        }
      });
      if (input) {
        input.addEventListener('change', () => _updateLabel(area, input.files));
      }
    });
  }
  function _updateLabel(area, files) {
    const label = area.querySelector('.file-upload-text');
    if (label && files.length) {
      label.textContent = files.length === 1 ? files[0].name : `${files.length} files selected`;
    }
  }
  return { init };
})();

/* ═══════════════ CONFIRM DIALOGS ═══════════════ */
function confirmAction(message, formId) {
  if (confirm(message)) {
    const form = document.getElementById(formId);
    if (form) form.submit();
    return true;
  }
  return false;
}

/* ═══════════════ CHART DEFAULTS ═══════════════ */
function initChartDefaults() {
  if (!window.Chart) return;
  const isDark = ThemeManager.get() !== 'light';
  Chart.defaults.font.family = "'DM Sans', system-ui, sans-serif";
  Chart.defaults.font.size = 12;
  Chart.defaults.color = isDark ? '#8fb88f' : '#4a3f20';
  Chart.defaults.borderColor = isDark ? 'rgba(40,160,40,0.18)' : 'rgba(184,130,10,0.18)';
  Chart.defaults.plugins.legend.labels.padding = 20;
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.legend.labels.pointStyleWidth = 10;
  Chart.defaults.plugins.tooltip.backgroundColor = isDark ? '#111911' : '#ffffff';
  Chart.defaults.plugins.tooltip.borderColor = isDark ? 'rgba(40,160,40,0.35)' : 'rgba(184,130,10,0.35)';
  Chart.defaults.plugins.tooltip.borderWidth = 1;
  Chart.defaults.plugins.tooltip.titleColor = isDark ? '#e4f4e4' : '#1a1508';
  Chart.defaults.plugins.tooltip.bodyColor  = isDark ? '#8fb88f' : '#4a3f20';
  Chart.defaults.plugins.tooltip.padding = 12;
  Chart.defaults.plugins.tooltip.cornerRadius = 10;
}

function getChartColors(isDark) {
  return isDark
    ? { accent: '#28a028', accentAlpha: 'rgba(40,160,40,0.2)', gold: '#d4952a', goldAlpha: 'rgba(212,149,42,0.2)',
        danger: '#e05252', info: '#4a9edd', success: '#3abf6a', grid: 'rgba(40,160,40,0.12)' }
    : { accent: '#b8820a', accentAlpha: 'rgba(184,130,10,0.15)', gold: '#b8820a', goldAlpha: 'rgba(184,130,10,0.15)',
        danger: '#c0392b', info: '#1a6baa', success: '#218a4a', grid: 'rgba(184,130,10,0.12)' };
}

/* ═══════════════ PAYMENT STATUS POLLING ═══════════════ */
function pollPaymentStatus(checkoutId, statusEl, interval = 3000, maxAttempts = 20) {
  let attempts = 0;
  const poll = setInterval(() => {
    if (++attempts > maxAttempts) { clearInterval(poll); return; }
    fetch(`/tenant/check-payment-status/${checkoutId}`, { credentials: 'same-origin' })
      .then(r => r.json())
      .then(d => {
        if (statusEl) statusEl.textContent = d.status;
        if (d.status === 'success') {
          clearInterval(poll);
          Toast.success('Payment Received', 'Your M-Pesa payment was successful!');
          setTimeout(() => location.reload(), 2000);
        } else if (d.status === 'failed') {
          clearInterval(poll);
          Toast.danger('Payment Failed', 'Your M-Pesa payment was not completed.');
        }
      }).catch(() => {});
  }, interval);
}

/* ═══════════════ HELPERS ═══════════════ */
function getCSRF() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  if (meta) return meta.getAttribute('content');
  const cookie = document.cookie.split(';').find(c => c.trim().startsWith('csrf_token='));
  return cookie ? cookie.split('=')[1] : '';
}

function timeAgo(isoStr) {
  try {
    const d = new Date(isoStr), now = new Date();
    const s = Math.floor((now - d) / 1000);
    if (s < 60) return `${s}s ago`;
    if (s < 3600) return `${Math.floor(s/60)}m ago`;
    if (s < 86400) return `${Math.floor(s/3600)}h ago`;
    return `${Math.floor(s/86400)}d ago`;
  } catch (e) { return isoStr; }
}

function formatKES(amount) {
  return 'KSh ' + parseFloat(amount).toLocaleString('en-KE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/* ═══════════════ INIT ═══════════════ */
document.addEventListener('DOMContentLoaded', () => {
  ThemeManager.init();
  Sidebar.init();
  Modal.init();
  Alerts.init();
  Dropdown.init();
  FileUpload.init();
  NotifPanel.init();
  initChartDefaults();

  // Fingerprint collection (non-blocking, privacy notice in policy page)
  setTimeout(() => Fingerprint.collect(), 1500);

  // Theme toggle buttons
  document.querySelectorAll('.theme-toggle-btn').forEach(btn => {
    btn.addEventListener('click', () => ThemeManager.set(btn.dataset.theme));
  });

  // Sidebar menu button
  const menuBtn = document.querySelector('.topbar-menu-btn');
  if (menuBtn) menuBtn.addEventListener('click', () => Sidebar.toggle());

  // Notification bell
  const notifBtn = document.querySelector('.notif-btn');
  if (notifBtn) notifBtn.addEventListener('click', () => NotifPanel.toggle());

  // Active nav item highlight
  const path = window.location.pathname;
  document.querySelectorAll('.nav-item').forEach(item => {
    const href = item.getAttribute('href');
    if (href && path.startsWith(href) && href !== '/') item.classList.add('active');
  });

  // Auto-format KES inputs
  document.querySelectorAll('input[data-kes]').forEach(input => {
    input.addEventListener('blur', () => {
      const v = parseFloat(input.value);
      if (!isNaN(v)) input.value = v.toFixed(2);
    });
  });

  // CSRF header for all fetch requests
  const origFetch = window.fetch;
  window.fetch = function(url, opts = {}) {
    if (typeof url === 'string' && url.startsWith('/') && !url.startsWith('/api/mpesa/callback')) {
      opts.headers = opts.headers || {};
      if (!opts.headers['X-CSRFToken']) opts.headers['X-CSRFToken'] = getCSRF();
    }
    return origFetch(url, opts);
  };
});

// Global expose
window.ThemeManager = ThemeManager;
window.Modal = Modal;
window.Toast = Toast;
window.Sidebar = Sidebar;
window.NotifPanel = NotifPanel;
window.confirmAction = confirmAction;
window.pollPaymentStatus = pollPaymentStatus;
window.getChartColors = getChartColors;
window.formatKES = formatKES;
