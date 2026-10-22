<script lang="ts">
	// Fees paid to Afe (the "Afe Missing Features" canvas, Account › Payments): filter pills, a notice
	// when one is waiting, and the table-style list with each payment's status and, when it's still
	// waiting, a way back to the checkout.
	import { cedis, date } from '$lib/format';

	let { data } = $props();
	const PURPOSE: Record<string, string> = {
		verification_fee: 'Verification fee',
		featured_listing: 'Featured listing',
		subscription: 'Landlord tools plan'
	};
	const STATUS: Record<string, [string, string]> = {
		pending: ['Waiting', 'warn'],
		paid: ['Paid', 'ok'],
		waived: ['Waived', 'quiet'],
		failed: ['Failed', 'bad']
	};
	type Filter = 'all' | 'paid' | 'pending';
	let filter = $state<Filter>('all');
	const rows = $derived(data.payments.filter((p) => filter === 'all' || p.status === filter));
	const waiting = $derived(data.payments.filter((p) => p.status === 'pending'));
</script>

<svelte:head><title>Fees paid · Afe</title></svelte:head>

<div class="head">
	<div class="page-head">
		<h2 class="h1ish">Fees paid</h2>
		<p>Everything you paid through Afe's payment partner: verification fees, featured listings and plans. Rent held with Afe is on each tenancy.</p>
	</div>
	<div class="pills" role="group" aria-label="Show">
		{#each [['all', 'All'], ['paid', 'Paid'], ['pending', 'Waiting']] as [k, label] (k)}
			<button type="button" aria-pressed={filter === k} onclick={() => (filter = k as Filter)}>{label}</button>
		{/each}
	</div>
</div>

{#if waiting.length}
	<div class="notice">
		<b>{waiting.length} waiting.</b>
		<span>{waiting.length === 1 ? `The ${(PURPOSE[waiting[0].purpose] ?? 'payment').toLowerCase()}${waiting[0].subject ? ` for ${waiting[0].subject}` : ''} isn't paid yet.` : 'Some payments are not finished yet.'}</span>
	</div>
{/if}

{#if data.payments.length}
	<div class="scroll">
		<table class="q wide-t">
			<thead><tr><th>What for</th><th>Reference</th><th>Date</th><th>Amount</th><th>Status</th></tr></thead>
			<tbody>
				{#each rows as p (p.reference)}
					<tr>
						<td><b>{PURPOSE[p.purpose] ?? p.purpose}</b>{#if p.subject}<br /><small>{p.subject}</small>{/if}{#if p.note}<br /><span class="muted small">{p.note}</span>{/if}</td>
						<td><span class="mono">{p.reference}</span></td>
						<td class="nowrap">{date(p.paid_at ?? p.created_at)}</td>
						<td class="amt">{cedis(p.amount_display)}</td>
						<td>
							<span class="st">
								<span class="pill {STATUS[p.status]?.[1] ?? 'quiet'}">{STATUS[p.status]?.[0] ?? p.status}</span>
								{#if p.status === 'pending' && p.checkout_url}<a class="btn sm" href={p.checkout_url}>Finish paying</a>{/if}
								<a class="small" href="/account/payments/{p.reference}/document" target="_blank" rel="noopener">{p.status === 'pending' || p.status === 'failed' ? 'Invoice' : 'Receipt'} (PDF)</a>
							</span>
						</td>
					</tr>
				{:else}
					<tr><td colspan="5" class="muted">No payments here.</td></tr>
				{/each}
			</tbody>
		</table>
	</div>
{:else}
	<div class="empty">No payments yet. Verification fees and featured listings you pay for appear here.</div>
{/if}
<p class="note" style="margin: 0">Afe never asks you to pay to a personal number. If anyone does, <a href="/check" data-section="report">report it</a>.</p>

<style>
	.head {
		display: flex;
		justify-content: space-between;
		align-items: flex-end;
		gap: 16px;
		flex-wrap: wrap;
	}
	.h1ish {
		font-size: 24px;
	}
	.wide-t {
		min-width: 640px;
	}
	.nowrap {
		white-space: nowrap;
	}
	.amt {
		font: 700 17px var(--font-display);
		white-space: nowrap;
		font-variant-numeric: tabular-nums;
	}
	.st {
		display: flex;
		flex-direction: column;
		gap: 8px;
		align-items: flex-start;
	}
</style>
