const CACHE_NAME = 'clocksimulator-v1.3.7';
const ASSETS = [
  '/',
  '/digital/',
  '/privacy',
  '/TOS',
  '/sitemap.xml',
  '/manifest.json',
  '/apple-touch-icon.png',
  '/android-chrome-192x192.png',
  '/android-chrome-512x512.png',
  '/og-image.png'
];
const LEGACY_PAGE_ALIASES = {
  '/privacy.html': '/privacy',
  '/TOS.html': '/TOS'
};

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function (cache) {
      return cache.addAll(ASSETS);
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys
          .filter(function (key) {
            return key !== CACHE_NAME && key.indexOf('clocksimulator-v') === 0;
          })
          .map(function (key) { return caches.delete(key); })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', function (event) {
  if (event.request.method !== 'GET') {
    event.respondWith(fetch(event.request));
    return;
  }

  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request).catch(function () {
        const url = new URL(event.request.url);
        const cacheKey = LEGACY_PAGE_ALIASES[url.pathname] || event.request;
        return caches.open(CACHE_NAME).then(function (cache) {
          return cache.match(cacheKey, { ignoreSearch: true }).then(function (cached) {
            if (cached) {
              return cached;
            }
            if (url.pathname === '/digital' || url.pathname.indexOf('/digital/') === 0) {
              return cache.match('/digital/');
            }
            return cache.match('/');
          });
        });
      })
    );
    return;
  }

  event.respondWith(
    caches.open(CACHE_NAME).then(function (cache) {
      return cache.match(event.request).then(function (cached) {
        return cached || fetch(event.request).then(function (response) {
          if (!response.ok) {
            return response;
          }
          return Promise.resolve().then(function () {
            return cache.put(event.request, response.clone());
          }).catch(function () { }).then(function () {
            return response;
          });
        });
      });
    }, function () {
      return fetch(event.request);
    })
  );
});
