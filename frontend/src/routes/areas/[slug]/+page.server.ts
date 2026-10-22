import { error } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import type { AreaOverview } from '$lib/api/types';
import { load404 } from '$lib/server/guards';

export const load: PageServerLoad = async ({ locals, params }) => {
	if (!/^[a-z0-9-]{2,60}$/.test(params.slug)) error(404, "Afe isn't open in that area yet.");
	return { overview: await load404(locals.api.get<AreaOverview>(`/properties/areas/${params.slug}`)) };
};
