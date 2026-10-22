import { fail } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import type { SavedSearch } from '$lib/api/types';
import { formError, str } from '$lib/server/guards';

export const load: PageServerLoad = async ({ locals }) => ({ searches: await locals.api.get<SavedSearch[]>('/me/searches') });

export const actions: Actions = {
	stop: async ({ locals, request }) => {
		const id = str(await request.formData(), 'id');
		if (!/^\d+$/.test(id)) return fail(400, { error: 'Unknown alert.' });
		try {
			await locals.api.del(`/me/searches/${id}`);
			return { stopped: true };
		} catch (err) {
			return formError(err);
		}
	}
};
