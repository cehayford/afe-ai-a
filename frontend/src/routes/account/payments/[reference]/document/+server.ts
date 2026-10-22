// A fee's PDF for the person who paid it: an invoice while it waits, a receipt once paid. Never cached.
import { error } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ locals, params }) => {
	if (!locals.me) error(401, 'Sign in first.');
	if (!/^AFE-[A-Z]+-[0-9A-Z-]{1,40}$/.test(params.reference)) error(404, 'Not found.');
	const res = await locals.api.forward('GET', `/payments/${params.reference}/document`, {});
	if (!res.ok) error(res.status === 404 ? 404 : 502, 'Could not open the file.');
	return new Response(res.body, {
		headers: {
			'Content-Type': 'application/pdf',
			'Content-Disposition': `inline; filename="${params.reference}.pdf"`,
			'Cache-Control': 'no-store',
			'X-Content-Type-Options': 'nosniff'
		}
	});
};
