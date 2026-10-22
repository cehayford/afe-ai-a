<script lang="ts">
	// The four-bar money trail from the Renter canvas: Paid, Held by Afe, Moved in, Landlord paid.
	import type { TenancyStatus } from '$lib/api/types';

	let { status }: { status: TenancyStatus } = $props();
	const reached = $derived(
		(
			{
				offered: 0,
				funding: 0,
				funded: 2,
				disputed: 2,
				release_pending: 3,
				releasing: 3,
				released: 4,
				refunding: 2,
				refunded: 2
			} as Record<string, number>
		)[status] ?? 0
	);
	const last = $derived(status === 'refunding' || status === 'refunded' ? 'Refunded to you' : 'Landlord paid');
</script>

<div class="flowbar" role="img" aria-label="Payment progress: {reached} of 4 steps">
	{#each ['Paid', 'Held by Afe', 'Moved in', last] as label, i}<div class:on={i < reached}>{label}</div>{/each}
</div>
