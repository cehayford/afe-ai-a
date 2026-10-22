<script lang="ts">
	// The fake payment partner's checkout, styled as a ticket: what is being paid, the amount after the
	// tear, and one button. Only used with the test payment provider; no money moves.
	import FormError from '$lib/components/FormError.svelte';
	import { cedis } from '$lib/format';

	let { data, form } = $props();
	let paying = $state(false);
</script>

<svelte:head><title>Test checkout · Afe</title></svelte:head>

<div class="page-640 checkout">
	<span class="tag warn" style="align-self: center">Test payment · no money moves</span>
	<div class="ticket" style="--notch: var(--paper)">
		<div class="t-top">
			<span class="label-mono">{data.payment.purpose === 'featured_listing' ? 'Featured listing' : 'Verification fee'}</span>
			<span class="mono small muted">{data.payment.reference}</span>
		</div>
		<div class="tear"></div>
		<div class="t-bot">
			<div class="total"><span>Total</span><b>{cedis(data.payment.amount_display)}</b></div>
			<FormError message={form?.error} />
			{#if data.payment.status === 'pending'}
				<form method="post" onsubmit={() => (paying = true)}><button class="btn big" type="submit" disabled={paying}>{paying ? 'Paying…' : 'Pay with test mobile money'}</button></form>
			{:else}
				<p class="muted" style="margin: 0">This payment is {data.payment.status}.</p>
			{/if}
		</div>
	</div>
</div>

<style>
	.checkout {
		max-width: 440px;
		padding: 32px 0;
		gap: 16px;
	}
	.ticket {
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: 16px;
		display: flex;
		flex-direction: column;
	}
	.t-top,
	.t-bot {
		padding: 22px;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.t-bot {
		gap: 14px;
	}
	.total {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 8px;
	}
	.total span {
		font-weight: 600;
	}
	.total b {
		font: 700 30px var(--font-display);
		color: var(--brand);
		font-variant-numeric: tabular-nums;
	}
	.t-bot form .btn {
		width: 100%;
	}
	@media (prefers-color-scheme: dark) {
		.total b {
			color: var(--accent);
		}
	}
</style>
