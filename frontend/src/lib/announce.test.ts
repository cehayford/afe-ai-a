import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { announce, announcer } from './announce.svelte';

describe('announce', () => {
	beforeEach(() => {
		vi.useFakeTimers();
		announcer.text = '';
	});
	afterEach(() => vi.useRealTimers());

	it('empties the live region, then puts the message in it', () => {
		announcer.text = 'Saved.';
		announce('Decision saved.');
		expect(announcer.text).toBe('');
		vi.advanceTimersByTime(150);
		expect(announcer.text).toBe('Decision saved.');
	});

	it('says the same message twice in a row', () => {
		announce('Decision saved.');
		vi.advanceTimersByTime(150);
		announce('Decision saved.');
		expect(announcer.text).toBe('');
		vi.advanceTimersByTime(150);
		expect(announcer.text).toBe('Decision saved.');
	});

	it('says only the latest of two quick messages', () => {
		announce('Uploading…');
		announce('Photo saved.');
		vi.advanceTimersByTime(150);
		expect(announcer.text).toBe('Photo saved.');
	});
});
