import { fail } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import type { Dispute, Finance, Mismatch, Tenancy } from '$lib/api/types';
import { formError, str } from '$lib/server/guards';

export const load: PageServerLoad = async ({ locals }) => {
	const [queue, disputes, finance] = await Promise.all([
		locals.api.get<Tenancy[]>('/review/tenancies'),
		locals.api.get<Dispute[]>('/review/disputes'),
		locals.api.withMeta<Finance>('/review/finance')
	]);
	return {
		queue,
		disputes,
		finance: finance.data,
		mismatches: (finance.meta.mismatches as Mismatch[]) ?? []
	};
};

export const actions: Actions = {
	release: async ({ locals, request }) => {
		const form = await request.formData();
		const ref = str(form, 'reference');
		if (!/^AFE-T-[0-9A-F]{6}$/i.test(ref)) return fail(400, { error: 'Unknown tenancy.' });
		try {
			await locals.api.post(`/review/tenancies/${ref}/release`, {
				note: str(form, 'note')
			});
			return { done: `Release sent for ${ref}.` };
		} catch (err) {
			return formError(err);
		}
	},
	decide: async ({ locals, request }) => {
		const form = await request.formData();
		const id = str(form, 'id');
		if (!/^\d+$/.test(id)) return fail(400, { error: 'Unknown dispute.' });
		try {
			await locals.api.post(`/review/disputes/${id}/decision`, {
				decision: str(form, 'decision'),
				note: str(form, 'note')
			});
			return { done: 'Decision recorded. Both sides have been told.' };
		} catch (err) {
			return formError(err);
		}
	}
};
