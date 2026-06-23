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

// Üretim akışı — instagram.html ve youtube.html aynı form ID'lerini kullanır.
// Başarılıysa üretilen video bilgisini döndürür; hatayı net biçimde gösterir.
let lastGenerated = null;

async function runGenerate() {
  const btn = document.getElementById('genBtn');
  btn.disabled = true; btn.innerHTML = '<span class="spin"></span>Üretiliyor… (1-3 dk)';
  msg('genMsg', 'info', 'Trend seçiliyor, seslendirme ve video hazırlanıyor…');

  const fd = new FormData();
  fd.append('topic', document.getElementById('topic').value);
  fd.append('lang', document.getElementById('lang').value);
  fd.append('voice', document.getElementById('voice').value);
  fd.append('region', document.getElementById('region').value);

  const { j } = await api('/api/generate', { method: 'POST', body: fd });
  btn.disabled = false; btn.innerHTML = '▶ Üret (Test)';

  if (!j.ok) {
    lastGenerated = null;
    msg('genMsg', 'err', 'Üretim başarısız:\n' + (j.error || 'Bilinmeyen hata'));
    return null;
  }
  lastGenerated = j;
  msg('genMsg', 'ok', 'Video üretildi ✓ (' + (j.scene_count || '?') + ' sahne)');
  document.getElementById('resultCard').classList.remove('hide');
  document.getElementById('r_title').value = j.title || '';
  document.getElementById('r_tags').value = j.tags || '';
  document.getElementById('r_desc').value = j.description || '';
  const v = document.getElementById('preview'); v.src = j.video_url; v.load();
  msg('warnMsg', j.warning ? 'warn' : '', j.warning ? ('⚠ ' + j.warning) : '');
  msg('pubMsg', '', '');
  return j;
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
