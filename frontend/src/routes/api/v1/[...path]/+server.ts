// Narrow proxy for browser-side calls that can't be form actions (the field app's offline
// photo queue). It forwards only field-visit endpoints and adds the signed-in person's
// token here on the server. SvelteKit rejects cross-site form posts (CSRF origin check),
// and JSON posts from other sites would need a CORS preflight that is never granted.
import { error } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

const ALLOWED = /^verify\/(worklist|assignments\/\d+|visits(\/\d+(\/photos|\/complete)?)?)$/;

const handler: RequestHandler = async ({ request, locals, params }) => {
	if (!locals.me) error(401, 'Sign in to continue.');
	if (!ALLOWED.test(params.path)) error(404, 'Not found.');
	const res = await locals.api.forward(request.method, `/${params.path}`, {
		body: request.method === 'GET' ? null : request.body,
		contentType: request.headers.get('content-type')
	});
	return new Response(res.body, {
		status: res.status,
		headers: { 'Content-Type': res.headers.get('content-type') ?? 'application/json', 'Cache-Control': 'no-store' }
	});
};

export const GET = handler;
export const POST = handler;
