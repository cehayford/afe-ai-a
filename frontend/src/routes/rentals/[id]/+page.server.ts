import { error, fail } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import type { RentalDetail } from '$lib/api/types';
import { formError, load404, requireMe, str } from '$lib/server/guards';

export const load: PageServerLoad = async ({ locals, params, url }) => {
	requireMe(locals.me, url);
	if (!/^\d+$/.test(params.id)) error(404, 'Not found.');
	return { d: await load404(locals.api.get<RentalDetail>(`/rentals/${params.id}`)) };
};

const id = (form: FormData, name = 'id') => {
	const v = str(form, name);
	return /^\d+$/.test(v) ? v : null;
};

export const actions: Actions = {
	pay: async ({ locals, params, request }) => {
		const f = await request.formData();
		try {
			await locals.api.post(`/rentals/${params.id}/payments`, {
				amount_ghs: Number(str(f, 'amount_ghs')), paid_on: str(f, 'paid_on'), method: str(f, 'method'),
				covers_months: Number(str(f, 'covers_months')), note: str(f, 'note')
			});
			return { done: 'Payment recorded. The receipt is below.' };
		} catch (err) {
			return formError(err);
		}
	},
	repair: async ({ locals, params, request }) => {
		const f = await request.formData();
		const body = new FormData();
		body.append('title', str(f, 'title'));
		body.append('details', str(f, 'details'));
		const photo = f.get('photo');
		if (photo instanceof File && photo.size > 0) body.append('photo', photo, photo.name);
		try {
			await locals.api.post(`/rentals/${params.id}/maintenance`, body);
			return { done: 'Repair request sent.' };
		} catch (err) {
			return formError(err);
		}
	},
	repairStatus: async ({ locals, request }) => {
		const f = await request.formData();
		const rid = id(f);
		if (!rid) return fail(400, { error: 'Unknown request.' });
		try {
			await locals.api.post(`/rentals/maintenance/${rid}`, { status: str(f, 'status'), note: str(f, 'note') });
			return { done: 'Repair updated.' };
		} catch (err) {
			return formError(err);
		}
	},
	agreement: async ({ locals, params }) => {
		try {
			await locals.api.post(`/rentals/${params.id}/agreements`);
			return { done: 'Agreement prepared and sent to the tenant.' };
		} catch (err) {
			return formError(err);
		}
	},
	sign: async ({ locals, request }) => {
		const f = await request.formData();
		const aid = id(f);
		if (!aid) return fail(400, { error: 'Unknown agreement.' });
		try {
			await locals.api.post(`/rentals/agreements/${aid}/sign`, { typed_name: str(f, 'typed_name') });
			return { done: 'Signed.' };
		} catch (err) {
			return formError(err);
		}
	},
	renew: async ({ locals, params, request }) => {
		const f = await request.formData();
		try {
			await locals.api.post(`/rentals/${params.id}/renewals`, {
				new_end_date: str(f, 'new_end_date'), new_rent_ghs: Number(str(f, 'new_rent_ghs')), advance_months: Number(str(f, 'advance_months'))
			});
			return { done: 'Renewal offer sent.' };
		} catch (err) {
			return formError(err);
		}
	},
	decideRenewal: async ({ locals, request }) => {
		const f = await request.formData();
		const rid = id(f);
		const answer = str(f, 'answer') === 'accept' ? 'accept' : 'decline';
		if (!rid) return fail(400, { error: 'Unknown renewal.' });
		try {
			await locals.api.post(`/rentals/renewals/${rid}/${answer}`);
			return { done: answer === 'accept' ? 'Renewal accepted.' : 'Renewal declined.' };
		} catch (err) {
			return formError(err);
		}
	},
	end: async ({ locals, params }) => {
		try {
			await locals.api.post(`/rentals/${params.id}/end`);
			return { done: 'Tenancy marked as ended.' };
		} catch (err) {
			return formError(err);
		}
	}
};
