import type { PageServerLoad } from './$types';
import type { Payment } from '$lib/api/types';

export const load: PageServerLoad = async ({ locals }) => ({ payments: await locals.api.get<Payment[]>('/me/payments') });
