import { redirect } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import type { Tenancy } from '$lib/api/types';
import { formError, load404, requireMe, str } from '$lib/server/guards';

export const load: PageServerLoad = async ({ locals, params, url }) => {
	requireMe(locals.me, url);
	return {
		tenancy: await load404(locals.api.get<Tenancy>(`/tenancies/${params.reference}`))
	};
};

/** Every action posts to the API and reloads the page; failures come back as a form error. */
function act(path: string, body?: (form: FormData) => Record<string, unknown>) {
	return async ({ locals, params, request }: Parameters<Actions[string]>[0]) => {
		const form = await request.formData();
		try {
			await locals.api.post(`/tenancies/${params.reference}${path}`, body ? body(form) : {});
		} catch (err) {
			return formError(err, { action: path });
		}
		return { done: path };
	};
}

export const actions: Actions = {
	accept: async ({ locals, params }) => {
		let t: Tenancy;
		try {
			t = await locals.api.post<Tenancy>(`/tenancies/${params.reference}/accept`);
		} catch (err) {
			return formError(err, { action: '/accept' });
		}
		redirect(303, t.checkout_url || `/tenancies/${t.reference}`);
	},
	pay: async ({ locals, params }) => {
		const t = await locals.api.get<Tenancy>(`/tenancies/${params.reference}`);
		if (!t.checkout_url) return { done: '/pay' };
		redirect(303, t.checkout_url);
	},
	decline: act('/decline'),
	withdraw: act('/withdraw'),
	confirm: async ({ locals, params, request }) => {
		const form = await request.formData();
		const photo = form.get('photo');
		const body = new FormData();
		if (photo instanceof File && photo.size > 0) body.append('photo', photo, photo.name);
		try {
			await locals.api.post(`/tenancies/${params.reference}/confirm-move-in`, body);
		} catch (err) {
			return formError(err, { action: '/confirm-move-in' });
		}
		return { done: '/confirm-move-in' };
	},
	evidence: act('/move-in-evidence', (f) => ({ note: str(f, 'note') })),
	dispute: act('/disputes', (f) => ({
		reason: str(f, 'reason'),
		details: str(f, 'details')
	})),
	review: act('/review', (f) => ({
		rating: Number(str(f, 'rating')),
		body: str(f, 'body')
	}))
};
