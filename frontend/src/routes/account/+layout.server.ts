import type { LayoutServerLoad } from './$types';
import { requireMe } from '$lib/server/guards';

export const load: LayoutServerLoad = async ({ locals, url }) => {
	requireMe(locals.me, url);
	return {};
};
