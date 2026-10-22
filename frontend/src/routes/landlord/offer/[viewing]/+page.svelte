<script lang="ts">
	// Offer a tenancy after a viewing: the terms in a card (as on the Landlord canvas's verification
	// steps), and a ticket beside it with the amounts and how the protected payment works.
	import { enhance } from '$app/forms';
	import FormError from '$lib/components/FormError.svelte';
	import { cedis, date, dateTime, initials, today } from '$lib/format';

	let { data, form } = $props();
	const v = $derived(data.viewing);
	const c = $derived(data.config);

	let lease = $state(12);
	let busy = $state(false);
	const cap = $derived(lease > 6 ? c.advance_cap_months_long : c.advance_cap_months_short);
	const inFourMonths = new Date(Date.now() + 120 * 86_400_000).toISOString().slice(0, 10);
	const fee = $derived((c.fee_bps / 100).toFixed(1).replace(/\.0$/, ''));
	const PAYER: Record<string, string> = { tenant: 'paid by the tenant', landlord: 'paid by you', split: 'split with the tenant' };
	const q = $derived(form?.quote);
</script>

<svelte:head><title>Offer a tenancy · Afe</title></svelte:head>

<a class="back" href="/account/viewings">← Viewings</a>
<div class="page-head">
	<span class="kicker">Protected payment</span>
	<h1>Offer a tenancy</h1>
</div>

<div class="who">
	<span class="avatar">{initials(v.other_name)}</span>
	<span class="who-t"><b>{v.other_name}</b><span class="small muted">{v.listing_title} · <span class="mono">{v.listing_reference}</span> · viewed {dateTime(v.requested_for)}</span></span>
</div>

