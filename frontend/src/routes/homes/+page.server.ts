import type { Actions, PageServerLoad } from './$types';
import type { Area, Listing, SavedSearch } from '$lib/api/types';
import { formError, str } from '$lib/server/guards';
import { track } from '$lib/server/track';

export const load: PageServerLoad = async (event) => {
	const { url, locals } = event;
	const q = {
		area: url.searchParams.get('area') ?? '',
		bedrooms: url.searchParams.get('bedrooms') ?? '',
		max_rent: url.searchParams.get('max_rent') ?? ''
	};
	const params = new URLSearchParams();
	if (q.area) params.set('area', q.area);
	if (/^\d+$/.test(q.bedrooms)) params.set('bedrooms', q.bedrooms);
	if (/^\d+(\.\d+)?$/.test(q.max_rent) && Number(q.max_rent) > 0) params.set('max_rent_ghs', q.max_rent);

	const [areas, listings, saved] = await Promise.all([
		locals.api.get<Area[]>('/properties/areas'),
		locals.api.get<Listing[]>(`/properties/search?${params}`),
		// Renters see which results they have saved (the Save / Saved toggle on each card).
		locals.me?.user.role === 'renter' ? locals.api.get<Listing[]>('/me/saved').catch(() => []) : Promise.resolve([] as Listing[])
	]);
	if ([...params.keys()].length) track(event, 'search', { area: q.area, bedrooms: q.bedrooms, results: listings.length });
	else track(event, 'page_view');
	return { areas, listings, q, saved: saved.map((l) => l.reference) };
};

export const actions: Actions = {
	/** "Get told when a home like this is listed": saves the current search as an alert. */
	alert: async ({ locals, request }) => {
		const form = await request.formData();
		const bedrooms = str(form, 'bedrooms');
		const maxRent = str(form, 'max_rent');
		try {
			const saved = await locals.api.post<SavedSearch>('/me/searches', {
				area_slug: str(form, 'area') || null,
				bedrooms: /^\d$/.test(bedrooms) ? Number(bedrooms) : null,
				max_rent_ghs: /^\d+$/.test(maxRent) ? Number(maxRent) : null,
				channel: str(form, 'channel')
			});
			return { alertSaved: saved.description };
		} catch (err) {
			return formError(err);
		}
	}
};
