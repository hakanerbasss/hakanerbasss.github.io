'use strict';

let selectedFile = null;
let pollTimer = null;

// ── Dosya seçimi ─────────────────────────────────────────────────────────────
function onFileSelect(input) {
  selectedFile = input.files[0] || null;
  const label = document.getElementById('fileSelectedLabel');
  const btn   = document.getElementById('btnUpload');
  if (selectedFile) {
    label.textContent = `✓ ${selectedFile.name}  (${fmtSize(selectedFile.size)})`;
    label.style.display = 'block';
    btn.disabled = false;
  } else {
    label.style.display = 'none';
    btn.disabled = true;
  }
}

// Sürükle-bırak
const dropZone = document.getElementById('dropZone');
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (!file) return;
  const input = document.getElementById('fileInput');
  // DataTransfer ile input.files'ı set edemeyiz, doğrudan ele al
  selectedFile = file;
  const label = document.getElementById('fileSelectedLabel');
  label.textContent = `✓ ${file.name}  (${fmtSize(file.size)})`;
  label.style.display = 'block';
  document.getElementById('btnUpload').disabled = false;
});

// ── Yükleme ──────────────────────────────────────────────────────────────────
async function uploadBook() {
  if (!selectedFile) return;

  const btn   = document.getElementById('btnUpload');
  const title = document.getElementById('titleInput').value.trim();

  btn.disabled = true;
  btn.textContent = 'Yükleniyor...';

  const form = new FormData();
  form.append('file', selectedFile);
  form.append('title', title);

  try {
    const r = await fetch('/api/jobs/upload', { method: 'POST', body: form });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || 'Yükleme hatası');

    // Reset
    selectedFile = null;
    document.getElementById('fileInput').value = '';
    document.getElementById('fileSelectedLabel').style.display = 'none';
    document.getElementById('titleInput').value = '';

    toast(`"${d.title}" sıraya alındı`, 'success');
    await loadJobs();
    startPoll();
  } catch (e) {
    toast('Hata: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg> Seslendir`;
  }
}

// ── Job listesi ───────────────────────────────────────────────────────────────
async function loadJobs() {
  try {
    const r = await fetch('/api/jobs');
    const d = await r.json();
    renderJobs(d.jobs || []);
    // Aktif iş varsa poll devam etsin
    const hasActive = (d.jobs || []).some(j => j.status === 'pending' || j.status === 'processing');
    if (hasActive) startPoll(); else stopPoll();
  } catch {}
}

function startPoll() {
  if (pollTimer) return;
  pollTimer = setInterval(loadJobs, 3000);
}

function stopPoll() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

function renderJobs(jobs) {
  const el = document.getElementById('jobList');
  if (!jobs.length) {
    el.innerHTML = `<div class="empty">
      <div class="empty-icon">🎙️</div>
      <div class="empty-title">Henüz iş yok</div>
      <div>Kitap yükleyerek başlayın</div>
    </div>`;
    return;
  }
  el.innerHTML = `<div class="jobs-list">${jobs.map(jobCard).join('')}</div>`;
}

function jobCard(j) {
  const statusCls = { pending: 's-pending', processing: 's-processing', completed: 's-completed', failed: 's-failed' }[j.status] || 's-pending';
  const statusLabel = { pending: 'Bekliyor', processing: 'İşleniyor', completed: 'Tamamlandı', failed: 'Hata' }[j.status] || j.status;

  const progressBar = (j.status === 'processing' || j.status === 'pending') ? `
    <div class="progress-wrap">
      <div class="progress-info">
        <span class="progress-msg">${j.done || 0} / ${j.total || '?'} parça</span>
        <span class="progress-pct">${j.progress || 0}%</span>
      </div>
      <div class="progress-bg"><div class="progress-fill" style="width:${j.progress || 0}%"></div></div>
    </div>` : '';

  const actions = buildActions(j);
  const error = j.error ? `<div class="error-text">⚠ ${esc(j.error)}</div>` : '';

  return `<div class="job-card">
    <div class="job-top">
      <span class="job-title" title="${esc(j.title)}">${esc(j.title)}</span>
      <span class="job-fmt">${esc(j.file_format || '')}</span>
      <span class="status-badge ${statusCls}">${statusLabel}</span>
    </div>
    ${progressBar}
    ${error}
    ${actions ? `<div class="job-actions">${actions}</div>` : ''}
  </div>`;
}

function buildActions(j) {
  let html = '';
  if (j.status === 'completed') {
    html += `<a class="btn btn-outline btn-sm" href="/api/jobs/${j.id}/download" download>
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
        <polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
      </svg>
      MP3 İndir
    </a>`;
  }
  html += `<button class="btn btn-danger btn-sm" onclick="deleteJob('${j.id}')">Sil</button>`;
  return html;
}

async function deleteJob(id) {
  if (!confirm('Bu işi ve dosyaları silmek istiyor musunuz?')) return;
  try {
    await fetch(`/api/jobs/${id}`, { method: 'DELETE' });
    await loadJobs();
    toast('Silindi', 'info');
  } catch (e) {
    toast('Silinemedi: ' + e.message, 'error');
  }
}

// ── Yardımcılar ───────────────────────────────────────────────────────────────
function esc(s) {
  return String(s ?? '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function fmtSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1048576).toFixed(1) + ' MB';
}

function toast(msg, type = 'info') {
  const colors = { success: ['#14532d','#86efac'], error: ['#7f1d1d','#fca5a5'], info: ['#1e1b4b','#a5b4fc'] };
  const [bg, fg] = colors[type] || colors.info;
  const el = document.createElement('div');
  el.style.cssText = `position:fixed;bottom:20px;right:20px;z-index:9999;background:${bg};color:${fg};
    border-radius:10px;padding:12px 18px;font-size:13px;font-weight:600;
    box-shadow:0 8px 24px rgba(0,0,0,.4);max-width:360px;`;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

// ── Sayfa yüklenince ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadJobs();
});
