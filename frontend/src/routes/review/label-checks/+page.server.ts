import { fail } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import type { LabelCheck } from '$lib/api/types';
import { formError, str } from '$lib/server/guards';

export const load: PageServerLoad = async ({ locals }) => ({ checks: await locals.api.get<LabelCheck[]>('/review/label-checks') });

export const actions: Actions = {
	default: async ({ locals, request }) => {
		const form = await request.formData();
		const id = str(form, 'id');
		if (!/^\d+$/.test(id)) return fail(400, { error: 'Unknown check.' });
		try {
			await locals.api.post(`/review/label-checks/${id}`, { agree: str(form, 'agree') === 'true', note: str(form, 'note') });
			return { done: true };
		} catch (err) {
			return formError(err);
		}
	}
};
