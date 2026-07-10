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

self.addEventListener('push', (e) => {
  const data = e.data ? e.data.json() : {};
  e.waitUntil(
    self.registration.showNotification(data.title || 'Yeni Haber', {
      body: data.body || '',
      icon: data.icon || '/static/news-icons/icon-192.png',
      badge: '/static/news-icons/icon-192.png',
      data: { url: data.url || '/haberler' },
    })
  );
});

self.addEventListener('notificationclick', (e) => {
  e.notification.close();
  const url = e.notification.data?.url || '/haberler';
  e.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((wins) => {
      for (const w of wins) {
        if (w.url.includes(url) && 'focus' in w) return w.focus();
      }
      if (clients.openWindow) return clients.openWindow(url);
    })
  );
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
