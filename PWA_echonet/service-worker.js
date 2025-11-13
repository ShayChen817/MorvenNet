self.addEventListener("install", e => {
    e.waitUntil(
        caches.open("echonet-cache").then(cache => {
            return cache.addAll([
                "/",
                "/static/index.html",
                "/static/style.css",
                "/static/app.js",
                "/static/icon.png",
            ]);
        })
    );
});

self.addEventListener("fetch", e => {
    e.respondWith(
        caches.match(e.request).then(resp => resp || fetch(e.request))
    );
});
