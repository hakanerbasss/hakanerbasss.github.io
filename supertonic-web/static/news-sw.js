const CACHE = 'hb-haberler-v1';

const SHELL = [
  '/static/news-manifest.json',
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

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);

  // Dış kaynaklar (AdSense, CDN) → doğrudan ağ
  if (url.origin !== self.location.origin) return;

  // API ve dinamik içerik → doğrudan ağ
  if (url.pathname.startsWith('/api/')) return;
  if (url.pathname.startsWith('/haberler')) return;

  // Statik dosyalar → önce önbellek
  e.respondWith(
    caches.match(e.request).then(
      (cached) => cached || fetch(e.request).catch(() => cached)
    )
  );
});
