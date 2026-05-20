// ─── API helpers ──────────────────────────────────────────────────────────────
async function api(url, method = 'GET', body = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(url, opts);
  return res.json();
}

// ─── Toast ────────────────────────────────────────────────────────────────────
function toast(msg, type = 'info') {
  const icons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.innerHTML = `<span>${icons[type] || 'ℹ️'}</span><span style="flex:1">${msg}</span><span class="toast-close" onclick="this.parentElement.remove()">✕</span>`;
  document.getElementById('toastContainer').appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

// ─── Modal ────────────────────────────────────────────────────────────────────
function openModal(title, html, extraClass = '') {
  document.getElementById('modalTitle').textContent = title;
  document.getElementById('modalBody').innerHTML = html;
  const box = document.getElementById('globalModalBox');
  box.className = 'modal ' + extraClass;
  document.getElementById('globalModal').style.display = 'flex';
  document.body.style.overflow = 'hidden';
}
function closeModal() {
  document.getElementById('globalModal').style.display = 'none';
  document.body.style.overflow = '';
}
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });
document.getElementById('globalModal')?.addEventListener('click', e => {
  if (e.target === document.getElementById('globalModal')) closeModal();
});

// ─── Sidebar ──────────────────────────────────────────────────────────────────
function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('open');
  document.getElementById('sidebarOverlay').classList.toggle('open');
}
function closeSidebar() {
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('sidebarOverlay').classList.remove('open');
}

// ─── Sidebar name ─────────────────────────────────────────────────────────────
async function loadSidebarName() {
  try {
    const s = await api('/api/settings');
    const el = document.getElementById('sidebarName');
    if (el && s.name) el.textContent = s.name.length > 12 ? s.name.slice(0, 12) + '…' : s.name;
  } catch {}
}

// ─── Notification badge ───────────────────────────────────────────────────────
async function loadNotifBadge() {
  try {
    const d = await api('/api/notifications/unread-count');
    const badge = document.getElementById('notifBadge');
    if (badge) {
      if (d.count > 0) { badge.textContent = d.count; badge.style.display = 'inline'; }
      else badge.style.display = 'none';
    }
  } catch {}
}

// ─── Format currency ──────────────────────────────────────────────────────────
function fmtCurrency(n, currency = 'UZS') {
  return Number(n).toLocaleString('uz-UZ') + ' ' + currency;
}

// ─── Format date ──────────────────────────────────────────────────────────────
function fmtDate(str) {
  if (!str) return '—';
  const d = new Date(str);
  return d.toLocaleDateString('uz-UZ', { year: 'numeric', month: '2-digit', day: '2-digit' });
}

function fmtDateTime(str) {
  if (!str) return '—';
  const d = new Date(str);
  return d.toLocaleString('uz-UZ', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}

// ─── Status badge ─────────────────────────────────────────────────────────────
function statusBadge(status) {
  const map = {
    active: ['badge-success', "Faol"],
    inactive: ['badge-gray', "Nofaol"],
    present: ['badge-success', "Keldi"],
    absent: ['badge-danger', "Kelmadi"],
    excused: ['badge-warning', "Sababli"],
    full: ['badge-success', "To'liq"],
    partial: ['badge-warning', "Qisman"],
    paid: ['badge-success', "To'langan"],
    unpaid: ['badge-danger', "To'lanmagan"],
  };
  const [cls, label] = map[status] || ['badge-gray', status];
  return `<span class="badge ${cls}">${label}</span>`;
}

// ─── Confirm dialog ───────────────────────────────────────────────────────────
function confirmAction(msg, onYes) {
  openModal('Tasdiqlash', `
    <p style="color:var(--text2);margin-bottom:20px">${msg}</p>
    <div style="display:flex;gap:10px;justify-content:flex-end">
      <button class="btn btn-ghost" onclick="closeModal()">Bekor qilish</button>
      <button class="btn btn-danger" onclick="closeModal();(${onYes.toString()})()">Ha, davom etish</button>
    </div>
  `);
}

// ─── Phone format ─────────────────────────────────────────────────────────────
function phoneLink(phone) {
  if (!phone) return '—';
  return `<a class="phone-link" href="tel:${phone}">📞 ${phone}</a>`;
}

// ─── Month picker helper ──────────────────────────────────────────────────────
function currentYearMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

function monthName(ym) {
  if (!ym) return '';
  const [y, m] = ym.split('-');
  return new Date(y, m - 1).toLocaleString('uz-UZ', { month: 'long', year: 'numeric' });
}

// ─── Avatar initials ──────────────────────────────────────────────────────────
function avatarHtml(student) {
  if (student.image) {
    return `<div class="student-avatar"><img src="${student.image}" alt="${student.first_name}" onerror="this.parentElement.innerHTML='${student.first_name[0] || '?'}'"></div>`;
  }
  const colors = ['#4f6ef7','#22c55e','#f59e0b','#ef4444','#8b5cf6','#06b6d4'];
  const color = colors[(student.first_name.charCodeAt(0) || 0) % colors.length];
  return `<div class="student-avatar" style="background:${color}20;color:${color}">${student.first_name[0] || '?'}</div>`;
}

// ─── Image upload ─────────────────────────────────────────────────────────────
async function uploadImage(file) {
  const fd = new FormData();
  fd.append('image', file);
  const res = await fetch('/api/upload-image', { method: 'POST', body: fd });
  return res.json();
}
