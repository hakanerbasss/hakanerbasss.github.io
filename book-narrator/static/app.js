'use strict';

let selectedFile = null;
let pollTimer = null;
let voices = [];
let languages = [];
let dsConfigured = false;
let pxConfigured = false;

document.addEventListener('DOMContentLoaded', () => {
  loadSettings();
  loadVoices();
  loadJobs();
  initDropZone();
});

// ── Ayarlar ──────────────────────────────────────────────────────────────────
async function loadSettings() {
  try {
    const r = await fetch('/api/settings');
    const d = await r.json();
    dsConfigured = d.deepseek_configured;
    pxConfigured = d.pexels_configured;

    if (d.deepseek_key) document.getElementById('deepseekKey').placeholder = d.deepseek_key;
    if (d.pexels_key)   document.getElementById('pexelsKey').placeholder   = d.pexels_key;

    const dsDot = document.getElementById('dsStatus');
    const pxDot = document.getElementById('pxStatus');
    if (dsDot) dsDot.className = 'api-dot ' + (dsConfigured ? 'dot-on' : 'dot-off');
    if (pxDot) pxDot.className = 'api-dot ' + (pxConfigured ? 'dot-on' : 'dot-off');

    // Settings badge
    const badge = document.getElementById('settingsBadge');
    if (badge) {
      if (dsConfigured && pxConfigured) {
        badge.textContent = '✓ Tümü aktif';
        badge.className = 'settings-badge badge-ok';
      } else if (dsConfigured || pxConfigured) {
        badge.textContent = '⚡ Kısmen aktif';
        badge.className = 'settings-badge badge-warn';
      } else {
        badge.textContent = 'API key girilmemiş';
        badge.className = 'settings-badge';
      }
    }

    // API key girilmemişse settings açık kalsın
    const details = document.getElementById('settingsDetails');
    if (details && (dsConfigured || pxConfigured)) {
      details.removeAttribute('open');
    } else if (details) {
      details.setAttribute('open', '');
    }

    // Dil seçenekleri doldur
    languages = d.languages || [];
    const srcSel = document.getElementById('sourceLang');
    const tgtSel = document.getElementById('targetLang');
    if (srcSel && languages.length) {
      srcSel.innerHTML = languages.map(l =>
        `<option value="${l.id}">${l.label}</option>`
      ).join('');
    }
    if (tgtSel && languages.length) {
      tgtSel.innerHTML = languages
        .filter(l => l.id !== 'auto')
        .map(l => `<option value="${l.id}"${l.id==='tr'?' selected':''}>${l.label}</option>`)
        .join('');
    }
    onLangChange();
  } catch {}
}

async function saveSettings() {
  const dsVal = document.getElementById('deepseekKey').value.trim();
  const pxVal = document.getElementById('pexelsKey').value.trim();
  try {
    const r = await fetch('/api/settings', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ deepseek_key: dsVal, pexels_key: pxVal }),
    });
    if (!r.ok) throw new Error();
    document.getElementById('deepseekKey').value = '';
    document.getElementById('pexelsKey').value   = '';
    toast('Ayarlar kaydedildi', 'success');
    await loadSettings();
  } catch {
    toast('Kayıt hatası', 'error');
  }
}

function onLangChange() {
  const src = document.getElementById('sourceLang')?.value || 'auto';
  const tgt = document.getElementById('targetLang')?.value || 'tr';
  const note = document.getElementById('langNote');
  if (!note) return;

  const srcLabel = languages.find(l => l.id === src)?.label || src;
  const tgtLabel = languages.find(l => l.id === tgt)?.label || tgt;

  if (src === tgt) {
    note.textContent = `✓ Kitap ${tgtLabel} dilinde — doğrudan seslendirilecek`;
    note.className = 'lang-note note-ok';
    note.style.display = 'block';
  } else if (src === 'auto') {
    note.textContent = `⚠ Kaynak dil seçilmedi. Türkçe ses için soldaki listeden kitabın dilini seçin (örn: English) ve DeepSeek key girin.`;
    note.className = 'lang-note note-warn';
    note.style.display = 'block';
  } else if (!dsConfigured) {
    note.textContent = `⚠ ${srcLabel} → ${tgtLabel} çevirisi için DeepSeek API key gerekli (üstteki Ayarlar'dan girin). Şu an kitap ${srcLabel} dilinde seslendirilecek.`;
    note.className = 'lang-note note-warn';
    note.style.display = 'block';
  } else {
    note.textContent = `✓ DeepSeek ile ${srcLabel} → ${tgtLabel} çevirisi yapılacak`;
    note.className = 'lang-note note-ok';
    note.style.display = 'block';
  }
}

