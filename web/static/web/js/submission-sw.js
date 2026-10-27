/* Cache only the anonymous editor shell and public assets, never accounts/API. */
const CACHE = 'ott-submission-shell-v13';
const SHELL = '/ai/offline/';
const ASSETS = [SHELL, '/static/web/css/retro.css', '/static/web/css/retro-submit.css',
  '/static/web/js/retro.js', '/static/web/js/submission-offline.js'];
self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    const response = await fetch(SHELL, {cache: 'reload'});
    if (!response.ok) throw new Error('Offline shell unavailable');
    const html = await response.clone().text();
    // Production templates use hashed static URLs from collectstatic manifest.
    const hashed = [...html.matchAll(/(?:src|href)=["']([^"']+)["']/g)]
      .map(match => new URL(match[1], self.location.origin))
      .filter(url => url.origin === self.location.origin && url.pathname.startsWith('/static/'))
      .map(url => url.href);
    await cache.put(SHELL, response);
    const assets = [...ASSETS.slice(1), ...hashed].map(path => new URL(path, self.location.origin).href);
    await cache.addAll([...new Set(assets)]);
    await self.skipWaiting();
  })());
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key =>
    key.startsWith('ott-submission-shell-') && key !== CACHE).map(key => caches.delete(key))))
    .then(() => self.clients.claim()));
});
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (event.request.mode === 'navigate' && ['/ai/', SHELL].includes(url.pathname)) {
    event.respondWith(fetch(event.request).then(response => response.status >= 500
      ? caches.match(SHELL).then(cached => cached || response) : response).catch(() => caches.match(SHELL)));
  } else if (url.pathname.startsWith('/static/web/')) {
    event.respondWith(caches.match(event.request).then(cached => cached || fetch(event.request)));
  }
});
