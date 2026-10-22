import { fail, redirect } from '@sveltejs/kit';
import type { RequestEvent } from '@sveltejs/kit';
import { formError, str } from './guards';

/** Shared "decide" form action for people and homes. */
export async function decide(event: RequestEvent, path: string) {
	const form = await event.request.formData();
	// Approving sends the evidence ticked; rejecting sends the one reason code picked.
	const approve = str(form, 'decision') === 'approve';
	try {
		await event.locals.api.post(path, {
			approve,
			reason_codes: approve ? form.getAll('codes').map(String) : [str(form, 'reason')].filter(Boolean),
			note: str(form, 'note')
		});
	} catch (err) {
		return formError(err, { form: 'decide' });
	}
	redirect(303, '/review');
}

/** Shared "revoke" form action: take a verification away, with one reason code and a note. */
export async function revoke(event: RequestEvent) {
	const form = await event.request.formData();
	const id = str(form, 'id');
	if (!/^\d+$/.test(id)) return fail(400, { form: 'revoke', error: 'Unknown verification.' });
	try {
		await event.locals.api.post(`/review/verifications/${id}/revoke`, {
			reason_codes: [str(form, 'reason')].filter(Boolean),
			note: str(form, 'note')
		});
	} catch (err) {
		return formError(err, { form: 'revoke' });
	}
	return { done: 'Verification revoked. Their live listings are paused.' };
}

/** Hide a tenant's review from renters (abuse, personal data); the note goes in the audit log. */
export async function hideReview(event: RequestEvent) {
	const form = await event.request.formData();
	const id = str(form, 'id');
	if (!/^\d+$/.test(id)) return fail(400, { form: 'review', error: 'Unknown review.' });
	try {
		await event.locals.api.post(`/review/reviews/${id}/hide`, { note: str(form, 'note') });
	} catch (err) {
		return formError(err, { form: 'review' });
	}
	return { done: 'Review hidden from renters.' };
}
