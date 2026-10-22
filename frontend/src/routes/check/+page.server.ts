import type { Actions, PageServerLoad } from './$types';
import type { CheckResult } from '$lib/api/types';
import { formError, str } from '$lib/server/guards';
import { track } from '$lib/server/track';

export const load: PageServerLoad = async (event) => {
	const q = (event.url.searchParams.get('q') ?? '').trim().slice(0, 20);
	if (!q) return { q, result: null };
	const result = await event.locals.api.get<CheckResult>(`/check?q=${encodeURIComponent(q)}`);
	track(event, 'check_lookup', { verified: result.verified });
	return { q, result };
};

export const actions: Actions = {
	report: async ({ request, locals }) => {
		const form = await request.formData();
		const report = {
			what_happened: str(form, 'what_happened'),
			reported_phone: str(form, 'reported_phone'),
			reported_reference: str(form, 'reported_reference')
		};
		try {
			await locals.api.post('/check/reports', report);
			return { reported: true };
		} catch (err) {
			return formError(err, { report });
		}
	}
};
