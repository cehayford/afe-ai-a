import { error, fail } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import type { AreaAdmin } from '$lib/api/types';
import { formError, str } from '$lib/server/guards';

export const load: PageServerLoad = async ({ locals }) => {
	if (locals.me?.user.role !== 'admin') error(403, 'Only an Afe admin can open areas.');
	return { areas: await locals.api.get<AreaAdmin[]>('/admin/areas') };
};

/** "5.66, -0.18" per line -> [[5.66, -0.18], ...] */
function points(text: string): number[][] {
	return text
		.split(/\n+/)
		.map((line) => line.split(/[ ,]+/).filter(Boolean).map(Number))
		.filter((p) => p.length === 2 && p.every((n) => Number.isFinite(n)));
}

export const actions: Actions = {
	create: async ({ locals, request }) => {
		const form = await request.formData();
		try {
			await locals.api.post('/admin/areas', {
				name: str(form, 'name'),
				slug: str(form, 'slug'),
				city: str(form, 'city') || 'Accra',
				boundary: points(str(form, 'boundary'))
			});
			return { done: 'Area created. It stays closed until it is ready.' };
		} catch (err) {
			return formError(err);
		}
	},
	survey: async ({ locals, request }) => {
		const form = await request.formData();
		const id = str(form, 'id');
		if (!/^\d+$/.test(id)) return fail(400, { error: 'Unknown area.' });
		const rows = [0, 1, 2, 3]
			.map((b) => ({ bedrooms: b, low_ghs: Number(str(form, `low${b}`)), median_ghs: Number(str(form, `mid${b}`)), high_ghs: Number(str(form, `high${b}`)) }))
			.filter((r) => r.low_ghs > 0 && r.median_ghs > 0 && r.high_ghs > 0);
		if (!rows.length) return fail(400, { error: 'Enter at least one size.' });
		try {
			await locals.api.post(`/admin/areas/${id}/price-survey`, rows);
			return { done: 'Price survey saved.' };
		} catch (err) {
			return formError(err);
		}
	},
	open: async ({ locals, request }) => {
		const form = await request.formData();
		const id = str(form, 'id');
		if (!/^\d+$/.test(id)) return fail(400, { error: 'Unknown area.' });
		const open = str(form, 'open') === 'true';
		try {
			await locals.api.post(`/admin/areas/${id}/open`, { open });
			return { done: open ? 'Area open for listings.' : 'Area closed.' };
		} catch (err) {
			return formError(err);
		}
	}
};
