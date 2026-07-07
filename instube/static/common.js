// InsTube — sayfalar arası paylaşılan yardımcılar

async function api(path, opts) {
  const r = await fetch(path, opts);
  let j = {};
  try { j = await r.json(); } catch (e) { j = { ok: false, error: 'Geçersiz yanıt' }; }
  return { status: r.status, j };
}

function msg(elId, kind, text) {
  const el = document.getElementById(elId);
  if (el) el.innerHTML = text ? `<div class="msg ${kind}">${text}</div>` : '';
}

// Üst gezinme çubuğu — #nav içine basılır
function renderNav(active) {
  const items = [
    ['/', 'Ana Sayfa', 'home'],
    ['/instagram.html', '📸 Instagram', 'ig'],
    ['/youtube.html', '▶️ YouTube + Instagram', 'yt'],
    ['/settings.html', '⚙️ Ayarlar', 'settings'],
  ];
  const el = document.getElementById('nav');
  if (el) el.innerHTML = items.map(([href, label, key]) =>
    `<a href="${href}" class="${key === active ? 'active' : ''}">${label}</a>`).join('');
}

// Durum rozetleri — #badges içine basılır
async function renderBadges() {
  const el = document.getElementById('badges');
  if (!el) return;
  const { j } = await api('/api/status');
  const item = (label, on) => `<span class="badge ${on ? 'on' : 'off'}">${on ? '✓' : '✗'} ${label}</span>`;
  el.innerHTML =
    item('DeepSeek', j.deepseek_set) +
    item('Pexels', j.pexels_set) +
    item('Instagram', j.instagram_set) +
    item('YouTube TR', j.youtube_tr) +
    item('YouTube EN', j.youtube_en);
}

// Üretim akışı — ARKA PLAN işi. "Üret"e basınca iş sunucuda başlar, bağlantıdan
// bağımsız sürer (telefon kapansa da devam eder). UI durumu 5sn'de bir yoklar.
let lastGenerated = null;
let pollTimer = null;

function setGenBusy(busy) {
  const btn = document.getElementById('genBtn');
  if (!btn) return;
  btn.disabled = busy;
  btn.innerHTML = busy ? '<span class="spin"></span>Üretiliyor…' : '▶ Üret (Test)';
}

function applyResult(d) {
  lastGenerated = d;
  document.getElementById('resultCard').classList.remove('hide');
  document.getElementById('r_title').value = d.title || '';
  document.getElementById('r_tags').value = d.tags || '';
  document.getElementById('r_desc').value = d.description || '';
  const v = document.getElementById('preview');
  v.src = d.video_url || ('/api/video/' + d.filename); v.load();
  msg('warnMsg', d.warning ? 'warn' : '', d.warning ? ('⚠ ' + d.warning) : '');
}

async function pollJob(jobId) {
  clearTimeout(pollTimer);
  const tick = async () => {
    const { j } = await api('/api/job/' + jobId);
    if (j.status === 'running') {
      setGenBusy(true);
      msg('genMsg', 'info', '⏳ Üretiliyor… arka planda devam ediyor. Telefonu kapatabilirsin; sonra bu sayfaya geri gelince sonuç burada olacak.');
      pollTimer = setTimeout(tick, 5000);
    } else if (j.status === 'done') {
      setGenBusy(false);
      applyResult(j.result);
      msg('genMsg', 'ok', 'Video üretildi ✓ (' + ((j.result && j.result.scene_count) || '?') + ' sahne)');
      msg('pubMsg', '', '');
    } else if (j.status === 'error') {
      setGenBusy(false);
      msg('genMsg', 'err', 'Üretim başarısız:\n' + (j.error || 'Bilinmeyen hata'));
    } else {
      setGenBusy(false);
    }
  };
  tick();
}

async function runGenerate() {
  setGenBusy(true);
  msg('genMsg', 'info', 'İş başlatılıyor…');
  const fd = new FormData();
  fd.append('topic', document.getElementById('topic').value);
  fd.append('lang', document.getElementById('lang').value);
  fd.append('voice', document.getElementById('voice').value);
  fd.append('region', document.getElementById('region').value);
  const { j } = await api('/api/generate', { method: 'POST', body: fd });
  if (!j.ok) { setGenBusy(false); msg('genMsg', 'err', j.error || 'Başlatılamadı'); return; }
  if (!j.started) msg('genMsg', 'info', 'Zaten bir üretim sürüyor — ona bağlanılıyor…');
  pollJob(j.job_id);
}

// Sayfa açılınca aktif/biten işi göster (geri gelince sonucu hazır bul)
async function resumeActiveJob() {
  const { j } = await api('/api/job');
  if (!j || j.status === 'none') return;
  if (j.status === 'running') {
    pollJob(j.id);
  } else if (j.status === 'done' && j.result) {
    applyResult(j.result);
    msg('genMsg', 'ok', 'Son üretim hazır ✓');
  } else if (j.status === 'error') {
    msg('genMsg', 'err', 'Son üretim başarısız:\n' + (j.error || ''));
  }
}


// Yayınlama sonucunu okunaklı biçimde yazdırır
function showPublishResult(j) {
  const lines = [];
  const res = j.results || {};
  if (res.youtube) {
    lines.push(res.youtube.ok
      ? '✓ YouTube: ' + (res.youtube.url || 'yüklendi')
      : '✗ YouTube: ' + res.youtube.error);
  }
  if (res.instagram) {
    lines.push(res.instagram.ok
      ? '✓ Instagram: yayınlandı (' + (res.instagram.media_id || '') + ')'
      : '✗ Instagram: ' + res.instagram.error);
  }
  if (!lines.length) lines.push(j.error || 'Sonuç yok');
  msg('pubMsg', j.ok ? 'ok' : 'err', lines.join('\n'));
}

function requireGenerated() {
  if (!lastGenerated || !lastGenerated.filename) {
    msg('pubMsg', 'err', 'Önce video üret.');
    return null;
  }
  return lastGenerated;
}
