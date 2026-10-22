// Server-side client for the Afe API. Only the frontend's server talks to the API: the
// browser never sees an access or refresh token (they live in httpOnly cookies here).

import { env } from '$env/dynamic/private';
import { dev } from '$app/environment';
import type { Cookies, RequestEvent } from '@sveltejs/kit';
import type { Envelope, SignIn } from '$lib/api/types';

export const API_URL = (env.AFE_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');

export const ACCESS_COOKIE = 'afe_at';
export const REFRESH_COOKIE = 'afe_rt';
export const MFA_COOKIE = 'afe_mfa';

export class ApiError extends Error {
	constructor(
		public status: number,
		public code: string,
		message: string,
		public reasons: string[] = []
	) {
		super(message);
	}

	/** One line for a form: the message plus any reasons. */
	get detail(): string {
		return this.reasons.length ? `${this.message} ${this.reasons.join(' ')}` : this.message;
	}
}

const cookieBase = { path: '/', httpOnly: true, sameSite: 'lax' as const, secure: !dev };

export function setSession(cookies: Cookies, session: SignIn): void {
	cookies.set(ACCESS_COOKIE, session.access_token, { ...cookieBase, maxAge: session.expires_in });
	cookies.set(REFRESH_COOKIE, session.refresh_token, { ...cookieBase, maxAge: 60 * 60 * 24 * 30 });
	cookies.delete(MFA_COOKIE, { path: '/' });
}

export function clearSession(cookies: Cookies): void {
	for (const name of [ACCESS_COOKIE, REFRESH_COOKIE, MFA_COOKIE]) cookies.delete(name, { path: '/' });
}

/** Seconds left on a JWT, read without verifying (the API verifies). */
function secondsLeft(token: string): number {
	try {
		const payload = JSON.parse(Buffer.from(token.split('.')[1], 'base64url').toString());
		return payload.exp - Date.now() / 1000;
	} catch {
		return -1;
	}
}

type Body = Record<string, unknown> | unknown[] | FormData | undefined;

export class Api {
	private refreshing: Promise<boolean> | null = null;

	constructor(
		private cookies: Cookies,
		private fetchFn: typeof fetch,
		private device: string,
		private clientAddress = ''
	) {}

	/** Headers every API call carries: the browser's user agent, and its address for rate limits. */
	private baseHeaders(): Record<string, string> {
		const headers: Record<string, string> = { 'X-Client-Device': this.device };
		if (this.clientAddress) headers['X-Forwarded-For'] = this.clientAddress;
		const deviceId = this.cookies.get('afe_dev');
		if (deviceId) headers['X-Afe-Device-Id'] = deviceId;
		return headers;
	}

	get signedIn(): boolean {
		return Boolean(this.cookies.get(ACCESS_COOKIE) || this.cookies.get(REFRESH_COOKIE));
	}

	/** Refresh once per request, however many loads ask at the same time. */
	private refresh(): Promise<boolean> {
		if (!this.refreshing) {
			this.refreshing = (async () => {
				const token = this.cookies.get(REFRESH_COOKIE);
				if (!token) return false;
				try {
					const session = await this.raw<SignIn>('POST', '/auth/refresh', { refresh_token: token }, false);
					setSession(this.cookies, session);
					return true;
				} catch {
					clearSession(this.cookies);
					return false;
				}
			})();
		}
		return this.refreshing;
	}

	async ensureFresh(): Promise<void> {
		const access = this.cookies.get(ACCESS_COOKIE);
		if ((!access || secondsLeft(access) < 30) && this.cookies.get(REFRESH_COOKIE)) await this.refresh();
	}

	private async raw<T>(method: string, path: string, body: Body, auth: boolean): Promise<T> {
		const headers: Record<string, string> = { Accept: 'application/json', ...this.baseHeaders() };
		const access = this.cookies.get(ACCESS_COOKIE);
		if (auth && access) headers.Authorization = `Bearer ${access}`;
		let payload: BodyInit | undefined;
		if (body instanceof FormData) payload = body;
		else if (body !== undefined) {
			headers['Content-Type'] = 'application/json';
			payload = JSON.stringify(body);
		}
		let res: Response;
		try {
			res = await this.fetchFn(`${API_URL}/api/v1${path}`, { method, headers, body: payload });
		} catch {
			throw new ApiError(503, 'unavailable', 'Afe is not reachable right now. Try again in a moment.');
		}
		const json = (await res.json().catch(() => null)) as Envelope<T> | null;
		if (!res.ok || !json) {
			const err = json?.error;
			throw new ApiError(res.status, err?.code ?? 'error', err?.message ?? `Request failed (${res.status}).`, err?.reasons ?? []);
		}
		return json.data as T;
	}

	/** Call the API; on an expired session, refresh once and retry. */
	async request<T>(method: string, path: string, body?: Body): Promise<T> {
		await this.ensureFresh();
		try {
			return await this.raw<T>(method, path, body, true);
		} catch (err) {
			if (err instanceof ApiError && err.status === 401 && err.code === 'not_authenticated' && (await this.refresh())) {
				return this.raw<T>(method, path, body, true);
			}
			throw err;
		}
	}

	/** Like request, but also returns the envelope's meta. */
	async withMeta<T>(path: string): Promise<{ data: T; meta: Record<string, unknown> }> {
		await this.ensureFresh();
		const headers: Record<string, string> = { Accept: 'application/json', ...this.baseHeaders() };
		const access = this.cookies.get(ACCESS_COOKIE);
		if (access) headers.Authorization = `Bearer ${access}`;
		const res = await this.fetchFn(`${API_URL}/api/v1${path}`, { headers });
		const json = (await res.json()) as Envelope<T>;
		if (!res.ok) throw new ApiError(res.status, json.error?.code ?? 'error', json.error?.message ?? 'Request failed.', json.error?.reasons);
		return { data: json.data as T, meta: json.meta };
	}

	get<T>(path: string) {
		return this.request<T>('GET', path);
	}
	post<T>(path: string, body?: Body) {
		return this.request<T>('POST', path, body ?? {});
	}
	patch<T>(path: string, body: Body) {
		return this.request<T>('PATCH', path, body);
	}
	del<T>(path: string) {
		return this.request<T>('DELETE', path);
	}
	/** Sign-in calls: no bearer token. */
	anon<T>(method: string, path: string, body?: Body) {
		return this.raw<T>(method, path, body, false);
	}

	/** Pass a request through to the API with this session's token (used by the proxy). */
	async forward(method: string, path: string, init: { body?: BodyInit | null; contentType?: string | null }) {
		await this.ensureFresh();
		const headers: Record<string, string> = this.baseHeaders();
		const access = this.cookies.get(ACCESS_COOKIE);
		if (access) headers.Authorization = `Bearer ${access}`;
		if (init.contentType) headers['Content-Type'] = init.contentType;
		return this.fetchFn(`${API_URL}/api/v1${path}`, {
			method,
			headers,
			body: init.body,
			// @ts-expect-error Node's fetch needs duplex for streamed bodies
			duplex: 'half'
		});
	}
}

export function createApi(event: RequestEvent): Api {
	let address = '';
	try {
		address = event.getClientAddress();
	} catch {
		// Not available while prerendering; the API then limits by the web server's address.
	}
	return new Api(event.cookies, event.fetch, event.request.headers.get('user-agent') ?? '', address);
}
