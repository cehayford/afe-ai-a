import { redirect } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import type { Viewing } from '$lib/api/types';
import { formError, str } from '$lib/server/guards';

export const load: PageServerLoad = async ({ locals }) => ({ viewings: await locals.api.get<Viewing[]>('/viewings') });

function back(form: FormData): string {
	const to = str(form, 'back');
	return to.startsWith('/') && !to.startsWith('//') ? to : '/account/viewings';
}

export const actions: Actions = {
	respond: async ({ request, locals }) => {
		const form = await request.formData();
		try {
			await locals.api.post(`/viewings/${str(form, 'id')}/respond`, {
				confirm: str(form, 'confirm') === 'true',
				note: str(form, 'note')
			});
		} catch (err) {
			return formError(err);
		}
		redirect(303, back(form));
	},
	cancel: async ({ request, locals }) => {
		const form = await request.formData();
		try {
			await locals.api.post(`/viewings/${str(form, 'id')}/cancel`);
		} catch (err) {
			return formError(err);
		}
		redirect(303, back(form));
	},
	outcome: async ({ request, locals }) => {
		const form = await request.formData();
		try {
			await locals.api.post(`/viewings/${str(form, 'id')}/outcome`, { answer: str(form, 'answer') });
			return { answered: true };
		} catch (err) {
			return formError(err);
		}
	},
	complete: async ({ request, locals }) => {
		const form = await request.formData();
		try {
			await locals.api.post(`/viewings/${str(form, 'id')}/complete`, { attended: str(form, 'attended') === 'true' });
		} catch (err) {
			return formError(err);
		}
		redirect(303, back(form));
	}
};
