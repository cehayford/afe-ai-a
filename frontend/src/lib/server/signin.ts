import { redirect, type Cookies } from '@sveltejs/kit';
import { dev } from '$app/environment';
import QRCode from 'qrcode';
import type { Role, SignIn } from '$lib/api/types';
import { MFA_COOKIE, setSession } from './api';

export function homeFor(role: Role): string {
	if (role === 'reviewer' || role === 'admin') return '/review';
	if (role === 'field_verifier') return '/field';
	if (role === 'landlord' || role === 'agent') return '/landlord';
	return '/';
}

/** Same-site paths only, so sign-in can't be used to send people elsewhere. */
export function safeNext(next: string | null): string {
	return next && next.startsWith('/') && !next.startsWith('//') && !next.includes('\\') ? next : '';
}

/** A Ghana number from the sign-in form: "24 412 3456" (after the +233 prefix), "024…" or "+233…". */
export function phoneFrom(value: string): string {
	const digits = value.replace(/\D/g, '');
	if (digits.length === 9) return `+233${digits}`;
	if (digits.length === 10 && digits.startsWith('0')) return `+233${digits.slice(1)}`;
	if (digits.length === 12 && digits.startsWith('233')) return `+${digits}`;
	return value; // the API explains what is wrong with it
}

/** Finish a sign-in step: set the session, or move to the authenticator step. With `showDone`
 *  (no page to go back to) the screen says what happened and where to go next, as in the design. */
export async function continueSignIn(cookies: Cookies, result: SignIn, next: string, showDone = false) {
	if (result.status === 'signed_in') {
		setSession(cookies, result);
		if (showDone && !safeNext(next)) return { step: 'done' as const, role: result.user.role };
		redirect(303, safeNext(next) || homeFor(result.user.role));
	}
	cookies.set(MFA_COOKIE, result.mfa_token, { path: '/', httpOnly: true, sameSite: 'lax', secure: !dev, maxAge: 300 });
	if (result.status === 'mfa_setup') {
		return {
			step: 'mfa_setup' as const,
			secret: result.totp_secret,
			qr: await QRCode.toDataURL(result.otpauth_uri, { margin: 1, width: 200 }),
			next
		};
	}
	return { step: 'mfa' as const, next };
}
