import { redirect } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import type { ListingDetail, Payment } from '$lib/api/types';
import { formError, load404, str } from '$lib/server/guards';

export const load: PageServerLoad = async ({ locals, params }) => {
	const { data, meta } = await load404(locals.api.withMeta<ListingDetail>(`/properties/listings/${params.id}`));
	return { listing: data, blockers: (meta.blockers as string[]) ?? [], flags: (meta.flags as string[]) ?? [] };
};

export const actions: Actions = {
	save: async ({ request, locals, params }) => {
		const form = await request.formData();
		try {
			await locals.api.patch(`/properties/listings/${params.id}`, {
				title: str(form, 'title'),
				description: str(form, 'description'),
				rent_ghs: str(form, 'rent_ghs'),
				advance_months: Number(str(form, 'advance_months')),
				min_lease_months: Number(str(form, 'min_lease_months')),
				available_from: str(form, 'available_from')
			});
			return { saved: true };
		} catch (err) {
			return formError(err);
		}
	},
	submit: async ({ locals, params }) => {
		try {
			await locals.api.post(`/properties/listings/${params.id}/submit`);
			return { submitted: true };
		} catch (err) {
			return formError(err);
		}
	},
	feature: async ({ locals, params }) => {
		let payment: Payment;
		try {
			payment = await locals.api.post<Payment>(`/properties/listings/${params.id}/feature`);
		} catch (err) {
			return formError(err);
		}
		// During the launch offer there's no checkout: the listing is featured at once.
		redirect(303, payment.checkout_url || `/landlord/listings/${params.id}?featured=1`);
	},
	archive: async ({ locals, params }) => {
		try {
			await locals.api.post(`/properties/listings/${params.id}/archive`);
		} catch (err) {
			return formError(err);
		}
		redirect(303, '/landlord');
	}
};
