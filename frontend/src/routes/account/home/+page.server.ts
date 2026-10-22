import type { PageServerLoad } from './$types';
import type { Rental } from '$lib/api/types';

export const load: PageServerLoad = async ({ locals }) => ({ homes: await locals.api.get<Rental[]>('/rentals/my-homes') });
