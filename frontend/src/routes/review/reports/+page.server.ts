import { fail } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import type { FraudReport } from '$lib/api/types';
import { formError, str } from '$lib/server/guards';

export const load: PageServerLoad = async ({ locals }) => ({ reports: await locals.api.get<FraudReport[]>('/review/reports') });

export const actions: Actions = {
	default: async ({ locals, request }) => {
		const form = await request.formData();
		const id = str(form, 'id');
		if (!/^\d+$/.test(id)) return fail(400, { error: 'Unknown report.' });
		try {
			await locals.api.post(`/review/reports/${id}/decision`, { upheld: str(form, 'upheld') === 'true', note: str(form, 'note') });
			return { done: 'Decision saved.' };
		} catch (err) {
			return formError(err);
		}
	}
};
