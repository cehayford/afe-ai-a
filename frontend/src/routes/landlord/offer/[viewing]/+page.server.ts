import { redirect } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import type { Payee, Quote, Tenancy, TenancyConfig, Viewing } from '$lib/api/types';
import { formError, str } from '$lib/server/guards';

export const load: PageServerLoad = async ({ locals, params }) => {
	const [config, payee, viewings] = await Promise.all([
		locals.api.get<TenancyConfig>('/tenancies/config'),
		locals.api.get<Payee | null>('/me/payouts'),
		locals.api.get<Viewing[]>('/viewings')
	]);
	const viewing = viewings.find((v) => String(v.id) === params.viewing && v.role === 'lister');
	if (!viewing) redirect(303, '/account/viewings');
	return { config, payee, viewing };
};

function terms(form: FormData, viewing: string) {
	return {
		viewing_id: Number(viewing),
		move_in_date: str(form, 'move_in_date'),
		lease_months: Number(str(form, 'lease_months')),
		advance_months: Number(str(form, 'advance_months')),
		deposit_months: Number(str(form, 'deposit_months'))
	};
}

export const actions: Actions = {
	quote: async ({ locals, params, request }) => {
		const body = terms(await request.formData(), params.viewing);
		try {
			return {
				quote: await locals.api.post<Quote>('/tenancies/quote', body),
				terms: body
			};
		} catch (err) {
			return formError(err, { terms: body });
		}
	},
	offer: async ({ locals, params, request }) => {
		const body = terms(await request.formData(), params.viewing);
		let t: Tenancy;
		try {
			t = await locals.api.post<Tenancy>('/tenancies', body);
		} catch (err) {
			return formError(err, { terms: body });
		}
		redirect(303, `/tenancies/${t.reference}`);
	}
};
