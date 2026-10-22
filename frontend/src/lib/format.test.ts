import { describe, expect, it } from 'vitest';
import { bedrooms, date, day, statusLabel, ghs } from './format';

describe('format', () => {
	it('formats dates in Ghana time', () => {
		expect(date('2026-11-14T10:30:00Z')).toBe('14 Nov 2026');
		expect(date(null)).toBe('—');
		expect(day('2026-11-14')).toBe('Sat 14 Nov');
	});

	it('names room counts the way listings do', () => {
		expect(bedrooms(0)).toBe('Single room');
		expect(bedrooms(1)).toBe('1 bedroom');
		expect(bedrooms(3)).toBe('3 bedrooms');
	});

	it('turns statuses into words', () => {
		expect(statusLabel('pending_review')).toBe('Pending review');
		expect(statusLabel('no_show')).toBe('No show');
	});
});

describe('ghs', () => {
	it('shows whole cedis without decimals and part cedis with two', () => {
		expect(ghs(2_880_000)).toBe('GH₵28,800');
		expect(ghs(12_345)).toBe('GH₵123.45');
		expect(ghs(null)).toBe('—');
	});
});
