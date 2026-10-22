import { error, fail } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import type { StaffMember } from '$lib/api/types';
import { formError, str } from '$lib/server/guards';

export const load: PageServerLoad = async ({ locals }) => {
	if (locals.me?.user.role !== 'admin') error(403, 'Only an Afe admin can manage staff.');
	return { staff: await locals.api.get<StaffMember[]>('/admin/staff') };
};

const ROLES = /^(field_verifier|reviewer|admin)$/;

export const actions: Actions = {
	add: async ({ locals, request }) => {
		const form = await request.formData();
		const values = { name: str(form, 'name'), phone: str(form, 'phone'), role: str(form, 'role') };
		try {
			await locals.api.post('/admin/staff', values);
			return { done: `Added ${values.name}. They've been sent an SMS to sign in.` };
		} catch (err) {
			return formError(err, values);
		}
	},
	role: async ({ locals, request }) => {
		const form = await request.formData();
		const id = str(form, 'id');
		const role = str(form, 'role');
		if (!/^\d+$/.test(id) || !ROLES.test(role)) return fail(400, { error: 'Unknown person or role.' });
		try {
			await locals.api.post(`/admin/staff/${id}/role`, { role });
			return { done: "Role changed. They'll need to sign in again." };
		} catch (err) {
			return formError(err);
		}
	},
	active: async ({ locals, request }) => {
		const form = await request.formData();
		const id = str(form, 'id');
		if (!/^\d+$/.test(id)) return fail(400, { error: 'Unknown person.' });
		const active = str(form, 'active') === 'true';
		try {
			await locals.api.post(`/admin/staff/${id}/active`, { active });
			return { done: active ? 'Account turned back on.' : 'Account turned off and signed out everywhere.' };
		} catch (err) {
			return formError(err);
		}
	}
};
