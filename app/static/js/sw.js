const CACHE_VERSION = 'wt-v2';
const STATIC_ASSETS = [
  '/static/css/nyt-theme.css',
  '/static/js/app.js',
  '/static/manifest.json',
  '/static/offline.html',
];

// Install: cache static assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

// Activate: clean up old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_VERSION).map((k) => caches.delete(k)))
    )
  );
  return self.clients.claim();
});

// Fetch: pass everything through to the network
self.addEventListener('fetch', (event) => {
  event.respondWith(fetch(event.request));
});

// Push notification handler
self.addEventListener('push', (event) => {
  if (!event.data) return;
  let data;
  try {
    data = event.data.json();
  } catch {
    data = { title: 'Wordle Tournament', body: event.data.text(), url: '/' };
  }
  event.waitUntil(
    self.registration.showNotification(data.title || 'Wordle Tournament', {
      body: data.body || '',
      icon: '/static/icons/icon-192.png',
      badge: '/static/icons/icon-192.png',
      data: { url: data.url || '/' },
    })
  );
});

// Notification click: open the URL
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = event.notification.data && event.notification.data.url ? event.notification.data.url : '/';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if (client.url === url && 'focus' in client) return client.focus();
      }
      return self.clients.openWindow(url);
    })
  );
});
