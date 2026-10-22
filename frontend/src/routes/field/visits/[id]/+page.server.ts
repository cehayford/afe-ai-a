import type { PageServerLoad } from './$types';
import type { VisitDetail } from '$lib/api/types';
import { load404 } from '$lib/server/guards';

export const load: PageServerLoad = async ({ locals, params }) => {
	const visit = await load404(locals.api.get<VisitDetail>(`/verify/visits/${params.id}`));
	const u = visit.unit;
	return { visit, head: { title: `${u.unit_label} · ${u.property_type_label}`, sub: `${u.digital_address}, ${u.area.name}` } };
};
