// "Download my data" (Act 843): stream the API's JSON export as a file.
import { error } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ locals }) => {
	if (!locals.me) error(401, 'Sign in to download your data.');
	const res = await locals.api.forward('GET', '/me/export', {});
	if (!res.ok) error(502, 'Could not prepare your data. Try again in a moment.');
	return new Response(res.body, {
		headers: {
			'Content-Type': 'application/json',
			'Content-Disposition': 'attachment; filename="afe-my-data.json"',
			'Cache-Control': 'no-store',
			'X-Content-Type-Options': 'nosniff'
		}
	});
};
