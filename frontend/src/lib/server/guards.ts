import { error, fail, redirect, type ActionFailure } from '@sveltejs/kit';
import type { Role, Me } from '$lib/api/types';
import { ApiError } from './api';

/** Send people who aren't signed in to the sign-in page, and bring them back after. */
export function requireMe(me: Me | null, url: URL): Me {
	if (!me) redirect(303, `/signin?next=${encodeURIComponent(url.pathname + url.search)}`);
	return me;
}

export function requireRole(me: Me | null, url: URL, roles: Role[]): Me {
	const who = requireMe(me, url);
	if (!roles.includes(who.user.role)) error(403, 'Your account cannot open this page.');
	return who;
}

/** Turn an API error into a form failure the page can show; rethrow anything else. */
export function formError<E extends Record<string, unknown> = Record<never, never>>(
	err: unknown,
	extra: E = {} as E
): ActionFailure<E & { error: string }> {
	if (err instanceof ApiError) {
		const status = err.status >= 400 && err.status < 500 ? err.status : 400;
		return fail(status, { ...extra, error: err.detail });
	}
	throw err;
}

/** Load helper: a missing thing is a 404 page; other API errors become error pages. */
export async function load404<T>(promise: Promise<T>): Promise<T> {
	try {
		return await promise;
	} catch (err) {
		if (err instanceof ApiError) error(err.status === 403 ? 403 : err.status === 404 ? 404 : 502, err.message);
		throw err;
	}
}

export function str(form: FormData, name: string): string {
	const value = form.get(name);
	return typeof value === 'string' ? value.trim() : '';
}
