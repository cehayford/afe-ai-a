import { fail } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import type { Rule } from '$lib/api/types';
import { formError, str } from '$lib/server/guards';

export const load: PageServerLoad = async ({ locals }) => ({
	rules: await locals.api.get<Rule[]>('/review/rules')
});

/** Form values arrive as text; send numbers and true/false as JSON values. */
function parse(raw: string): unknown {
	if (raw === 'true' || raw === 'false') return raw === 'true';
	return /^-?\d+$/.test(raw) ? Number(raw) : raw;
}

async function act(locals: App.Locals, request: Request, verb: 'approve' | 'reject', done: string) {
	const id = str(await request.formData(), 'id');
	if (!/^\d+$/.test(id)) return fail(400, { error: 'Unknown proposal.' });
	try {
		await locals.api.post(`/review/rules/${id}/${verb}`);
		return { done };
	} catch (err) {
		return formError(err);
	}
}

export const actions: Actions = {
	propose: async ({ locals, request }) => {
		const form = await request.formData();
		try {
			await locals.api.post('/review/rules', {
				key: str(form, 'key'),
				value: parse(str(form, 'value')),
				source: str(form, 'source')
			});
			return {
				done: 'Proposed. A second reviewer must approve it before it applies.'
			};
		} catch (err) {
			return formError(err);
		}
	},
	approve: ({ locals, request }) => act(locals, request, 'approve', 'Approved. It applies to new tenancies from now.'),
	reject: ({ locals, request }) => act(locals, request, 'reject', 'Rejected.'),
	rollback: async ({ locals, request }) => {
		const key = str(await request.formData(), 'key');
		if (!/^[a-z_]+$/.test(key)) return fail(400, { error: 'Unknown rule.' });
		try {
			await locals.api.post(`/review/rules/${key}/rollback`);
			return { done: 'Rollback proposed. A second reviewer must approve it.' };
		} catch (err) {
			return formError(err);
		}
	}
};
