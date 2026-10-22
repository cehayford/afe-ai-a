<script lang="ts">
	// A protected payment, from the Renter canvas's "Protected checkout" and "Confirm move-in" views:
	// the money trail, what to do now (pay, or tick the move-in checks and release), and a ticket with
	// the amounts. Landlords see the same page with their side of it.
	import { enhance } from '$app/forms';
	import FormError from '$lib/components/FormError.svelte';
	import PayFlow from '$lib/components/PayFlow.svelte';
	import { cedis, dateTime, day, TENANCY_LABELS, tenancyTone } from '$lib/format';
	import { hydrated } from '$lib/hydrated.svelte';
	const js = hydrated();

	let { data, form } = $props();
	const t = $derived(data.tenancy);
	const can = (a: string) => t.actions.includes(a as never);
	const tenant = $derived(t.role === 'tenant');

	const REASONS: [string, string][] = [
		['not_delivered', "The home wasn't handed over"],
		['not_as_listed', "The home isn't what was listed"],
		['tenant_no_show', "The tenant didn't move in"],
		['access_refused', 'Access was refused on the move-in date'],
		['other', 'Something else']
	];
	const reasons = $derived(REASONS.filter(([k]) => (tenant ? k !== 'tenant_no_show' : !['not_delivered', 'not_as_listed'].includes(k))));

	// Move-in: every box ticked before the payment can be released.
	let ticks = $state([false, false, false]);
	const moveChecks = $derived(['I have the keys', 'The home matches the listing and photos', `I met the verified landlord, ${t.landlord_name}`]);
	const allTicked = $derived(ticks.every(Boolean));
	let problem = $state(false);
	let busy = $state(false);
	const done = () => {
		busy = true;
		return async ({ update }: { update: () => Promise<void> }) => {
			await update();
			busy = false;
		};
	};

	const heading = $derived(
		form?.done === '/confirm-move-in' || t.status === 'released'
			? tenant
				? 'Welcome home.'
				: 'Paid to you'
			: t.status === 'disputed' || form?.done === '/disputes'
				? tenant
					? 'Your money stays with Afe.'
					: 'Payment on hold'
				: can('confirm_move_in')
					? 'Confirm your move-in'
					: can('accept') || can('pay')
						? 'Pay your rent safely'
						: TENANCY_LABELS[t.status]
	);
</script>

<svelte:head><title>{t.reference} · Afe</title></svelte:head>

