import { fail } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import type { ListingDetail, Viewing } from '$lib/api/types';
import { formError, load404, requireMe, str } from '$lib/server/guards';
import { track } from '$lib/server/track';

export const load: PageServerLoad = async ({ locals, url, params }) => {
	requireMe(locals.me, url);
	const listing = await load404(locals.api.get<ListingDetail>(`/properties/${params.reference}`));
	return { listing };
};

export const actions: Actions = {
	/** Day and time come from the chips, in Ghana time (UTC+0 all year). */
	default: async (event) => {
		requireMe(event.locals.me, event.url);
		const form = await event.request.formData();
		const day = str(form, 'day');
		const time = str(form, 'time');
		if (!/^\d{4}-\d{2}-\d{2}$/.test(day) || !/^\d{2}:\d{2}$/.test(time)) return fail(400, { error: 'Choose a day and a time for the viewing.' });
		try {
			const viewing = await event.locals.api.post<Viewing>(`/properties/${event.params.reference}/viewings`, { when: `${day}T${time}:00Z`, note: '' });
			track(event, 'viewing_request', { reference: event.params.reference });
			return { booked: { when: viewing.requested_for, thread: viewing.thread_id } };
		} catch (err) {
			return formError(err);
		}
	}
};
