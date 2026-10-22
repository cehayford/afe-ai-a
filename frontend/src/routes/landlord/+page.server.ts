import type { PageServerLoad } from './$types';
import type { MyUnit, Pricing, Tenancy, Thread, Viewing } from '$lib/api/types';

const HELD = ['funded', 'disputed', 'release_pending', 'releasing'];

export const load: PageServerLoad = async ({ locals }) => {
	const [homes, viewings, pricing, tenancies, threads] = await Promise.all([
		locals.api.get<MyUnit[]>('/me/units'),
		locals.api.get<Viewing[]>('/viewings'),
		locals.api.get<Pricing>('/pricing'),
		locals.api.get<Tenancy[]>('/tenancies').catch(() => [] as Tenancy[]),
		locals.api.get<Thread[]>('/messages').catch(() => [] as Thread[])
	]);
	const weekAgo = Date.now() - 7 * 86_400_000;
	const mine = viewings.filter((v) => v.role === 'lister');
	return {
		homes,
		pricing,
		toAnswer: mine.filter((v) => v.status === 'requested'),
		upcoming: mine
			.filter((v) => ['requested', 'confirmed'].includes(v.status) && new Date(v.requested_for).getTime() > Date.now())
			.sort((a, b) => a.requested_for.localeCompare(b.requested_for)),
		stats: {
			live: homes.flatMap((h) => h.listings).filter((l) => l.status === 'live').length,
			enquiries: threads.filter((t) => t.role === 'lister' && new Date(t.last_message_at).getTime() > weekAgo).length,
			booked: mine.filter((v) => v.status === 'confirmed' && new Date(v.requested_for).getTime() > Date.now()).length,
			held: tenancies.filter((t) => t.role === 'landlord' && HELD.includes(t.status)).reduce((sum, t) => sum + t.payout_pesewas, 0)
		}
	};
};
