import type { PageServerLoad } from './$types';
import type { VerifierStats } from '$lib/api/types';

export const load: PageServerLoad = async ({ locals }) => ({ stats: await locals.api.get<VerifierStats[]>('/review/verifier-stats') });
