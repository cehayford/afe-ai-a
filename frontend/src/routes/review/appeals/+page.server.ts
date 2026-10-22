import { fail } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import type { Appeal } from '$lib/api/types';
import { formError, str } from '$lib/server/guards';

export const load: PageServerLoad = async ({ locals }) => ({ appeals: await locals.api.get<Appeal[]>('/review/appeals') });

export const actions: Actions = {
	default: async ({ locals, request }) => {
		const form = await request.formData();
		const id = str(form, 'id');
		if (!/^\d+$/.test(id)) return fail(400, { error: 'Unknown appeal.' });
		try {
			await locals.api.post(`/review/appeals/${id}/decision`, { upheld: str(form, 'upheld') === 'true', outcome: str(form, 'outcome') });
			return { done: true };
		} catch (err) {
			return formError(err);
		}
	}
};
