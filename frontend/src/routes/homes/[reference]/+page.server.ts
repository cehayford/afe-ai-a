import { redirect } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import type { ListingDetail, Thread } from '$lib/api/types';
import { formError, load404, str } from '$lib/server/guards';
import { track } from '$lib/server/track';

export const load: PageServerLoad = async (event) => {
	const listing = await load404(event.locals.api.get<ListingDetail>(`/properties/${event.params.reference}`));
	track(event, 'listing_view', { reference: listing.reference });
	return { listing };
};

function signInFirst(url: URL): never {
	redirect(303, `/signin?next=${encodeURIComponent(url.pathname)}`);
}

export const actions: Actions = {
	save: async (event) => {
		if (!event.locals.me) signInFirst(event.url);
		const saved = str(await event.request.formData(), 'saved') === 'true';
		try {
			if (saved) await event.locals.api.del(`/properties/${event.params.reference}/save`);
			else {
				await event.locals.api.post(`/properties/${event.params.reference}/save`);
				track(event, 'listing_save', { reference: event.params.reference });
			}
		} catch (err) {
			return formError(err);
		}
	},

	enquire: async (event) => {
		if (!event.locals.me) signInFirst(event.url);
		const body = str(await event.request.formData(), 'body');
		try {
			const thread = await event.locals.api.post<Thread>(`/properties/${event.params.reference}/enquiries`, { body });
			track(event, 'enquiry_start', { reference: event.params.reference });
			redirect(303, `/account/messages/${thread.id}`);
		} catch (err) {
			return formError(err, { form: 'enquire', body });
		}
	}
};
