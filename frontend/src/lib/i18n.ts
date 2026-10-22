// Language for the core renter journey (roadmap workstream B, decision B17).
//
// English is complete. The Twi catalogue is filled by a professional translator and checked by
// native speakers, especially the scam warnings: a wrong warning is worse than none. Until
// TWI_READY is set, the language switch stays hidden, and any missing Twi string falls back to
// English, so a half-finished catalogue can never reach renters.

export type Lang = 'en' | 'tw';

const en = {
	'banner.never_pay': 'Never pay before you view a home.',
	'banner.no_viewing_fee': 'Afe will never ask for a viewing fee.',
	'footer.checked': 'Afe checks every landlord and home in person before it is listed. Seen a scam?',
	'footer.check_link': 'Check a number or report it',
	'home.title': 'Homes checked in person by Afe',
	'home.lede':
		"Every landlord's Ghana Card is checked, every home is visited, and every photo is taken by Afe. If it's on Afe, it's real.",
	'search.area': 'Area',
	'search.all_areas': 'All areas',
	'search.size': 'Size',
	'search.max_rent': 'Max rent (GH₵ / month)',
	'search.submit': 'Search',
	'search.none': 'No verified homes match that search yet. Try another area or a higher budget.',
	'alerts.title': 'Get told when a home like this is listed',
	'alerts.sign_in': 'Sign in to get alerts',
	'alerts.save': 'Save this search',
	'areas.title': 'Neighbourhoods'
} as const;

export type MessageKey = keyof typeof en;

// Filled by the translator. Keys must match the English ones; leave a key out rather than guess.
const tw: Partial<Record<MessageKey, string>> = {};

/** Flip only when every key is translated and native speakers have reviewed the scam warnings. */
export const TWI_READY = false;

export const catalogues: Record<Lang, Partial<Record<MessageKey, string>>> = { en, tw };

export function translate(lang: Lang, key: MessageKey): string {
	return catalogues[lang][key] ?? en[key];
}

export function langFrom(cookie: string | undefined): Lang {
	return TWI_READY && cookie === 'tw' ? 'tw' : 'en';
}

/** Share of English keys that have a Twi translation (for the translator's progress). */
export function twiCoverage(): number {
	const keys = Object.keys(en);
	return keys.filter((k) => tw[k as MessageKey]).length / keys.length;
}
