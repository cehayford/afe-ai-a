import { redirect } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import type { Area, CheckResult, Listing, ListingDetail, Pricing } from '$lib/api/types';
import { formError, str } from '$lib/server/guards';
import { track } from '$lib/server/track';

/** Set when someone closes the launch-offer bar, so it stays closed on this browser. */
const OFFER_CLOSED = 'afe_offer_closed';

export const load: PageServerLoad = async (event) => {
	const { url, locals, cookies } = event;
	// Search used to live here: keep old links (SMS alerts, bookmarks, area pages) working.
	if (['area', 'bedrooms', 'max_rent'].some((k) => url.searchParams.has(k))) {
		redirect(308, `/homes${url.search}`);
	}
	const [areas, listings, pricing] = await Promise.all([
		locals.api.get<Area[]>('/properties/areas'),
		locals.api.get<Listing[]>('/properties/search'),
		locals.api.get<Pricing>('/pricing').catch(() => null)
	]);
	// The "what you see on every listing" panel shows a real record when there is a live home.
	const record = listings[0]
		? await locals.api
				.get<ListingDetail>(`/properties/${listings[0].reference}`)
				.then((d) => d.verification)
				.catch(() => [])
		: [];
	track(event, 'page_view', { page: 'landing' });
	return {
		areas,
		latest: listings.slice(0, 3),
		live: listings.length,
		record,
		pricing,
		offerClosed: cookies.get(OFFER_CLOSED) === '1',
		closed: url.searchParams.has('closed')
	};
};

export const actions: Actions = {
	/** The x on the launch-offer bar. Works without JavaScript too: the page reloads without the bar. */
	closeOffer: async ({ cookies }) => {
		cookies.set(OFFER_CLOSED, '1', { path: '/', maxAge: 60 * 60 * 24 * 180, sameSite: 'lax' });
	},
	/** The landing page's scam check answers in place; /check has the full page. */
	check: async (event) => {
		const q = str(await event.request.formData(), 'q').slice(0, 20);
		if (!q) return { check: null, q };
		try {
			const result = await event.locals.api.get<CheckResult>(`/check?q=${encodeURIComponent(q)}`);
			track(event, 'check_lookup', { verified: result.verified, from: 'landing' });
			return { check: result, q };
		} catch (err) {
			return formError(err, { q });
		}
	}
};
