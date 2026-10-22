import type { PageServerLoad } from './$types';
import type { Worklist } from '$lib/api/types';

export const load: PageServerLoad = async ({ locals }) => ({ work: await locals.api.get<Worklist>('/verify/worklist') });
