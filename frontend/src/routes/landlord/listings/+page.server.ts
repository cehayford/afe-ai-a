import type { PageServerLoad } from './$types';
import type { MyUnit, Viewing } from '$lib/api/types';

export const load: PageServerLoad = async ({ locals }) => {
	const [homes, viewings] = await Promise.all([locals.api.get<MyUnit[]>('/me/units'), locals.api.get<Viewing[]>('/viewings')]);
	const views = new Map<string, number>();
	for (const v of viewings) if (v.role === 'lister') views.set(v.listing_reference, (views.get(v.listing_reference) ?? 0) + 1);
	return {
		listings: homes.flatMap((h) => h.listings.map((l) => ({ ...l, viewings: views.get(l.reference) ?? 0 })))
	};
};
