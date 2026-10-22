// Browser-side calls for the field app. They go to this frontend's /api/v1 proxy, which
// adds the verifier's token server-side; the browser never holds a token.

export class FieldError extends Error {
	constructor(
		message: string,
		public status: number
	) {
		super(message);
	}
	get retryable(): boolean {
		return this.status === 0 || this.status >= 500 || this.status === 408 || this.status === 429;
	}
}

export async function call<T>(path: string, init: { method?: string; json?: unknown; form?: FormData } = {}) {
	const headers: Record<string, string> = { Accept: 'application/json' };
	let body: BodyInit | undefined;
	if (init.json !== undefined) {
		headers['Content-Type'] = 'application/json';
		body = JSON.stringify(init.json);
	} else if (init.form) body = init.form;
	let res: Response;
	try {
		res = await fetch(`/api/v1${path}`, { method: init.method ?? 'GET', headers, body, credentials: 'same-origin' });
	} catch {
		throw new FieldError('No connection right now.', 0);
	}
	const payload = await res.json().catch(() => null);
	if (!res.ok) throw new FieldError(payload?.error?.message ?? `Request failed (${res.status}).`, res.status);
	return payload as { data: T; meta: Record<string, unknown> };
}
