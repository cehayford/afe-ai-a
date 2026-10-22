// Stream a private authority document to a signed-in reviewer. The API checks the role
// and logs the read; the frontend adds the reviewer's token and never caches the file.
import { error } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ locals, params }) => {
	if (!locals.me || !['reviewer', 'admin'].includes(locals.me.user.role)) error(403, 'Reviewers only.');
	if (!/^\d+$/.test(params.id)) error(404, 'Not found.');
	const res = await locals.api.forward('GET', `/review/authority/${params.id}/document`, {});
	if (!res.ok) error(res.status === 404 ? 404 : 502, 'Could not open the document.');
	return new Response(res.body, {
		headers: {
			'Content-Type': res.headers.get('content-type') ?? 'application/octet-stream',
			'Content-Disposition': res.headers.get('content-disposition') ?? 'inline',
			'Cache-Control': 'no-store',
			'X-Content-Type-Options': 'nosniff'
		}
	});
};
