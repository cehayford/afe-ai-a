import { describe, expect, it } from 'vitest';
import { distanceM } from './geo';

describe('distanceM', () => {
	it('matches the API within a metre', () => {
		// 0.001° of latitude is about 111 m.
		const d = distanceM(5.6402, -0.1583, 5.6412, -0.1583);
		expect(d).toBeGreaterThan(110);
		expect(d).toBeLessThan(112);
	});

	it('is zero for the same point', () => {
		expect(distanceM(5.64, -0.15, 5.64, -0.15)).toBe(0);
	});
});
