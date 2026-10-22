import { fail, redirect } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import type { Listing, MyUnit, Payment } from '$lib/api/types';
import { formError, load404, str } from '$lib/server/guards';
import { track } from '$lib/server/track';

export const load: PageServerLoad = async ({ locals, params, url }) => {
	const home = await load404(locals.api.get<MyUnit>(`/properties/units/${params.id}`));
	const reference = url.searchParams.get('payment');
	const payment = reference ? await locals.api.get<Payment>(`/payments/${reference}`).catch(() => null) : null;
	return { home, payment };
};

export const actions: Actions = {
	document: async ({ request, locals, params }) => {
		const form = await request.formData();
		const file = form.get('document');
		if (!(file instanceof File) || file.size === 0) return fail(400, { form: 'document', error: 'Choose the document file.' });
		const body = new FormData();
		for (const key of ['relationship', 'document_type', 'utility_reference']) body.set(key, str(form, key));
		body.set('document', file, file.name || 'document');
		try {
			await locals.api.post(`/kyc/units/${params.id}/authority`, body);
			return { uploaded: true };
		} catch (err) {
			return formError(err, { form: 'document' });
		}
	},

	pay: async (event) => {
		let payment: Payment;
		try {
			payment = await event.locals.api.post<Payment>('/payments/verification-fee', { unit_id: Number(event.params.id) });
		} catch (err) {
			return formError(err, { form: 'pay' });
		}
		track(event, 'fee_checkout_start');
		redirect(303, payment.checkout_url);
	},

	listing: async ({ request, locals, params }) => {
		const form = await request.formData();
		const values = {
			title: str(form, 'title'),
			description: str(form, 'description'),
			rent_ghs: str(form, 'rent_ghs'),
			advance_months: str(form, 'advance_months'),
			min_lease_months: str(form, 'min_lease_months'),
			available_from: str(form, 'available_from')
		};
		let listing: Listing;
		try {
			listing = await locals.api.post<Listing>('/properties/listings', {
				...values,
				unit_id: Number(params.id),
				advance_months: Number(values.advance_months),
				min_lease_months: Number(values.min_lease_months)
			});
		} catch (err) {
			return formError(err, { form: 'listing', ...values });
		}
		redirect(303, `/landlord/listings/${listing.id}`);
	}
};
