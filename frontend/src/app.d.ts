// See https://svelte.dev/docs/kit/types#app.d.ts
import type { Api } from '$lib/server/api';
import type { Me } from '$lib/api/types';

declare global {
	namespace App {
		interface Error {
			message: string;
			reasons?: string[];
		}
		interface Locals {
			api: Api;
			me: Me | null;
		}
	}
}

export {};
