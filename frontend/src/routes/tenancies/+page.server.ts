import type { PageServerLoad } from './$types';
import type { Tenancy } from '$lib/api/types';
import { requireMe } from '$lib/server/guards';

export const load: PageServerLoad = async ({ locals, url }) => {
	requireMe(locals.me, url);
	return { tenancies: await locals.api.get<Tenancy[]>('/tenancies') };
};
