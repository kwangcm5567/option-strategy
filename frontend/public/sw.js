const CACHE_NAME = 'alpha-options-v2';
const APP_SHELL = ['/index.html'];

self.addEventListener('install', (event) => {
  // 跳过等待，立即激活新版本
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(APP_SHELL)).catch(() => {})
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  // API 请求永远走网络，不缓存
  if (event.request.url.includes('/api/')) return;
  // JS/CSS 资产走网络优先（hash 变了自然更新），fallback 到缓存
  const url = new URL(event.request.url);
  if (url.pathname.startsWith('/assets/')) {
    event.respondWith(
      fetch(event.request).catch(() => caches.match(event.request))
    );
    return;
  }
  // index.html：缓存优先（离线可用），但后台更新
  event.respondWith(
    caches.match(event.request).then(cached => {
      const network = fetch(event.request).then(res => {
        caches.open(CACHE_NAME).then(c => c.put(event.request, res.clone()));
        return res;
      });
      return cached || network;
    })
  );
});
