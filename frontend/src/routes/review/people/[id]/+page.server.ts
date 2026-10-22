import { fail } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import type { PersonGraph, PersonReview, ReasonCode } from '$lib/api/types';
import { formError, load404, str } from '$lib/server/guards';
import { decide, hideReview, revoke } from '$lib/server/decisions';

export const load: PageServerLoad = async ({ locals, params }) => {
	const [person, codes, graph] = await Promise.all([
		load404(locals.api.get<PersonReview>(`/review/people/${params.id}`)),
		locals.api.get<ReasonCode[]>('/review/reason-codes'),
		locals.api.get<PersonGraph>(`/review/people/${params.id}/graph`)
	]);
	return { person, codes, graph };
};

export const actions: Actions = {
	decide: (event) => decide(event, `/review/people/${event.params.id}/decision`),
	revoke,
	hideReview,
	suspend: async ({ locals, params, request }) => {
		if (locals.me?.user.role !== 'admin') return fail(403, { error: 'Only an Afe admin can suspend accounts.' });
		const form = await request.formData();
		const active = str(form, 'active') === 'true';
		try {
			await locals.api.post(`/admin/people/${params.id}/active`, { active, reason: str(form, 'reason') });
			return { done: active ? 'Account restored.' : 'Account suspended and signed out everywhere. No money will be released to them.' };
		} catch (err) {
			return formError(err);
		}
	}
};