<div class="page-1000 tenancy">
	<a class="back" href="/tenancies">← Payments</a>
	<div class="page-head">
		<div class="row"><span class="tag soft">Protected payment</span><span class="pill {tenancyTone(t.status)}">{TENANCY_LABELS[t.status]}</span></div>
		<h1>{heading}</h1>
		<p>{t.listing_title} · {t.address}, {t.area} · {tenant ? `Landlord ${t.landlord_name}` : `Tenant ${t.tenant_name}`} · {t.reference}</p>
	</div>
	<PayFlow status={t.status} />

	<FormError message={form?.error} />
	{#if form?.done === '/review'}<p class="result">Thanks for your review. It helps other renters.</p>{/if}

	<div class="t-grid">
		<div class="t-main">
			{#if form?.done === '/confirm-move-in' || (t.status === 'released' && tenant)}
				<div class="card-done">
					<span class="done-mark">✓</span>
					<p>We're releasing {cedis(t.held_display)} to {t.landlord_name}. Your receipt is below{can('review') ? ', and you can now review this home' : ''}.</p>
				</div>
			{:else if t.status === 'disputed' || form?.done === '/disputes'}
				<div class="card-hold">
					<p>
						{tenant ? 'A member of our team will call you within one working day.' : 'An Afe reviewer will contact both of you.'} Nothing is released while
						the case is open.
					</p>
				</div>
			{/if}

			{#if can('accept') || can('pay')}
				<div class="stack-20">
					<div class="fact-block">
						<span class="lbl">Months of rent in advance</span>
						<div class="chips"><span class="chip on">{t.advance_months} {t.advance_months === 1 ? 'month' : 'months'}</span></div>
						<span class="note">Set in {t.landlord_name}'s offer. Afe caps advance rent at 6 months.</span>
					</div>
					<div class="fact-block">
						<span class="lbl">Pay with</span>
						<div class="methods">
							<div><b>MTN Mobile Money</b><span>Approve on your phone</span></div>
							<div><b>Telecel Cash</b><span>Approve on your phone</span></div>
							<div><b>Debit or credit card</b><span>Visa or Mastercard</span></div>
						</div>
						<span class="note">You choose on our payment partner's secure page. Offer open until {dateTime(t.offer_expires_at)}.</span>
					</div>
				</div>
			{/if}

			{#if can('confirm_move_in')}
				<div class="stack-20">
					<p class="lead">Once you confirm, we release {cedis(t.held_display)} to {t.landlord_name}. Tick each one that's true.</p>
					<form class="stack-20" method="post" action="?/confirm" enctype="multipart/form-data" use:enhance={done}>
						<div class="checks">
							{#each moveChecks as label, i}
								<label class="check tick-row">
									<input type="checkbox" bind:checked={ticks[i]} required />
									<span class="box24" aria-hidden="true">{ticks[i] ? '✓' : ''}</span>{label}
								</label>
							{/each}
						</div>
						<div>
							<label for="photo">A photo of the home today (optional, kept private)</label>
							<input id="photo" name="photo" type="file" accept="image/*" capture="environment" />
						</div>
						<button class="btn big" type="submit" disabled={(js.on && !allTicked) || busy}>Release payment to landlord</button>
					</form>
					<p class="small muted" style="margin: 0">Prefer WhatsApp? Send <span class="mono">MOVED IN {t.reference}</span> to Afe from the phone number on your account, then reply YES within 30 minutes.</p>
					{#if can('dispute')}
						<button type="button" class="btn danger-line block" style="height: 48px; font-size: 15px" onclick={() => (problem = !problem)} aria-expanded={problem}>
							Something's wrong. Keep my money held.
						</button>
					{/if}
				</div>
			{/if}

			{#if can('dispute') && (problem || !can('confirm_move_in'))}
				<details class="box" open={problem}>
					<summary>{can('confirm_move_in') ? 'Tell us what went wrong' : 'Something wrong?'}</summary>
					<form class="stack" method="post" action="?/dispute" use:enhance={done} style="margin-top: 12px">
						<p class="small" style="margin: 0">Raising a problem stops the payment from moving until an Afe reviewer decides.</p>
						<label for="reason">What went wrong</label>
						<select id="reason" name="reason" required>
							{#each reasons as [k, label]}<option value={k}>{label}</option>{/each}
						</select>
						<label for="details">Details</label>
						<textarea id="details" name="details" minlength="20" maxlength="4000" required></textarea>
						<button class="btn danger" type="submit" disabled={busy}>Keep my money held</button>
					</form>
				</details>
			{/if}

			{#if can('withdraw')}
				<form class="box stack" method="post" action="?/withdraw" use:enhance={done}>
					<p style="margin: 0">Waiting for {t.tenant_name} to accept, until {dateTime(t.offer_expires_at)}.</p>
					<div><button class="btn quiet md" type="submit">Withdraw offer</button></div>
				</form>
			{/if}
			{#if can('record_move_in')}
				<form class="box stack" method="post" action="?/evidence" use:enhance={done}>
					<h2 class="bx">Record the handover</h2>
					<p class="small" style="margin: 0">If the tenant doesn't confirm, this record lets Afe release the payment after the move-in period.</p>
					<label for="note">What happened</label>
					<textarea id="note" name="note" minlength="10" maxlength="2000" required placeholder="Keys handed to the tenant on Saturday at 10am; meter readings photographed."></textarea>
					<div><button class="btn md" type="submit">Save record</button></div>
				</form>
			{/if}

			{#if t.dispute}
				<div class="box">
					<h2 class="bx">Problem raised</h2>
					<p class="small muted">{t.dispute.opened_by_name} · {dateTime(t.dispute.created_at)} · {t.dispute.reason_label}</p>
					<p>{t.dispute.details}</p>
					{#if t.dispute.status === 'resolved'}
						<p class="result {t.dispute.decision === 'release' ? '' : 'no'}">Afe decided: {t.dispute.decision === 'release' ? 'pay the landlord' : 'refund the tenant'}. {t.dispute.decision_note}</p>
					{/if}
				</div>
			{/if}
			{#if t.landlord_evidence}
				<div class="box">
					<h2 class="bx">Landlord's move-in record</h2>
					<p class="small muted">{dateTime(t.landlord_evidence_at)}</p>
					<p>{t.landlord_evidence}</p>
				</div>
			{/if}
			{#if t.review}
				<div class="box">
					<h2 class="bx">Your review · <span class="stars">{'★'.repeat(t.review.rating)}{'☆'.repeat(5 - t.review.rating)}</span></h2>
					<p>{t.review.body}</p>
				</div>
			{/if}
			{#if can('review')}
				<form class="box stack" method="post" action="?/review" use:enhance={done}>
					<h2 class="bx">Review your landlord</h2>
					<fieldset class="rating">
						<legend class="small">Rating</legend>
						{#each [1, 2, 3, 4, 5] as n}<label class="chip" style="height: 40px"><input type="radio" name="rating" value={n} required />{n} ★</label>{/each}
					</fieldset>
					<label for="body">What should other renters know?</label>
					<textarea id="body" name="body" minlength="20" maxlength="2000" required></textarea>
					<div><button class="btn md" type="submit">Post review</button></div>
				</form>
			{/if}

			<div class="box">
				<h2 class="bx">Terms</h2>
				<dl class="kv">
					<dt>Monthly rent</dt><dd>{t.rent_display}</dd>
					<dt>Lease</dt><dd>{t.lease_months} months from {day(t.move_in_date)}</dd>
					<dt>Deposit</dt><dd>{t.deposit_months ? `${t.deposit_months} months` : 'None'}</dd>
					{#if !tenant}<dt>You receive</dt><dd><strong>{t.payout_display}</strong>{t.payee ? ` to ${t.payee}` : ''}</dd>{/if}
				</dl>
				{#if t.has_move_in_photo || t.has_receipt || t.has_agreement}
					<div class="row" style="margin-top: 14px">
						{#if t.has_receipt}<a class="btn quiet sm" href="/tenancies/{t.reference}/receipt" target="_blank" rel="noopener">Receipt (PDF)</a>{/if}
						{#if t.has_agreement}<a class="btn quiet sm" href="/tenancies/{t.reference}/agreement" target="_blank" rel="noopener">Tenancy summary (PDF)</a>{/if}
						{#if t.has_move_in_photo}<a class="btn quiet sm" href="/tenancies/{t.reference}/move-in-photo" target="_blank" rel="noopener">Move-in photo</a>{/if}
					</div>
				{/if}
			</div>
		</div>

		<aside class="sum" style="--notch: var(--paper)">
			<div class="sum-top">
				<div class="sum-title">{t.listing_title}, {t.area}</div>
				<div class="line2"><span>{t.deposit_months ? `Rent × ${t.advance_months} months and deposit` : `Rent × ${t.advance_months} months`}</span><span class="num">{cedis(t.held_display)}</span></div>
				<div class="line2">
					<span>Protection fee{t.fee_pesewas && t.fee_payer !== 'tenant' ? (t.fee_payer === 'split' ? ' (split with landlord)' : ' (paid by landlord)') : ''}</span>
					{#if t.fee_pesewas}<span class="num">{cedis(t.fee_display)}</span>{:else}<span class="free">Free</span>{/if}
				</div>
				{#if !t.fee_pesewas}<div class="offer">Launch offer: no protection fee.</div>{/if}
			</div>
			<div class="tear"></div>
			<div class="sum-bot">
				<div class="total"><span>{tenant ? 'Total held by Afe' : 'Held for you'}</span><b>{cedis(tenant ? t.charge_display : t.held_display)}</b></div>
				{#if can('accept')}
					<form method="post" action="?/accept" use:enhance={done}><button class="btn big" type="submit" disabled={busy}>Pay {cedis(t.charge_display)}</button></form>
					<form method="post" action="?/decline" use:enhance={done}><button class="btn quiet block" type="submit" disabled={busy}>Decline the offer</button></form>
				{:else if can('pay')}
					<form method="post" action="?/pay"><button class="btn big" type="submit">Finish paying {cedis(t.charge_display)}</button></form>
				{/if}
				<span class="fine">The landlord is paid only after you confirm move-in, and only to their verified, name-matched account.</span>
			</div>
		</aside>
	</div>
	<p class="note">Afe never asks you to pay a landlord directly. If anyone asks for money outside this page, <a href="/check" data-section="report">report it</a>.</p>
</div>

<style>
	.tenancy {
		padding-top: 12px;
	}
	.tenancy h1 {
		font-size: 34px;
		line-height: 1.1;
	}
	.t-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 320px), 1fr));
		gap: 24px;
		align-items: start;
	}
	.t-main,
	.stack-20 {
		display: flex;
		flex-direction: column;
		gap: 20px;
	}
	.fact-block {
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.lbl {
		font-size: 14px;
		font-weight: 600;
	}
	.methods {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.methods div {
		display: flex;
		flex-direction: column;
		gap: 2px;
		padding: 12px 14px;
		border-radius: 8px;
		border: 1px solid var(--line);
		background: var(--surface);
		font-size: 15px;
	}
	.methods b {
		font-weight: 600;
	}
	.methods span {
		font-size: 13px;
		color: var(--muted);
	}
	.lead {
		margin: 0;
		font-size: 16px;
		color: var(--muted);
	}
	.tick-row input {
		position: absolute;
		opacity: 0;
		width: 1px;
		height: 1px;
	}
	.tick-row {
		position: relative;
	}
	.box24 {
		width: 24px;
		height: 24px;
		flex: 0 0 auto;
		border-radius: 6px;
		border: 2px solid var(--line);
		background: var(--surface);
		color: #fff;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 14px;
		font-weight: 700;
	}
	.tick-row:has(input:checked) .box24 {
		border: 0;
		background: var(--brand);
	}
	.tick-row:has(input:focus-visible) .box24 {
		outline: 2px solid var(--amber);
		outline-offset: 2px;
	}
	.card-done,
	.card-hold {
		border-radius: 16px;
		padding: 20px 24px;
		display: flex;
		gap: 14px;
		align-items: center;
	}
	.card-done {
		background: var(--ok-soft);
	}
	.card-done .done-mark {
		width: 44px;
		height: 44px;
		flex: none;
		font-size: 20px;
		background: var(--surface);
	}
	.card-hold {
		background: var(--surface);
		border: 2px solid var(--warn-strong);
	}
	.card-done p,
	.card-hold p {
		margin: 0;
		font-size: 15.5px;
		line-height: 1.55;
	}
	.bx {
		margin: 0 0 12px;
		font-size: 20px;
	}
	.sum {
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: 16px;
		display: flex;
		flex-direction: column;
	}
	.sum-top {
		padding: 20px;
		display: flex;
		flex-direction: column;
		gap: 12px;
		font-size: 15px;
	}
	.sum-title {
		font: 700 19px var(--font-display);
	}
	.line2 {
		display: flex;
		justify-content: space-between;
		gap: 8px;
	}
	.free {
		color: var(--ok);
		font-weight: 600;
	}
	.offer {
		font-size: 12.5px;
		color: var(--warn);
	}
	.sum-bot {
		padding: 20px;
		display: flex;
		flex-direction: column;
		gap: 12px;
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
	@media (prefers-color-scheme: dark) {
		.total b {
			color: var(--accent);
		}
	}
</style>
