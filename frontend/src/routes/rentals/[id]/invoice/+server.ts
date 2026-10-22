// The next rent due as a PDF invoice, for the landlord and the tenant on this record. Never cached.
import { error } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ locals, params }) => {
	if (!locals.me) error(401, 'Sign in first.');
	if (!/^\d+$/.test(params.id)) error(404, 'Not found.');
	const res = await locals.api.forward('GET', `/rentals/${params.id}/invoice`, {});
	if (!res.ok) error(res.status === 404 ? 404 : res.status === 409 ? 409 : 502, 'Could not open the file.');
	return new Response(res.body, {
		headers: {
			'Content-Type': 'application/pdf',
			'Content-Disposition': `inline; filename="rent-invoice-${params.id}.pdf"`,
			'Cache-Control': 'no-store',
			'X-Content-Type-Options': 'nosniff'
		}
	});
};
