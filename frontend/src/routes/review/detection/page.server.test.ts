import { describe, expect, it } from 'vitest';
import { load } from './+page.server';

describe('Models page loader', () => {
	it('still loads the models and their mode controls when the weekly history and the copilot numbers fail', async () => {
		const locals = {
			api: {
				withMeta: async () => ({ data: [{ name: 'price' }], meta: { versions: [] } }),
				get: async () => {
					throw new Error('history failed');
				}
			}
		};
		const out = await load({ locals } as never);
		expect(out).toEqual({ detectors: [{ name: 'price' }], versions: [], history: [], copilot: null });
	});
});
