/// <reference types="@sveltejs/kit" />
/// <reference no-default-lib="true"/>
/// <reference lib="esnext" />
/// <reference lib="webworker" />

// Keeps the app shell and the field pages usable when the signal drops. API calls and
// signed-in pages outside /field are never cached.
import { build, files, version } from '$service-worker';

const sw = self as unknown as ServiceWorkerGlobalScope;
const CACHE = `afe-${version}`;
const SHELL = [...build, ...files];

sw.addEventListener('install', (event) => {
	event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => sw.skipWaiting()));
});

sw.addEventListener('activate', (event) => {
	event.waitUntil(
		caches
			.keys()
			.then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
			.then(() => sw.clients.claim())
	);
});

sw.addEventListener('fetch', (event) => {
	const req = event.request;
	const url = new URL(req.url);
	if (req.method !== 'GET' || url.origin !== sw.location.origin) return;

	if (SHELL.includes(url.pathname)) {
		event.respondWith(caches.match(url.pathname).then((hit) => hit ?? fetch(req)));
		return;
	}

	// Field pages: network first, fall back to the last copy seen on this phone.
	if (url.pathname.startsWith('/field') && !url.pathname.startsWith('/api/')) {
		event.respondWith(
			fetch(req)
				.then((res) => {
					if (res.ok && !res.redirected) {
						const copy = res.clone();
						caches.open(CACHE).then((c) => c.put(req, copy));
					}
					return res;
				})
				.catch(async () => {
					const hit = await caches.match(req);
					return (
						hit ??
						new Response(
							"<p style='font-family:sans-serif;padding:16px'>You are offline and this page isn't saved on your phone yet. Photos you took are safe; open the visit again when you have signal.</p>",
							{ headers: { 'Content-Type': 'text/html; charset=utf-8' } }
						)
					);
				})
		);
	}
});
