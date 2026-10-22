import { redirect } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import type { IdentityCheck, MyUnit, Payee, Pricing } from '$lib/api/types';
import { formError, str } from '$lib/server/guards';

// The four steps of "Get verified" read their state from here: identity, documents, payout, visit.
export const load: PageServerLoad = async ({ locals }) => {
	const [check, homes, payee, pricing] = await Promise.all([
		locals.api.get<IdentityCheck | null>('/kyc/ghana-card'),
		locals.api.get<MyUnit[]>('/me/units'),
		locals.api.get<Payee | null>('/me/payouts').catch(() => null),
		locals.api.get<Pricing>('/pricing').catch(() => null)
	]);
	return { check, homes, payee, free: Boolean(pricing?.launch_offer) };
};

export const actions: Actions = {
	default: async ({ request, locals }) => {
		const form = await request.formData();
		const body = new FormData();
		body.set('card_number', str(form, 'card_number'));
		body.set('full_name', str(form, 'full_name'));
		const selfie = form.get('selfie');
		if (selfie instanceof File && selfie.size > 0) body.set('selfie', selfie, selfie.name || 'selfie.jpg');
		try {
			await locals.api.post<IdentityCheck>('/kyc/ghana-card', body);
		} catch (err) {
			return formError(err, { card_number: str(form, 'card_number'), full_name: str(form, 'full_name') });
		}
		redirect(303, '/landlord/verify');
	}
};
