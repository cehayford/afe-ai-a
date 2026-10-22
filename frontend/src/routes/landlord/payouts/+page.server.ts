import type { Actions, PageServerLoad } from './$types';
import type { Payee, Tenancy } from '$lib/api/types';
import { formError, str } from '$lib/server/guards';

export const load: PageServerLoad = async ({ locals }) => {
	const [payee, tenancies] = await Promise.all([
		locals.api.get<Payee | null>('/me/payouts'),
		locals.api.get<Tenancy[]>('/tenancies').catch(() => [] as Tenancy[])
	]);
	return { payee, payouts: tenancies.filter((t) => t.role === 'landlord' && !['offered', 'funding'].includes(t.status)) };
};

export const actions: Actions = {
	default: async ({ locals, request }) => {
		const form = await request.formData();
		try {
			const payee = await locals.api.post<Payee>('/me/payouts', {
				channel: str(form, 'channel'),
				account_number: str(form, 'account_number'),
				code: str(form, 'code')
			});
			return { saved: payee };
		} catch (err) {
			return formError(err, {
				channel: str(form, 'channel'),
				account_number: str(form, 'account_number')
			});
		}
	}
};
