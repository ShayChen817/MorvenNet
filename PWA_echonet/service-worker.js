self.addEventListener("install", event => {
    self.skipWaiting(); // activate new SW immediately
});

self.addEventListener("activate", event => {
    clients.claim(); // take control of existing pages
});

self.addEventListener("fetch", event => {
    event.respondWith(
        fetch(event.request)
            .then(response => response)
            .catch(() => caches.match(event.request))
    );
});
