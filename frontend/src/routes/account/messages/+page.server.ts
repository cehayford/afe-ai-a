import type { PageServerLoad } from './$types';
import type { Thread } from '$lib/api/types';

export const load: PageServerLoad = async ({ locals }) => ({ threads: await locals.api.get<Thread[]>('/messages') });
