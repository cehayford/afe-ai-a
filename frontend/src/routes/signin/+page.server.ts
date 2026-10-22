import { fail, redirect } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import type { SignIn } from '$lib/api/types';
import { MFA_COOKIE } from '$lib/server/api';
import { formError, str } from '$lib/server/guards';
import { continueSignIn, homeFor, phoneFrom, safeNext } from '$lib/server/signin';

export const load: PageServerLoad = async ({ locals, url }) => {
	const next = safeNext(url.searchParams.get('next'));
	if (locals.me) redirect(303, next || homeFor(locals.me.user.role));
	return { next, mode: url.searchParams.get('mode') === 'password' ? 'password' : 'code' };
};

const channelOf = (form: FormData) => (str(form, 'channel') === 'sms' ? 'sms' : 'whatsapp');

export const actions: Actions = {
	sendCode: async ({ request, locals }) => {
		const form = await request.formData();
		const phone = phoneFrom(str(form, 'phone'));
		const next = str(form, 'next');
		const channel = channelOf(form);
		try {
			await locals.api.anon('POST', '/auth/code', { phone, purpose: 'login', channel });
			return { step: 'code' as const, phone, next, channel };
		} catch (err) {
			return formError(err, { phone, next, channel });
		}
	},

	verifyCode: async ({ request, locals, cookies }) => {
		const form = await request.formData();
		const phone = str(form, 'phone');
		const next = str(form, 'next');
		try {
			const result = await locals.api.anon<SignIn>('POST', '/auth/signin/code', { phone, code: str(form, 'code') });
			return await continueSignIn(cookies, result, next, true);
		} catch (err) {
			return formError(err, { step: 'code' as const, phone, next });
		}
	},

	password: async ({ request, locals, cookies }) => {
		const form = await request.formData();
		const login = str(form, 'login');
		const next = str(form, 'next');
		try {
			const result = await locals.api.anon<SignIn>('POST', '/auth/signin/password', {
				login,
				password: form.get('password')?.toString() ?? ''
			});
			return await continueSignIn(cookies, result, next);
		} catch (err) {
			return formError(err, { mode: 'password', login, next });
		}
	},

	mfa: async ({ request, locals, cookies }) => {
		const form = await request.formData();
		const next = str(form, 'next');
		const token = cookies.get(MFA_COOKIE);
		if (!token) return fail(400, { error: 'Your sign-in expired. Start again.', next });
		try {
			const result = await locals.api.anon<SignIn>('POST', '/auth/mfa', { mfa_token: token, code: str(form, 'code') });
			return await continueSignIn(cookies, result, next, true);
		} catch (err) {
			return formError(err, { step: 'mfa' as const, next });
		}
	}
};
