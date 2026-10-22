import { describe, expect, it } from 'vitest';
import { catalogues, langFrom, translate, TWI_READY } from './i18n';

describe('i18n', () => {
	it('only uses keys that exist in English', () => {
		const english = new Set(Object.keys(catalogues.en));
		for (const key of Object.keys(catalogues.tw)) expect(english.has(key)).toBe(true);
	});

	it('falls back to English for anything not yet translated', () => {
		expect(translate('tw', 'banner.never_pay')).toBe(catalogues.tw['banner.never_pay'] ?? 'Never pay before you view a home.');
	});

	it('keeps renters on English until Twi is complete and reviewed', () => {
		if (!TWI_READY) expect(langFrom('tw')).toBe('en');
		expect(langFrom(undefined)).toBe('en');
	});
});
