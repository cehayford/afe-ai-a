import type { PageServerLoad } from './$types';
import type { Thread, Viewing } from '$lib/api/types';

export const load: PageServerLoad = async ({ locals }) => {
	const [threads, viewings] = await Promise.all([locals.api.get<Thread[]>('/messages'), locals.api.get<Viewing[]>('/viewings')]);
	return {
		threads: threads.filter((t) => t.role === 'lister'),
		requests: viewings.filter((v) => v.role === 'lister' && v.status === 'requested')
	};
};
