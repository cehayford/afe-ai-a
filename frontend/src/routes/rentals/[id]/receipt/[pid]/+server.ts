// Private file for the landlord and tenant on this record; never cached.
import { error } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ locals, params }) => {
	if (!locals.me) error(401, 'Sign in first.');
	if (!/^\d+$/.test(params.id) || !/^\d+$/.test(params.pid)) error(404, 'Not found.');
	const res = await locals.api.forward('GET', `/rentals/${params.id}/payments/${params.pid}/receipt`, {});
	if (!res.ok) error(res.status === 404 ? 404 : 502, 'Could not open the file.');
	return new Response(res.body, {
		headers: { 'Content-Type': 'application/pdf', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' }
	});
};
