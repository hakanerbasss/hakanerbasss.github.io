'use strict';

// ── State ────────────────────────────────────────────────────────────────────
let currentJobId = null;
let pollTimer = null;
let selectedFormat = 'shorts';
let ytConnected = false;

// ── Init ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('storyText').addEventListener('input', updateCharCount);
  checkYtStatus();

  // OAuth callback param
  if (location.search.includes('yt=connected')) {
    history.replaceState({}, '', '/');
    checkYtStatus();
  }
});

function updateCharCount() {
  const n = document.getElementById('storyText').value.length;
  document.getElementById('charCount').textContent = `${n.toLocaleString('tr-TR')} karakter`;
}

// ── Format seçici ────────────────────────────────────────────────────────────
function setFormat(fmt) {
  selectedFormat = fmt;
  document.querySelectorAll('.format-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.fmt === fmt);
  });
}

// ── YouTube bağlantı ─────────────────────────────────────────────────────────
async function checkYtStatus() {
  try {
    const r = await fetch('/api/youtube/status');
    const d = await r.json();
    ytConnected = d.connected;
    const badge = document.getElementById('ytBadge');
    const btn = document.getElementById('btnYtConnect');
    if (ytConnected) {
      badge.className = 'yt-badge connected';
      badge.querySelector('span').textContent = 'YouTube bağlı';
      if (btn) btn.textContent = '✓ YouTube Bağlı';
    }
  } catch {}
}

async function connectYouTube() {
  try {
    const r = await fetch('/api/youtube/auth-url');
    const d = await r.json();
    if (d.auth_url) window.location.href = d.auth_url;
    else showToast('YouTube yapılandırılmamış (.env dosyasını kontrol edin)', 'error');
  } catch (e) {
    showToast('Bağlantı hatası: ' + e.message, 'error');
  }
}

// ── Video Üretimi ────────────────────────────────────────────────────────────
async function startGenerate() {
  const title = document.getElementById('title').value.trim();
  const text = document.getElementById('storyText').value.trim();

  if (!title) { showToast('Lütfen bir başlık girin.', 'error'); return; }
  if (text.length < 50) { showToast('Metin en az 50 karakter olmalı.', 'error'); return; }

  const btn = document.getElementById('btnGenerate');
  btn.disabled = true;
  btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg> İşleniyor...';

  clearPoll();

  const body = {
    title,
    text,
    format: selectedFormat,
    youtube_description: document.getElementById('ytDesc').value,
    youtube_tags: document.getElementById('ytTags').value
      .split(',').map(s => s.trim()).filter(Boolean),
  };

  try {
    const r = await fetch('/api/video/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      const err = await r.json();
      throw new Error(err.detail || 'Sunucu hatası');
    }
    const d = await r.json();
    currentJobId = d.job_id;
    renderProgress(0, 'Başlatılıyor...', 'processing', []);
    pollTimer = setInterval(() => pollStatus(currentJobId), 2000);
  } catch (e) {
    btn.disabled = false;
    btn.innerHTML = '▶ Video Üret';
    showToast('Hata: ' + e.message, 'error');
  }
}

async function pollStatus(jobId) {
  try {
    const r = await fetch(`/api/video/status/${jobId}`);
    if (!r.ok) return;
    const job = await r.json();

    if (job.status === 'processing' || job.status === 'pending') {
      renderProgress(job.progress, job.message, job.status, job.scenes);
    } else if (job.status === 'completed') {
      clearPoll();
      renderCompleted(job);
      resetGenerateBtn();
    } else if (job.status === 'failed') {
      clearPoll();
      renderFailed(job.error || job.message);
      resetGenerateBtn();
    }
  } catch {}
}

// ── Render functions ─────────────────────────────────────────────────────────
function renderProgress(pct, msg, status, scenes) {
  const panel = document.getElementById('rightPanel');
  panel.innerHTML = `
    <div class="card">
      <div class="card-title">
        Üretim Durumu
        <span class="status-badge status-${status}" style="float:right">
          ${statusLabel(status)}
        </span>
      </div>
      <div class="progress-wrap">
        <div class="progress-row">
          <span class="progress-message">${escHtml(msg)}</span>
          <span class="progress-pct">${pct}%</span>
        </div>
        <div class="progress-bar-bg">
          <div class="progress-bar-fill" style="width:${pct}%"></div>
        </div>
      </div>
    </div>
    ${scenes && scenes.length > 0 ? renderScenes(scenes) : ''}
  `;
}

function renderScenes(scenes) {
  if (!scenes.length) return '';
  const items = scenes.map(s => `
    <div class="scene-card">
      <div class="scene-header">
        <span class="scene-num">${s.index + 1}</span>
        <span class="scene-atm">${s.atmosphere || 'neutral'}</span>
        <span class="scene-status">${s.clip_path ? '✓ hazır' : s.audio_path ? '⏳ video...' : '⏳'}</span>
      </div>
      <div class="scene-text">${escHtml(s.text.substring(0, 120))}${s.text.length > 120 ? '…' : ''}</div>
      <div class="scene-keywords">
        ${(s.keywords || []).map(k => `<span class="kw-tag">${escHtml(k)}</span>`).join('')}
      </div>
    </div>
  `).join('');
  return `
    <div class="card">
      <div class="card-title">Sahneler (${scenes.length})</div>
      <div class="scenes-grid">${items}</div>
    </div>
  `;
}

