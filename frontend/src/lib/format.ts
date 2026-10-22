// Dates and times in Ghana time (Africa/Accra, UTC+0 all year).

const TZ = 'Africa/Accra';

export function date(iso: string | null | undefined): string {
	if (!iso) return '—';
	return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: TZ }).format(
		new Date(iso)
	);
}

export function dateTime(iso: string | null | undefined): string {
	if (!iso) return '—';
	return new Intl.DateTimeFormat('en-GB', {
		weekday: 'short',
		day: 'numeric',
		month: 'short',
		hour: '2-digit',
		minute: '2-digit',
		timeZone: TZ
	}).format(new Date(iso));
}

export function day(iso: string | null | undefined): string {
	if (!iso) return '—';
	return new Intl.DateTimeFormat('en-GB', { weekday: 'short', day: 'numeric', month: 'short', timeZone: TZ }).format(
		new Date(iso.length === 10 ? `${iso}T12:00:00Z` : iso)
	);
}

/** "1 Nov", for availability on tickets and cards. */
export function shortDate(iso: string | null | undefined): string {
	if (!iso) return '—';
	return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', timeZone: TZ }).format(
		new Date(iso.length === 10 ? `${iso}T12:00:00Z` : iso)
	);
}

/** The design sets money with a space after the symbol: "GH₵3,500" -> "GH₵ 3,500". */
export function cedis(display: string): string {
	return display.replace(/^GH₵\s?/, 'GH₵ ');
}

/** "2 h ago", "Yesterday", "3 days ago": how long ago a message or event was. */
export function ago(iso: string | null | undefined): string {
	if (!iso) return '';
	const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
	if (mins < 60) return mins <= 1 ? 'Just now' : `${mins} min ago`;
	const hours = Math.round(mins / 60);
	if (hours < 24) return `${hours} h ago`;
	const days = Math.round(hours / 24);
	return days === 1 ? 'Yesterday' : days < 7 ? `${days} days ago` : date(iso);
}

/** "Ama Mensah" -> "AM", for the round initials badges. */
export function initials(name: string): string {
	return (
		name
			.split(/\s+/)
			.filter(Boolean)
			.slice(0, 2)
			.map((w) => w[0]?.toUpperCase())
			.join('') || 'A'
	);
}

export function bedrooms(n: number): string {
	return n === 0 ? 'Single room' : `${n} bedroom${n === 1 ? '' : 's'}`;
}

export function statusLabel(status: string): string {
	return status.replaceAll('_', ' ').replace(/^./, (c) => c.toUpperCase());
}

/** Today in Ghana as YYYY-MM-DD, for date inputs. */
export function today(): string {
	return new Date().toISOString().slice(0, 10);
}

/** Pesewas as Ghana cedis, e.g. 2880000 -> "GH₵28,800". */
export function ghs(pesewas: number | null | undefined): string {
	if (pesewas == null) return '—';
	const cedis = pesewas / 100;
	return `GH₵${cedis.toLocaleString('en-GH', { minimumFractionDigits: cedis % 1 ? 2 : 0, maximumFractionDigits: 2 })}`;
}

export const TENANCY_LABELS: Record<string, string> = {
	offered: 'Offer waiting',
	funding: 'Waiting for payment',
	funded: 'Payment held',
	disputed: 'Problem raised',
	release_pending: 'Release being checked',
	releasing: 'Paying the landlord',
	released: 'Paid to landlord',
	refunding: 'Refunding',
	refunded: 'Refunded',
	declined: 'Declined',
	withdrawn: 'Withdrawn',
	expired: 'Expired'
};

export function tenancyTone(status: string): string {
	if (['funded', 'released'].includes(status)) return 'ok';
	if (['offered', 'funding', 'release_pending', 'releasing', 'refunding'].includes(status)) return 'warn';
	if (status === 'disputed') return 'bad';
	return '';
}
