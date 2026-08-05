// Sürüm değişince activate eski önbellekleri siler — arayüz güncellemesi
// takılı kalmasın diye her önemli değişiklikte bu numarayı artır.
const CACHE = 'hbbot-v2';

const SHELL = [
  '/static/index.html',
  '/static/login.html',
  '/static/manifest.json',
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// HTML mi istiyoruz? (sayfa gezinmesi veya .html isteği)
function isHtml(request, url) {
  return request.mode === 'navigate'
    || url.pathname.endsWith('.html')
    || (request.headers.get('accept') || '').includes('text/html');
}

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);

  // Dış kaynaklar ve API istekleri → doğrudan ağ
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/')) return;
  if (url.pathname.startsWith('/haberler')) return;

  if (isHtml(e.request, url)) {
    // HTML → ÖNCE AĞ. Eskiden önce-önbellek yapılıyordu ve önbellek adı hiç
    // değişmediği için panel güncellemeleri kullanıcıya hiç ulaşmıyordu
    // (yeni ses seçenekleri, yeni ayarlar vb. görünmüyordu).
    // Ağ yanıtı taze kopyayı önbelleğe yazar; çevrimdışıyken son kopya sunulur.
    e.respondWith(
      fetch(e.request)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(e.request, copy)).catch(() => {});
          return res;
        })
        .catch(() => caches.match(e.request).then((c) => c || caches.match('/static/index.html')))
    );
    return;
  }

  // İkon/görsel gibi değişmeyen varlıklar → önce önbellek (hızlı açılış)
  e.respondWith(
    caches.match(e.request).then(
      (cached) => cached || fetch(e.request).catch(() => cached)
    )
  );
});
