// The tenant's move-in photo: private evidence, for the two parties and reviewers only.
import { error } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ locals, params }) => {
	if (!locals.me) error(401, 'Sign in to see the photo.');
	if (!/^AFE-T-[0-9A-F]{6}$/i.test(params.reference)) error(404, 'Not found.');
	const res = await locals.api.forward('GET', `/tenancies/${params.reference}/move-in-photo`, {});
	if (!res.ok) error(res.status === 404 ? 404 : 502, 'Could not open the photo.');
	return new Response(res.body, {
		headers: { 'Content-Type': 'image/webp', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' }
	});
};
