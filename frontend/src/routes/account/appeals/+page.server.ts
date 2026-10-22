import { fail } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import type { Appeal, Appealable } from '$lib/api/types';
import { formError, str } from '$lib/server/guards';

export const load: PageServerLoad = async ({ locals }) => {
	const [appealable, appeals] = await Promise.all([
		locals.api.get<Appealable[]>('/me/appealable'),
		locals.api.get<Appeal[]>('/me/appeals')
	]);
	return { appealable, appeals };
};

export const actions: Actions = {
	default: async ({ locals, request }) => {
		const form = await request.formData();
		const [kind, subject] = str(form, 'decision').split(':');
		if (!/^(verification|listing|report)$/.test(kind) || !/^\d+$/.test(subject ?? '')) return fail(400, { error: 'Choose a decision.', reason: str(form, 'reason') });
		try {
			await locals.api.post('/me/appeals', { kind, subject_id: Number(subject), reason: str(form, 'reason') });
			return { sent: true };
		} catch (err) {
			return formError(err, { reason: str(form, 'reason') });
		}
	}
};
