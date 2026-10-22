<script lang="ts">
	// Payments tab of My Afe (Renter canvas): each protected payment with its four-bar money trail.
	import MyAfe from '$lib/components/shell/MyAfe.svelte';
	import PayFlow from '$lib/components/PayFlow.svelte';
	import { cedis, day, TENANCY_LABELS } from '$lib/format';

	let { data } = $props();
	const status = (t: (typeof data.tenancies)[number]) =>
		({
			offered: `Offer from ${t.landlord_name}: accept and pay to secure the home.`,
			funding: 'Waiting for your payment to go through.',
			funded: `Held by Afe. Waiting for you to confirm move-in on ${day(t.move_in_date)}.`,
			disputed: 'On hold: a problem is open and an Afe reviewer is looking at it.',
			release_pending: 'Release being checked.',
			releasing: `Paying ${t.landlord_name}.`,
			released: `Released to ${t.landlord_name}. Your receipt is on the payment page.`,
			refunding: 'Refunding you.',
			refunded: 'Refunded to you.'
		})[t.status as string] ?? TENANCY_LABELS[t.status];
</script>

<svelte:head><title>Payments · Afe</title></svelte:head>

<MyAfe me={data.me!}>
	<h2 class="sr">Payments</h2>
	{#if data.tenancies.length}
		{#each data.tenancies as t (t.reference)}
			<a class="pay-card" href="/tenancies/{t.reference}">
				<div class="pay-head">
					<span class="t">{t.listing_title}, {t.area}</span>
					<span class="amt">{cedis(t.role === 'tenant' ? t.charge_display : t.held_display)}</span>
				</div>
				<PayFlow status={t.status} />
				<span class="st">{t.role === 'tenant' ? status(t) : `Tenant ${t.tenant_name} · ${TENANCY_LABELS[t.status]}`}</span>
			</a>
		{/each}
	{:else}
		<p class="muted" style="margin: 0; font-size: 15px">No payments yet. After a viewing, the landlord can offer you the tenancy, and you pay through Afe.</p>
	{/if}
</MyAfe>

<style>
	.pay-card {
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: 12px;
		padding: 20px;
		display: flex;
		flex-direction: column;
		gap: 16px;
		color: var(--ink);
	}
	.pay-card:hover {
		border-color: var(--brand);
		color: var(--ink);
	}
	.pay-head {
		display: flex;
		justify-content: space-between;
		gap: 12px;
		flex-wrap: wrap;
	}
	.t {
		font: 700 18px var(--font-display);
	}
	.amt {
		font: 700 20px var(--font-display);
		color: var(--brand);
		font-variant-numeric: tabular-nums;
	}
	.st {
		font-size: 14px;
		color: var(--muted);
	}
	@media (prefers-color-scheme: dark) {
		.amt {
			color: var(--accent);
		}
	}
</style>
