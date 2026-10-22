import type { Handle, HandleServerError } from '@sveltejs/kit';
import { dev } from '$app/environment';
import { createApi, clearSession, ApiError } from '$lib/server/api';
import type { Me } from '$lib/api/types';

const DEVICE_COOKIE = 'afe_dev';

export const handle: Handle = async ({ event, resolve }) => {
	// A random ID per browser (no personal data). Accounts used on the same device are linked
	// for the trust team's fraud checks; see the privacy notice.
	if (!/^[0-9a-f-]{36}$/.test(event.cookies.get(DEVICE_COOKIE) ?? '')) {
		event.cookies.set(DEVICE_COOKIE, crypto.randomUUID(), {
			path: '/',
			httpOnly: true,
			sameSite: 'lax',
			secure: !dev,
			maxAge: 60 * 60 * 24 * 730
		});
	}
	event.locals.api = createApi(event);
	event.locals.me = null;

	if (event.locals.api.signedIn) {
		try {
			event.locals.me = await event.locals.api.get<Me>('/me');
		} catch (err) {
			if (err instanceof ApiError && err.status === 401) clearSession(event.cookies);
		}
	}

	const response = await resolve(event);
	response.headers.set('X-Content-Type-Options', 'nosniff');
	response.headers.set('X-Frame-Options', 'DENY');
	response.headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');
	// Location and camera are used by the field app only, on this site only.
	response.headers.set('Permissions-Policy', 'geolocation=(self), camera=(self), microphone=()');
	if (dev) allowLocalApi(response.headers);
	return response;
};

// Local development only: the API serves listing photos itself over plain http (AFE_MEDIA_URL defaults
// to http://127.0.0.1:8000/media), and Vite's dev client starts a blob: worker. Added here at request
// time because the policy in vite.config.ts is baked into .svelte-kit/generated whenever
// `svelte-kit sync` (svelte-check) or a build runs, so a dev-only switch there silently disappears.
const LOCAL_API = 'http://127.0.0.1:8000 http://localhost:8000';

function allowLocalApi(headers: Headers) {
	const csp = headers.get('content-security-policy');
	if (!csp) return;
	headers.set(
		'content-security-policy',
		csp.replace(/img-src([^;]*)/, `img-src$1 ${LOCAL_API}`).replace(/worker-src([^;]*)/, 'worker-src$1 blob:')
	);
}

export const handleError: HandleServerError = ({ error, status }) => {
	if (error instanceof ApiError) return { message: error.message, reasons: error.reasons };
	if (status === 404) return { message: 'Page not found.' };
	console.error(error);
	return { message: 'Something went wrong on our side. Please try again.' };
};
