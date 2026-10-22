import type { Actions, PageServerLoad } from './$types';
import type { ThreadDetail } from '$lib/api/types';
import { formError, load404, str } from '$lib/server/guards';

export const load: PageServerLoad = async ({ locals, params }) => ({
	thread: await load404(locals.api.get<ThreadDetail>(`/messages/${params.id}`))
});

export const actions: Actions = {
	send: async ({ request, locals, params }) => {
		const body = str(await request.formData(), 'body');
		try {
			await locals.api.post(`/messages/${params.id}`, { body });
		} catch (err) {
			return formError(err, { body });
		}
	}
};
