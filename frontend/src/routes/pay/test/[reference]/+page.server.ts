// Development stand-in for the payment partner's hosted checkout. The API only allows the
// matching "complete" call when it runs in debug mode with the fake payment provider.
import { redirect } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import type { Payment } from '$lib/api/types';
import { formError, load404, requireMe } from '$lib/server/guards';

export const load: PageServerLoad = async ({ locals, params, url }) => {
	requireMe(locals.me, url);
	return { payment: await load404(locals.api.get<Payment>(`/payments/${params.reference}`)) };
};

export const actions: Actions = {
	default: async ({ locals, params }) => {
		let payment: Payment;
		try {
			payment = await locals.api.post<Payment>(`/payments/test/${params.reference}/complete`);
		} catch (err) {
			return formError(err);
		}
		redirect(
			303,
			payment.purpose === 'featured_listing'
				? '/landlord?featured=1'
				: payment.purpose === 'subscription'
					? '/landlord/rentals'
					: `/landlord/homes/${payment.unit_id}?payment=${payment.reference}`
		);
	}
};
