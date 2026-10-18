// Service worker: caches the app shell so the site opens offline / on a weak network.
// API answers are never cached here (they depend on time and place).
const CACHE = "seruen-v19-explanations";
const SHELL = ["./", "index.html", "about.html", "styles.css", "app.js", "route.js", "i18n.js", "config.js", "storage.js", "features.js", "manifest.json",
  "presets.json", "scenarios.json",
  "vendor/leaflet/leaflet.css", "vendor/leaflet/leaflet.js", "icons/icon.svg", "icons/icon-192.png"];
self.addEventListener("install", (e) => e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())));
self.addEventListener("activate", (e) => e.waitUntil(caches.keys().then((ks) =>
  Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (["/health", "/presets", "/scenarios"].includes(url.pathname)) return;  // always fresh
  e.respondWith(fetch(e.request).then((r) => {
    const copy = r.clone(); caches.open(CACHE).then((c) => c.put(e.request, copy)); return r;
  }).catch(() => caches.match(e.request)));
});
