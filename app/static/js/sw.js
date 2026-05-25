const CACHE_VERSION = 'wt-v1';
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

// Fetch: cache-first for static assets, network-first for navigation
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(event.request).then((cached) => cached || fetch(event.request))
    );
    return;
  }

  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request).catch(() =>
        caches.match('/static/offline.html').then(
          (r) => r || new Response('Offline', { status: 503 })
        )
      )
    );
    return;
  }
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
