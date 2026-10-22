import type { PageServerLoad } from './$types';
import type { Workload } from '$lib/api/types';

export const load: PageServerLoad = async ({ locals }) => ({ w: await locals.api.get<Workload>('/review/workload') });
