import type { PageServerLoad } from './$types';
import type { Assignment, Worklist } from '$lib/api/types';
import { load404 } from '$lib/server/guards';

export const load: PageServerLoad = async ({ locals, params }) => {
	const [assignment, work] = await Promise.all([
		load404(locals.api.get<Assignment>(`/verify/assignments/${params.id}`)),
		locals.api.get<Worklist>('/verify/worklist')
	]);
	const u = assignment.unit;
	return { assignment, radius: work.radius_m, head: { title: `${u.unit_label} · ${u.property_type_label}`, sub: `${u.digital_address}, ${u.area.name}` } };
};