// ── Ses seçimi ────────────────────────────────────────────────────────────────
async function loadVoices() {
  try {
    const r = await fetch('/api/voices');
    const d = await r.json();
    voices = d.voices || [];
    const sel = document.getElementById('voiceSelect');
    sel.innerHTML = voices.map(v =>
      `<option value="${v.id}">${v.label} (${v.id})</option>`
    ).join('');
  } catch {
    document.getElementById('voiceSelect').innerHTML =
      '<option value="M1">Erkek 1 (M1)</option>';
  }
}

function onVoiceChange() {
  document.getElementById('previewWrap').style.display = 'none';
}

async function previewVoice() {
  const voice = document.getElementById('voiceSelect').value;
  if (!voice) return;
  const btn = document.getElementById('btnPreview');
  btn.disabled = true; btn.textContent = 'Üretiliyor...';
  try {
    const form = new FormData();
    form.append('voice', voice);
    const r = await fetch('/api/preview', { method: 'POST', body: form });
    if (!r.ok) { const e = await r.json(); throw new Error(e.detail || 'Hata'); }
    const url = URL.createObjectURL(await r.blob());
    const audio = document.getElementById('previewAudio');
    audio.src = url;
    document.getElementById('previewWrap').style.display = 'flex';
    audio.play().catch(() => {});
    toast('Önizleme hazır', 'success');
  } catch (e) {
    toast('Hata: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg> Önizle`;
  }
}

// ── Dosya seçimi ─────────────────────────────────────────────────────────────
function initDropZone() {
  const zone = document.getElementById('dropZone');
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', e => {
    e.preventDefault(); zone.classList.remove('drag-over');
    const f = e.dataTransfer.files[0]; if (f) applyFile(f);
  });
}
function onFileSelect(input) { if (input.files[0]) applyFile(input.files[0]); }
function applyFile(file) {
  selectedFile = file;
  const label = document.getElementById('fileSelectedLabel');
  label.textContent = `✓ ${file.name}  (${fmtSize(file.size)})`;
  label.style.display = 'block';
  document.getElementById('btnUpload').disabled = false;
}

// ── Yükleme ───────────────────────────────────────────────────────────────────
async function uploadBook() {
  if (!selectedFile) return;
  const btn     = document.getElementById('btnUpload');
  const title   = document.getElementById('titleInput').value.trim();
  const voice   = document.getElementById('voiceSelect').value || 'M1';
  const srcLang = document.getElementById('sourceLang')?.value || 'auto';
  const tgtLang = document.getElementById('targetLang')?.value || 'tr';

  btn.disabled = true; btn.textContent = 'Yükleniyor...';

  const form = new FormData();
  form.append('file', selectedFile);
  form.append('title', title);
  form.append('voice', voice);
  form.append('source_lang', srcLang);
  form.append('target_lang', tgtLang);

  try {
    const r = await fetch('/api/jobs/upload', { method: 'POST', body: form });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || 'Yükleme hatası');
    selectedFile = null;
    document.getElementById('fileInput').value = '';
    document.getElementById('fileSelectedLabel').style.display = 'none';
    document.getElementById('titleInput').value = '';
    document.getElementById('btnUpload').disabled = true;
    toast(`"${d.title}" sıraya alındı`, 'success');
    await loadJobs(); startPoll();
  } catch (e) {
    toast('Hata: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg> Seslendir`;
  }
}

// ── Job listesi ───────────────────────────────────────────────────────────────
async function loadJobs() {
  try {
    const r = await fetch('/api/jobs');
    const d = await r.json();
    renderJobs(d.jobs || []);
    const hasActive = (d.jobs || []).some(j => j.status === 'pending' || j.status === 'processing');
    if (hasActive) startPoll(); else stopPoll();
  } catch {}
}
function startPoll() { if (pollTimer) return; pollTimer = setInterval(loadJobs, 3000); }
function stopPoll()  { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } }

function renderJobs(jobs) {
  const el = document.getElementById('jobList');
  if (!jobs.length) {
    el.innerHTML = `<div class="empty"><div class="empty-icon">🎙️</div><div class="empty-title">Henüz sesli kitap yok</div><div>Kitap yükleyerek başlayın</div></div>`;
    return;
  }
  el.innerHTML = `<div class="jobs-list">${jobs.map(jobCard).join('')}</div>`;
}

