const CACHE = 'atik-rota-v6';
const SHELL = ['/static/css/app.css', '/static/js/app.js', '/static/manifest.json'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

// Yalnızca aynı kökenden gelen uygulama kabuğu isteklerini önbelleğe al
// API, harita karoları ve dış CDN istekleri doğrudan ağa gitsin.
// ÖNCE AĞ, sonra önbellek: eskiden önce-önbellek yapılıyordu ve önbellek
// adı değişmediği sürece app.js/app.css güncellemeleri kullanıcıya hiç
// ulaşmıyordu (Detay butonu eklendiğinde yaşandığı gibi). Ağ yanıtı taze
// kopyayı önbelleğe yazar; çevrimdışıyken son kopya sunulur.
self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/')) return;
  e.respondWith(
    fetch(e.request)
      .then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(e.request, copy)).catch(() => {});
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});
