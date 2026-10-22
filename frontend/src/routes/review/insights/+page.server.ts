import type { PageServerLoad } from './$types';
import type { Target } from '$lib/api/types';

export const load: PageServerLoad = async ({ locals }) => ({ targets: await locals.api.get<Target[]>('/review/targets') });
