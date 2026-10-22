import { fail, redirect } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import type { Area, MyUnit } from '$lib/api/types';
import { formError, str } from '$lib/server/guards';

export const load: PageServerLoad = async ({ locals }) => ({ areas: await locals.api.get<Area[]>('/properties/areas') });

export const actions: Actions = {
	default: async ({ request, locals }) => {
		const form = await request.formData();
		const values = {
			area_slug: str(form, 'area_slug'),
			digital_address: str(form, 'digital_address'),
			unit_label: str(form, 'unit_label') || 'Whole property',
			lat: str(form, 'lat'),
			lng: str(form, 'lng'),
			property_type: str(form, 'property_type'),
			bedrooms: str(form, 'bedrooms'),
			bathrooms: str(form, 'bathrooms') || '1',
			landmark: str(form, 'landmark')
		};
		if (!values.lat || !values.lng) {
			return fail(400, { ...values, error: 'Place the pin on the map, or use your location at the home.' });
		}
		let home: MyUnit;
		try {
			home = await locals.api.post<MyUnit>('/properties/units', {
				...values,
				bedrooms: Number(values.bedrooms),
				bathrooms: Number(values.bathrooms)
			});
		} catch (err) {
			return formError(err, values);
		}
		redirect(303, `/landlord/homes/${home.unit.id}`);
	}
};