function jobCard(j) {
  const STATUS = {
    pending:    ['s-pending',    'Sırada'],
    processing: ['s-processing', 'İşleniyor'],
    paused:     ['s-paused',     'Duraklatıldı'],
    completed:  ['s-completed',  'Tamamlandı'],
    failed:     ['s-failed',     'Hata'],
  };
  const [cls, label] = STATUS[j.status] || ['s-pending', j.status];
  const voiceLabel = voices.find(v => v.id === j.voice)?.label || j.voice || 'M1';
  const langLabel  = languages.find(l => l.id === j.target_lang)?.label || j.target_lang || '';

  const isActive = j.status === 'processing' || j.status === 'pending';
  const isPaused = j.status === 'paused';
  const isDone   = j.status === 'completed';

  const progressBar = (isActive || isPaused) ? `
    <div class="progress-wrap">
      <div class="progress-info">
        <span class="progress-msg">${j.done || 0} / ${j.total || '?'} parça</span>
        <span class="progress-pct">${j.progress || 0}%</span>
      </div>
      <div class="progress-bg">
        <div class="progress-fill${isPaused ? ' paused' : ''}" style="width:${j.progress||0}%"></div>
      </div>
    </div>` : '';

  const audioPlayer = isDone && j.output_path ? `
    <div class="job-audio">
      <audio controls src="/api/jobs/${j.id}/download" preload="none"></audio>
    </div>` : '';

  const metaBox = isDone && j.youtube_metadata ? buildMetaBox(j.youtube_metadata) : '';
  const actions = buildActions(j);
  const error   = j.error ? `<div class="error-text">⚠ ${esc(j.error)}</div>` : '';

  return `<div class="job-card">
    <div class="job-top">
      <span class="job-title" title="${esc(j.title)}">${esc(j.title)}</span>
      <div class="job-meta">
        <span class="job-fmt">${esc(j.file_format||'')}</span>
        <span class="job-voice">${esc(voiceLabel)}</span>
        ${langLabel ? `<span class="job-lang">${esc(langLabel)}</span>` : ''}
        <span class="status-badge ${cls}">${label}</span>
      </div>
    </div>
    ${progressBar}
    ${audioPlayer}
    ${error}
    ${actions ? `<div class="job-actions">${actions}</div>` : ''}
    ${metaBox}
  </div>`;
}

function buildActions(j) {
  let html = '';
  if (j.status === 'completed') {
    if (j.output_path)       html += `<a class="btn btn-dl btn-sm" href="/api/jobs/${j.id}/download" download>⬇ MP3</a>`;
    if (j.output_video_path) html += `<a class="btn btn-dl-video btn-sm" href="/api/jobs/${j.id}/video" download>🎬 MP4</a>`;
    if (j.output_srt_path)   html += `<a class="btn btn-ghost btn-sm" href="/api/jobs/${j.id}/srt" download>📄 SRT</a>`;
  }
  if (j.status === 'processing' || j.status === 'pending')
    html += `<button class="btn btn-pause btn-sm" onclick="pauseJob('${j.id}')">⏸ Duraklat</button>`;
  if (j.status === 'paused')
    html += `<button class="btn btn-resume btn-sm" onclick="resumeJob('${j.id}')">▶ Devam</button>`;
  html += `<button class="btn btn-danger btn-sm" onclick="deleteJob('${j.id}')">✕ Sil</button>`;
  return html;
}

function buildMetaBox(metaJson) {
  try {
    const m = JSON.parse(metaJson);
    return `<details class="meta-box">
      <summary>📋 YouTube Metadata</summary>
      <div class="meta-section"><strong>Başlık</strong>${esc(m.title||'')}</div>
      <div class="meta-section"><strong>Açıklama</strong><pre>${esc(m.description||'')}</pre></div>
      <div class="meta-section"><strong>Etiketler</strong>${esc((m.tags||[]).join(', '))}</div>
      <div class="meta-section"><strong>Hashtag</strong>${esc((m.hashtags||[]).join(' '))}</div>
    </details>`;
  } catch { return ''; }
}

// ── Eylemler ─────────────────────────────────────────────────────────────────
async function pauseJob(id) {
  try { await fetch(`/api/jobs/${id}/pause`, { method: 'POST' }); toast('Duraklatıldı', 'info'); await loadJobs(); }
  catch (e) { toast('Hata: ' + e.message, 'error'); }
}
async function resumeJob(id) {
  try { await fetch(`/api/jobs/${id}/resume`, { method: 'POST' }); toast('Devam...', 'success'); await loadJobs(); startPoll(); }
  catch (e) { toast('Hata: ' + e.message, 'error'); }
}
async function deleteJob(id) {
  if (!confirm('Bu işi ve dosyaları silmek istiyor musunuz?')) return;
  try { await fetch(`/api/jobs/${id}`, { method: 'DELETE' }); await loadJobs(); toast('Silindi', 'info'); }
  catch (e) { toast('Silinemedi: ' + e.message, 'error'); }
}

// ── Yardımcılar ───────────────────────────────────────────────────────────────
function esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function fmtSize(b) {
  return b < 1024 ? b+'B' : b < 1048576 ? (b/1024).toFixed(1)+'KB' : (b/1048576).toFixed(1)+'MB';
}
function toast(msg, type='info') {
  const c = {success:['#f0fdf4','#15803d','#86efac'], error:['#fef2f2','#b91c1c','#fca5a5'], info:['#eff6ff','#1d4ed8','#93c5fd']}[type]||['#f8fafc','#334155','#cbd5e1'];
  const el = document.createElement('div');
  el.className = 'toast';
  el.style.cssText = `background:${c[0]};color:${c[1]};border:1px solid ${c[2]}`;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}
