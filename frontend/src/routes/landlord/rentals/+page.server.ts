import { redirect } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import type { MyUnit, PlanInfo, Rental } from '$lib/api/types';
import { formError, str } from '$lib/server/guards';

export const load: PageServerLoad = async ({ locals }) => {
	const [rentals, plan, homes, groups] = await Promise.all([
		locals.api.get<Rental[]>('/rentals'),
		locals.api.get<PlanInfo>('/rentals/plan'),
		locals.api.get<MyUnit[]>('/me/units'),
		locals.api.get<{ owner: string; homes: { id: number; address: string }[] }[]>('/rentals/agent-homes')
	]);
	return { rentals, plan, homes, groups };
};

export const actions: Actions = {
	add: async ({ locals, request }) => {
		const form = await request.formData();
		const values = {
			tenant_name: str(form, 'tenant_name'),
			tenant_phone: str(form, 'tenant_phone'),
			rent_ghs: Number(str(form, 'rent_ghs')),
			pay_every_months: Number(str(form, 'pay_every_months')),
			start_date: str(form, 'start_date'),
			end_date: str(form, 'end_date'),
			unit_id: str(form, 'unit_id') ? Number(str(form, 'unit_id')) : null
		};
		let id: number;
		try {
			id = (await locals.api.post<Rental>('/rentals', values)).id;
		} catch (err) {
			return formError(err);
		}
		redirect(303, `/rentals/${id}`);
	},
	plan: async ({ locals, request }) => {
		const plan = str(await request.formData(), 'plan');
		let res: { checkout_url: string; active: boolean };
		try {
			res = await locals.api.post(`/rentals/plan/${plan === 'pro' ? 'pro' : 'standard'}`);
		} catch (err) {
			return formError(err, { form: 'plan' });
		}
		if (res.checkout_url) redirect(303, res.checkout_url);
		return { planActive: true };
	}
};
