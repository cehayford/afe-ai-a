// Development stand-in for the escrow partner's hosted checkout. The API only accepts the
// matching "pay" call in debug mode with the TestEscrow partner.
import { redirect } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import type { Tenancy } from '$lib/api/types';
import { formError, load404, requireMe } from '$lib/server/guards';

export const load: PageServerLoad = async ({ locals, params, url }) => {
	requireMe(locals.me, url);
	return {
		tenancy: await load404(locals.api.get<Tenancy>(`/tenancies/${params.reference}`))
	};
};

export const actions: Actions = {
	default: async ({ locals, params }) => {
		try {
			await locals.api.post(`/tenancies/test/${params.reference}/pay`);
		} catch (err) {
			return formError(err);
		}
		redirect(303, `/tenancies/${params.reference}`);
	}
};
