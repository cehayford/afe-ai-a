import { redirect } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import type { Device, User } from '$lib/api/types';
import { clearSession } from '$lib/server/api';
import { formError, str } from '$lib/server/guards';

export const load: PageServerLoad = async ({ locals }) => ({
	devices: await locals.api.get<Device[]>('/me/devices')
});

export const actions: Actions = {
	profile: async ({ request, locals }) => {
		const form = await request.formData();
		try {
			await locals.api.patch<User>('/me', {
				display_name: str(form, 'display_name'),
				email: str(form, 'email'),
				whatsapp_opt_in: form.get('whatsapp_opt_in') === 'on'
			});
			return { saved: true };
		} catch (err) {
			return formError(err);
		}
	},

	close: async ({ request, locals, cookies }) => {
		const form = await request.formData();
		try {
			await locals.api.post('/me/close', {
				confirm: str(form, 'confirm'),
				password: form.get('password')?.toString() ?? '',
				code: str(form, 'code')
			});
		} catch (err) {
			return formError(err, { closing: true });
		}
		clearSession(cookies);
		redirect(303, '/?closed=1');
	},

	privacy: async ({ locals }) => {
		try {
			await locals.api.post('/me/privacy');
		} catch (err) {
			return formError(err);
		}
		return { privacyAccepted: true };
	},

	everywhere: async ({ locals, cookies }) => {
		await locals.api.post('/auth/signout/everywhere');
		clearSession(cookies);
		redirect(303, '/signin');
	}
};