{#if !c.enabled}
	<div class="notice"><b>Not open yet.</b><span>Protected payments start once Afe's payment partner has its licence. You'll get an SMS when you can offer tenancies here.</span></div>
{:else if v.status !== 'completed'}
	<div class="notice"><b>After the viewing.</b><span>You can offer a tenancy once the viewing has happened. Mark it as done on your <a href="/account/viewings">viewings page</a>.</span></div>
{:else if !data.payee}
	<div class="notice row spread"><span><b>Add a payout account first</b>, so Afe knows where to send the rent.</span><a class="btn sm" href="/landlord/payouts">Add payout account</a></div>
{:else}
	{#if c.free_until}
		<div class="notice ok"><b>Launch offer.</b><span>No protection fee on tenancies until {date(c.free_until)}. The tenant pays only the rent held.</span></div>
	{/if}
	<div class="detail">
		<form
			class="terms"
			method="post"
			action="?/quote"
			use:enhance={() => {
				busy = true;
				return async ({ update }) => {
					await update({ reset: false });
					busy = false;
				};
			}}
		>
			<div class="t-head">
				<span class="step-no">Terms</span>
				<h2>What you're offering</h2>
				<p>{v.other_name} sees these terms, accepts, and pays Afe's licensed payment partner. You can work out the amounts first.</p>
			</div>
			<FormError message={form?.error} />
			<div class="form-grid">
				<div>
					<label for="move_in_date">Move-in date</label>
					<input id="move_in_date" type="date" name="move_in_date" min={today()} max={inFourMonths} required value={form?.terms?.move_in_date ?? ''} />
				</div>
				<div>
					<label for="lease_months">Lease (months)</label>
					<input id="lease_months" type="number" name="lease_months" min="1" max="60" required bind:value={lease} />
				</div>
				<div>
					<label for="advance_months">Advance rent (months)</label>
					<input id="advance_months" type="number" name="advance_months" min="0" max={cap} required value={form?.terms?.advance_months ?? Math.min(6, cap)} />
					<p class="note" style="margin: 6px 0 0">The law caps advance rent at {cap} months for this lease.</p>
				</div>
				<div>
					<label for="deposit_months">Deposit (months)</label>
					<input id="deposit_months" type="number" name="deposit_months" min="0" max={c.max_deposit_months} required value={form?.terms?.deposit_months ?? 0} />
				</div>
			</div>
			<div class="t-foot">
				<button class="btn secondary" type="submit" disabled={busy}>Work out the amounts</button>
				<button class="btn" type="submit" formaction="?/offer" disabled={busy}>Send offer</button>
			</div>
		</form>

		<aside class="side">
			<div class="sum" style="--notch: var(--paper)">
				<div class="sum-top">
					<span class="label-mono">Amounts</span>
					{#if q}
						<div class="line2"><span>Held until move-in</span><span class="amt">{cedis(q.held_display)}</span></div>
						<div class="line2">
							<span>Protection fee ({fee}%, {PAYER[q.fee_payer] ?? q.fee_payer})</span>
							{#if q.fee_pesewas}<span class="amt">{cedis(q.fee_display)}</span>{:else}<span class="free">Free</span>{/if}
						</div>
						<div class="line2"><span>Tenant pays</span><span class="amt">{cedis(q.charge_display)}</span></div>
						{#if (form?.terms?.advance_months ?? 0) > q.advance_cap_months}
							<p class="flag" style="margin: 0">The law caps advance rent at {q.advance_cap_months} months for this lease. Lower it before you send the offer.</p>
						{/if}
					{:else}
						<p class="small muted" style="margin: 0">Set the terms and choose <b>Work out the amounts</b> to see what {v.other_name} pays and what you receive.</p>
					{/if}
				</div>
				<div class="tear"></div>
				<div class="sum-bot">
					<div class="total"><span>You receive</span><b>{q ? cedis(q.payout_display) : '—'}</b></div>
					<span class="fine">To {data.payee.masked}, after {v.other_name} confirms they've moved in.</span>
				</div>
			</div>

			<div>
				<h3 class="how">How it works</h3>
				<ol class="steps" style="margin: 0">
					<li>{v.other_name} accepts and pays Afe's licensed payment partner.</li>
					<li>The money is held until they confirm they've moved in.</li>
					<li>It's then paid to {data.payee.masked}.</li>
				</ol>
			</div>
			<p class="note" style="margin: 0">If the home isn't handed over, the tenant is refunded. Record the handover on the tenancy page on the move-in day.</p>
		</aside>
	</div>
{/if}

<style>
	.who {
		display: flex;
		gap: 12px;
		align-items: center;
	}
	.who-t {
		display: flex;
		flex-direction: column;
		gap: 2px;
		min-width: 0;
	}
	.terms {
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: 16px;
		padding: 28px;
		display: flex;
		flex-direction: column;
		gap: 22px;
	}
	.t-head {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	.t-head h2 {
		margin: 0;
		font-size: 26px;
	}
	.t-head p {
		margin: 0;
		font-size: 15px;
		color: var(--muted);
	}
	.step-no {
		font: 12px var(--font-mono);
		color: var(--warn);
	}
	.t-foot {
		display: flex;
		justify-content: space-between;
		gap: 12px;
		flex-wrap: wrap;
		border-top: 1px solid var(--hair);
		padding-top: 20px;
	}
	.side {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}
	.sum {
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: 16px;
		display: flex;
		flex-direction: column;
	}
	.sum-top,
	.sum-bot {
		padding: 20px;
		display: flex;
		flex-direction: column;
		gap: 12px;
		font-size: 15px;
	}
	.line2 {
		display: flex;
		justify-content: space-between;
		gap: 8px;
	}
	.amt {
		font-variant-numeric: tabular-nums;
		white-space: nowrap;
	}
	.free {
		color: var(--ok);
		font-weight: 600;
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
		font: 700 28px var(--font-display);
		color: var(--brand);
		font-variant-numeric: tabular-nums;
	}
	.fine {
		font-size: 13px;
		color: var(--muted);
		line-height: 1.5;
	}
	.how {
		margin: 0 0 10px;
		font-size: 18px;
	}
	@media (max-width: 520px) {
		.terms {
			padding: 20px;
		}
		.t-foot > :global(*) {
			flex: 1 1 100%;
		}
	}
	@media (prefers-color-scheme: dark) {
		.total b {
			color: var(--accent);
		}
	}
</style>
