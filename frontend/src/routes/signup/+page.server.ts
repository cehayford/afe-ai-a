import { fail, redirect } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import type { Pricing, SignIn } from '$lib/api/types';
import { MFA_COOKIE } from '$lib/server/api';
import { formError, str } from '$lib/server/guards';
import { continueSignIn, homeFor, phoneFrom } from '$lib/server/signin';
import { track } from '$lib/server/track';

const ROLES = ['renter', 'landlord', 'agent'];

export const load: PageServerLoad = async ({ locals, url }) => {
	if (locals.me) redirect(303, homeFor(locals.me.user.role));
	const role = url.searchParams.get('role') ?? 'renter';
	const pricing = await locals.api.get<Pricing>('/pricing').catch(() => null);
	return { role: ROLES.includes(role) ? role : 'renter', freeVerification: Boolean(pricing?.launch_offer) };
};

function detailsOf(form: FormData) {
	return {
		phone: phoneFrom(str(form, 'phone')),
		display_name: str(form, 'display_name'),
		role: str(form, 'role'),
		accept: str(form, 'accept'),
		channel: str(form, 'channel') === 'sms' ? 'sms' : 'whatsapp'
	};
}

export const actions: Actions = {
	sendCode: async (event) => {
		const details = detailsOf(await event.request.formData());
		if (!ROLES.includes(details.role)) return fail(400, { error: 'Choose how you will use Afe.', ...details });
		// Creating an account is agreeing to the terms and privacy notice (said beside the button).
		if (details.accept !== 'yes') return fail(400, { error: 'Read and accept the privacy notice and terms to continue.', ...details });
		if (details.display_name.length < 2) return fail(400, { error: 'Enter your full name, as it appears on your Ghana Card.', ...details });
		try {
			await event.locals.api.anon('POST', '/auth/code', { phone: details.phone, purpose: 'signup', channel: details.channel });
			track(event, 'signup_start', { role: details.role });
			return { step: 'code' as const, ...details };
		} catch (err) {
			return formError(err, details);
		}
	},

	verify: async (event) => {
		const form = await event.request.formData();
		const details = detailsOf(form);
		try {
			const result = await event.locals.api.anon<SignIn>('POST', '/auth/signup', {
				phone: details.phone,
				display_name: details.display_name,
				role: details.role,
				code: str(form, 'code'),
				accept_privacy: details.accept === 'yes'
			});
			track(event, 'signup_complete', { role: details.role });
			return await continueSignIn(event.cookies, result, '', true);
		} catch (err) {
			return formError(err, { step: 'code' as const, ...details });
		}
	},

	mfa: async ({ request, locals, cookies }) => {
		const form = await request.formData();
		const token = cookies.get(MFA_COOKIE);
		if (!token) return fail(400, { error: 'Your sign-up session expired. Sign in to finish.' });
		try {
			const result = await locals.api.anon<SignIn>('POST', '/auth/mfa', { mfa_token: token, code: str(form, 'code') });
			return await continueSignIn(cookies, result, str(form, 'next'), true);
		} catch (err) {
			return formError(err, { step: 'mfa' as const });
		}
	}
};
