import { redirect } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import { REFRESH_COOKIE, clearSession } from '$lib/server/api';

export const load: PageServerLoad = async () => redirect(303, '/account');

export const actions: Actions = {
	default: async ({ cookies, locals }) => {
		const token = cookies.get(REFRESH_COOKIE);
		if (token) await locals.api.anon('POST', '/auth/signout', { refresh_token: token }).catch(() => {});
		clearSession(cookies);
		redirect(303, '/');
	}
};
