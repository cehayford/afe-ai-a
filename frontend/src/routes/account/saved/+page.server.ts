import type { PageServerLoad } from './$types';
import type { Listing } from '$lib/api/types';

export const load: PageServerLoad = async ({ locals }) => ({ listings: await locals.api.get<Listing[]>('/me/saved') });