function renderCompleted(job) {
  const panel = document.getElementById('rightPanel');
  const ytSection = ytConnected ? `
    <div class="card">
      <div class="card-title">YouTube'a Yükle</div>
      <div class="yt-panel">
        <div class="field">
          <label>Başlık</label>
          <input type="text" id="ytTitle" value="${escAttr(job.request?.title || '')}" maxlength="100">
        </div>
        <div style="display:flex;gap:10px;margin-top:4px">
          <button class="btn btn-success" onclick="uploadToYoutube('${job.job_id}')">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M23.5 6.2c-.3-1-1-1.8-2-2.1C19.6 3.5 12 3.5 12 3.5s-7.6 0-9.5.6c-1 .3-1.7 1.1-2 2.1C0 8.1 0 12 0 12s0 3.9.5 5.8c.3 1 1 1.8 2 2.1 1.9.6 9.5.6 9.5.6s7.6 0 9.5-.6c1-.3 1.7-1.1 2-2.1.5-1.9.5-5.8.5-5.8s0-3.9-.5-5.8zM9.75 15.5v-7l6.25 3.5-6.25 3.5z"/></svg>
            YouTube'a Yükle
          </button>
        </div>
      </div>
    </div>
  ` : `
    <div class="card">
      <div class="card-title">YouTube</div>
      <p style="color:var(--muted);font-size:13px">YouTube'a yüklemek için bağlanın (sol panel → YouTube Yükleme Ayarları).</p>
    </div>
  `;

  panel.innerHTML = `
    <div class="card">
      <div class="card-title">
        Üretim Durumu
        <span class="status-badge status-completed" style="float:right">Tamamlandı</span>
      </div>
      <div class="result-box">
        <div class="big-check">🎉</div>
        <div class="result-title">Video Hazır!</div>
        <div class="result-sub">
          ${job.scenes.length} sahne · ${selectedFormat === 'shorts' ? '1080×1920 Shorts' : '1920×1080 Yatay'}
        </div>
        <div class="result-actions">
          <a class="btn btn-primary" href="/api/video/download/${job.job_id}" download>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            MP4 İndir
          </a>
          <button class="btn btn-outline" onclick="startGenerate()">Yeni Video</button>
        </div>
      </div>
    </div>
    ${ytSection}
    ${renderScenes(job.scenes)}
  `;
}

function renderFailed(err) {
  document.getElementById('rightPanel').innerHTML = `
    <div class="card">
      <div class="card-title">
        Üretim Durumu
        <span class="status-badge status-failed" style="float:right">Hata</span>
      </div>
      <div class="error-box">${escHtml(err)}</div>
      <button class="btn btn-outline" style="margin-top:16px" onclick="resetView()">Tekrar Dene</button>
    </div>
  `;
}

// ── YouTube upload ───────────────────────────────────────────────────────────
async function uploadToYoutube(jobId) {
  const titleEl = document.getElementById('ytTitle');
  const title = titleEl ? titleEl.value.trim() : document.getElementById('title').value.trim();
  const privacy = document.getElementById('ytPrivacy').value;
  const description = document.getElementById('ytDesc').value;
  const tags = document.getElementById('ytTags').value
    .split(',').map(s => s.trim()).filter(Boolean);

  try {
    const r = await fetch('/api/youtube/upload', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: jobId, title, description, tags, privacy, category_id: '22' }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || 'Yükleme hatası');

    showToast(`YouTube'a yüklendi! ${d.youtube_url}`, 'success');
    // Linki sayfada göster
    const ytPanel = document.querySelector('.yt-panel');
    if (ytPanel) {
      ytPanel.insertAdjacentHTML('beforeend', `
        <a href="${d.youtube_url}" target="_blank" class="btn btn-outline" style="margin-top:8px">
          Videoyu YouTube'da Aç ↗
        </a>
      `);
    }
  } catch (e) {
    showToast('Hata: ' + e.message, 'error');
  }
}

// ── Yardımcılar ──────────────────────────────────────────────────────────────
function statusLabel(s) {
  return { pending: 'Bekliyor', processing: 'İşleniyor', completed: 'Tamamlandı', failed: 'Hata' }[s] || s;
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function escAttr(str) { return escHtml(str); }

function clearPoll() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

function resetGenerateBtn() {
  const btn = document.getElementById('btnGenerate');
  if (btn) {
    btn.disabled = false;
    btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg> Video Üret';
  }
}

function resetView() {
  document.getElementById('rightPanel').innerHTML = `
    <div class="empty-state" id="emptyState">
      <div class="icon">🎬</div>
      <div style="font-size:16px;font-weight:600;color:var(--text)">Hazır</div>
      <div>Metni girin ve "Video Üret" butonuna tıklayın.</div>
    </div>`;
}

function showToast(msg, type = 'info') {
  const el = document.createElement('div');
  el.style.cssText = `
    position:fixed;bottom:24px;right:24px;z-index:9999;
    background:${type === 'error' ? '#7f1d1d' : type === 'success' ? '#14532d' : '#1e1b4b'};
    color:${type === 'error' ? '#fca5a5' : type === 'success' ? '#86efac' : '#a5b4fc'};
    border-radius:10px;padding:14px 20px;max-width:380px;font-size:13px;
    box-shadow:0 8px 24px rgba(0,0,0,.4);line-height:1.5;
    animation:fadeIn .2s ease;
  `;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 5000);
}
