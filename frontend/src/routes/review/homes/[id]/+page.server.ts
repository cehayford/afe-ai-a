import type { Actions, PageServerLoad } from './$types';
import type { HomeReview, ReasonCode } from '$lib/api/types';
import { formError, load404, str } from '$lib/server/guards';
import { decide, revoke } from '$lib/server/decisions';

export const load: PageServerLoad = async ({ locals, params }) => {
	const [home, codes] = await Promise.all([
		load404(locals.api.get<HomeReview>(`/review/units/${params.id}`)),
		locals.api.get<ReasonCode[]>('/review/reason-codes')
	]);
	return { home, codes };
};

export const actions: Actions = {
	decide: (event) => decide(event, `/review/units/${event.params.id}/decision`),
	revoke,

	owner: async ({ request, locals }) => {
		const form = await request.formData();
		try {
			await locals.api.post(`/review/authority/${str(form, 'id')}/owner-confirmation`, {
				owner_phone: str(form, 'owner_phone'),
				owner_name: str(form, 'owner_name')
			});
			return { done: 'Owner confirmation recorded.' };
		} catch (err) {
			return formError(err, { form: 'authority' });
		}
	},

	authority: async ({ request, locals }) => {
		const form = await request.formData();
		try {
			await locals.api.post(`/review/authority/${str(form, 'id')}/decision`, {
				accept: str(form, 'accept') === 'true',
				note: str(form, 'note')
			});
			return { done: 'Document decision saved.' };
		} catch (err) {
			return formError(err, { form: 'authority' });
		}
	}
};
