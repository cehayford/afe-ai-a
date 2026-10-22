import type { LayoutServerLoad } from './$types';
import { requireRole } from '$lib/server/guards';

export const load: LayoutServerLoad = async ({ locals, url }) => {
	requireRole(locals.me, url, ['field_verifier']);
	return {};
};
