import type { Actions, PageServerLoad } from './$types';
import type { Notification } from '$lib/api/types';

export const load: PageServerLoad = async ({ locals }) => ({
	notifications: await locals.api.get<Notification[]>('/me/notifications')
});

export const actions: Actions = {
	read: async ({ locals }) => {
		await locals.api.post('/me/notifications/read', {});
	}
};
