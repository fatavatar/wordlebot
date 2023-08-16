// simple pwa config

var cacheVersion = new Date().getTime();
var staticCacheName = "wordlebot-v" + cacheVersion

var filesToCache = [
    '/',
    '/offline',
    '/static/images/icons/favicon.ico',
    '/static/images/icons/android-chrome-192x192.png',
    '/static/images/icons/android-chrome-512x512.png',
    '/static/images/icons/apple-touch-icon.png',
];

// Cache on install
self.addEventListener("install", event => {
  this.skipWaiting();
  event.waitUntil(
    caches.open(staticCacheName)
      .then(cache => {
        return cache.addAll(filesToCache);
      })
  )
});



self.addEventListener('visibilitychange', function() {
    if (document.visibilityState === 'visible') {
        console.log('APP resumed');
        window.location.reload();
    }
});

self.addEventListener('notificationclick', function (event)
{
  console.log("Got Event!")
    //For root applications: just change "'./'" to "'/'"
    //Very important having the last forward slash on "new URL('./', location)..."
    // const rootUrl = new URL('/', location).href; 
    event.notification.close();
    event.waitUntil(clients.openWindow(event.notification.data.url));

    // event.waitUntil(
    //     clients.matchAll().then(matchedClients =>
    //     {
    //         for (let client of matchedClients)
    //         {
    //             if (client.url.indexOf(rootUrl) >= 0)
    //             {
    //                 return client.focus();
    //             }
    //         }

    //         return clients.openWindow(rootUrl).then(function (client) { client.focus(); });
    //     })
    // );
});

// Clear cache on activate
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames
          .filter(cacheName => (cacheName.startsWith("wordlebot-")))
          .filter(cacheName => (cacheName !== staticCacheName))
          .map(cacheName => caches.delete(cacheName))
      );
    })
  );
});

async function cleanRedirect(response) {
  const clonedResponse = response.clone();

  return new Response(await clonedResponse.blob(), {
    headers: clonedResponse.headers,
    status: clonedResponse.status,
    statusText: clonedResponse.statusText,
  });
}

// Serve from cache, and return offline page if client is offline 
this.addEventListener('fetch', event => {
  if (event.response.type === 'opaqueredirect') {
    return event.respondWith(cleanRedirect(event.response))
  }
  if (event.request.mode === 'navigate' || (event.request.method === 'GET' && event.request.headers.get('accept').includes('text/html'))) {
    event.respondWith(
      fetch(event.request.url).catch(error => {
        return caches.match('/offline');
      })
    );
  } else{
    event.respondWith(caches.match(event.request)
        .then(function (response) {
        return response || fetch(event.request);
      })
    );
  }
});

