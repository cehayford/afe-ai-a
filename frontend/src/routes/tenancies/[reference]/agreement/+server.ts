// Stream the tenancy summary PDF to the tenant or landlord. The API checks who may read it
// and logs every read; nothing is cached on the way.
import { error } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ locals, params }) => {
	if (!locals.me) error(401, 'Sign in to open the agreement.');
	if (!/^AFE-T-[0-9A-F]{6}$/i.test(params.reference)) error(404, 'Not found.');
	const res = await locals.api.forward('GET', `/tenancies/${params.reference}/agreement`, {});
	if (!res.ok) error(res.status === 404 ? 404 : 502, 'Could not open the agreement.');
	return new Response(res.body, {
		headers: {
			'Content-Type': 'application/pdf',
			'Content-Disposition': res.headers.get('content-disposition') ?? 'inline',
			'Cache-Control': 'no-store',
			'X-Content-Type-Options': 'nosniff'
		}
	});
};
