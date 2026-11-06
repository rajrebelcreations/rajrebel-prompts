// RRC AI Prompts - service worker (keeps the app installable; always shows the latest site)
const CACHE = "rrc-v1";
self.addEventListener("install", (e) => { self.skipWaiting(); });
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const req = e.request;
  // only page loads on this site; Firebase, ads and everything else go straight to the network
  if (req.method !== "GET" || req.mode !== "navigate" || new URL(req.url).origin !== self.location.origin) return;
  e.respondWith(
    fetch(req).then(res => {
      if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put("/", copy)); }
      return res;
    }).catch(() => caches.match("/").then(r => r || Response.error()))
  );
});
