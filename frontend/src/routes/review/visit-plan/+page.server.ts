import { fail } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import type { VisitPlan } from '$lib/api/types';
import { formError, str } from '$lib/server/guards';

export const load: PageServerLoad = async ({ locals, url }) => {
	const day = url.searchParams.get('day') ?? '';
	const q = /^\d{4}-\d{2}-\d{2}$/.test(day) ? `?day=${day}` : '';
	return { plan: await locals.api.get<VisitPlan>(`/review/visit-plan${q}`) };
};

export const actions: Actions = {
	assign: async ({ locals, request }) => {
		const form = await request.formData();
		const verifier = str(form, 'verifier_id');
		const units = form.getAll('unit_id').map(String).filter((v) => /^\d+$/.test(v));
		const day = str(form, 'day');
		if (!/^\d+$/.test(verifier) || !units.length || !/^\d{4}-\d{2}-\d{2}$/.test(day)) return fail(400, { error: 'Pick a route.' });
		try {
			const res = await locals.api.post<{ assigned: number; problems: string[] }>('/review/visit-plan/assign', {
				verifier_id: Number(verifier),
				unit_ids: units.map(Number),
				day
			});
			return { assigned: res.assigned, problems: res.problems };
		} catch (err) {
			return formError(err);
		}
	}
};
