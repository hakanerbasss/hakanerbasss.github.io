// Ağ öncelikli: sayfa güncellenince kullanıcı hemen yenisini görür, internet yoksa önbellekten açılır.
const CACHE = 'cv-v1';
const SHELL = ['/cv/', '/cv/foto.jpg', '/cv/manifest.json', '/uygulamalarim/'];
self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => {}));
  self.skipWaiting();
});
self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))));
  self.clients.claim();
});
self.addEventListener('fetch', (e) => {
  const r = e.request;
  const url = new URL(r.url);
  if (r.method !== 'GET' || url.origin !== self.location.origin) return;
  if (!(url.pathname.startsWith('/cv/') || url.pathname.startsWith('/uygulamalarim/'))) return;
  e.respondWith(
    fetch(r).then((res) => {
      const copy = res.clone();
      caches.open(CACHE).then((c) => c.put(r, copy)).catch(() => {});
      return res;
    }).catch(() => caches.match(r))
  );
});
