import type { RequestEvent } from '@sveltejs/kit';

/** Record a product event (plan §13 metrics). Never blocks or breaks the page. */
export function track(event: RequestEvent, name: string, props: Record<string, string | number | boolean> = {}): void {
	let anon = event.cookies.get('afe_aid');
	if (!anon) {
		anon = crypto.randomUUID();
		event.cookies.set('afe_aid', anon, { path: '/', httpOnly: true, sameSite: 'lax', maxAge: 60 * 60 * 24 * 365 });
	}
	event.locals.api
		.post('/events', { name, anonymous_id: anon, path: event.url.pathname, props })
		.catch(() => {});
}
