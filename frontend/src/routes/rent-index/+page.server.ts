import type { PageServerLoad } from './$types';
import type { RentIndex } from '$lib/api/types';

export const load: PageServerLoad = async ({ locals }) => ({ index: await locals.api.get<RentIndex>('/properties/rent-index') });
