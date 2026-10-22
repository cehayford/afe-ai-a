import adapter from '@sveltejs/adapter-node';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vitest/config';

export default defineConfig({
	plugins: [
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},
			// Node server: the frontend keeps sign-in tokens server-side and calls the API.
			adapter: adapter(),
			// Content security policy. SvelteKit adds hashes for its own inline start-up script.
			csp: {
				mode: 'auto',
				directives: {
					'default-src': ['self'],
					'script-src': ['self'],
					// Svelte and Leaflet set inline styles.
					'style-src': ['self', 'unsafe-inline'],
					// Listing photos come from the CDN; map tiles from OpenStreetMap; camera previews are blobs.
					// (Local development adds the local API's http address in src/hooks.server.ts.)
					'img-src': ['self', 'data:', 'blob:', 'https:'],
					'connect-src': ['self'],
					'font-src': ['self'],
					'worker-src': ['self'],
					'object-src': ['none'],
					'base-uri': ['self'],
					'frame-ancestors': ['none'],
					// Forms post to this site; payments continue on the partner's hosted checkout.
					'form-action': ['self', 'https://checkout.paystack.com']
				}
			}
		})
	],
	test: {
		include: ['src/**/*.test.ts']
	}
});
