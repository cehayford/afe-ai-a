import { redirect } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import type { HomeReview, PersonReview, Queue, ReasonCode, User } from '$lib/api/types';
import { formError, str } from '$lib/server/guards';

// The review desk: one queue on the left, the selected item on the right (?item=kind:id).
export const load: PageServerLoad = async ({ locals, url }) => {
	const [queue, verifiers, codes] = await Promise.all([
		locals.api.get<Queue>('/review/queue'),
		locals.api.get<User[]>('/review/verifiers'),
		locals.api.get<ReasonCode[]>('/review/reason-codes')
	]);
	const first = queue.homes_to_decide[0]
		? `home:${queue.homes_to_decide[0].id}`
		: queue.people[0]
			? `person:${queue.people[0].id}`
			: queue.flags[0]
				? `flag:${queue.flags[0].id}`
				: queue.listings[0]
					? `listing:${queue.listings[0].listing.id}`
					: queue.homes_to_visit[0]
						? `visit:${queue.homes_to_visit[0].id}`
						: '';
	const item = url.searchParams.get('item') || first;
	const [kind, id] = item.split(':');
	const home = kind === 'home' || kind === 'visit' || kind === 'fee' ? await locals.api.get<HomeReview>(`/review/units/${id}`).catch(() => null) : null;
	const person = kind === 'person' ? await locals.api.get<PersonReview>(`/review/people/${id}`).catch(() => null) : null;
	return { queue, verifiers, codes, item, home, person, filter: url.searchParams.get('filter') ?? 'all' };
};

async function post(locals: App.Locals, path: string, body: Record<string, unknown>, done: string) {
	try {
		await locals.api.post(path, body);
		return { done };
	} catch (err) {
		return formError(err);
	}
}

export const actions: Actions = {
	/** Approve or reject a home or a person. The next item in the queue opens after. */
	decide: async ({ request, locals }) => {
		const form = await request.formData();
		const [kind, id] = str(form, 'item').split(':');
		const path = kind === 'person' ? `/review/people/${id}/decision` : `/review/units/${id}/decision`;
		const approve = str(form, 'decision') === 'approve';
		const codes = approve ? form.getAll('codes').map(String) : [str(form, 'reason')].filter(Boolean);
		try {
			await locals.api.post(path, { approve, reason_codes: codes, note: str(form, 'note') });
		} catch (err) {
			return formError(err);
		}
		redirect(303, `/review?done=${encodeURIComponent(approve ? 'Approved' : 'Rejected')}`);
	},
	assign: async ({ request, locals }) => {
		const form = await request.formData();
		return post(
			locals,
			`/review/units/${str(form, 'unit_id')}/assignments`,
			{ verifier_id: Number(str(form, 'verifier_id')), scheduled_for: str(form, 'scheduled_for'), note: str(form, 'note') },
			'Visit assigned.'
		);
	},
	cancel: async ({ request, locals }) => post(locals, `/review/assignments/${str(await request.formData(), 'id')}/cancel`, {}, 'Visit cancelled.'),
	waive: async ({ request, locals }) => {
		const form = await request.formData();
		return post(locals, `/review/units/${str(form, 'unit_id')}/fee-waiver`, { note: str(form, 'note') }, 'Fee waived.');
	},
	publish: async ({ request, locals }) => post(locals, `/review/listings/${str(await request.formData(), 'id')}/publish`, {}, 'Listing is live.'),
	resolve: async ({ request, locals }) => {
		const form = await request.formData();
		return post(
			locals,
			`/review/flags/${str(form, 'id')}/resolve`,
			{ confirmed_fraud: str(form, 'outcome') === 'confirm', note: str(form, 'note') || 'Resolved from the review queue' },
			'Flag resolved.'
		);
	},
	authority: async ({ request, locals }) => {
		const form = await request.formData();
		return post(locals, `/review/authority/${str(form, 'id')}/decision`, { accept: str(form, 'accept') === 'true', note: str(form, 'note') }, 'Document decision saved.');
	},
	owner: async ({ request, locals }) => {
		const form = await request.formData();
		return post(
			locals,
			`/review/authority/${str(form, 'id')}/owner-confirmation`,
			{ owner_phone: str(form, 'owner_phone'), owner_name: str(form, 'owner_name') },
			'Owner confirmation recorded.'
		);
	}
};
