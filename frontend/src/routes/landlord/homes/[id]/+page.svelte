<script lang="ts">
	// One home in verification, in the style of the Landlord canvas: where it stands (the stepper),
	// what to do next (pay the fee, create the listing), its listings, and its documents with an
	// upload tile.
	import { enhance } from '$app/forms';
	import FormError from '$lib/components/FormError.svelte';
	import StageSteps from '$lib/components/StageSteps.svelte';
	import { bedrooms, cedis, date, statusLabel, today } from '$lib/format';
	import { hydrated } from '$lib/hydrated.svelte';
	const js = hydrated();

	let { data, form } = $props();
	const home = $derived(data.home);
	const unit = $derived(home.unit);
	const isAgent = $derived(data.me?.user.role === 'agent');
	let docType = $state('indenture');
	let docFile = $state('');
	let busy = $state(false);
	const done = () => {
		busy = true;
		return async ({ update }: { update: () => Promise<void> }) => {
			await update();
			busy = false;
			docFile = '';
		};
	};
	const docTypes = $derived(
		(isAgent ? [['owner_authorisation', 'Letter of authority']] : []).concat([
			['indenture', 'Indenture'],
			['land_title', 'Land title certificate'],
			['lands_commission_search', 'Lands Commission search'],
			['site_plan', 'Site plan']
		])
	);
	const listingTone = (s: string) => (s === 'live' ? 'ok' : s === 'draft' || s === 'pending_review' ? 'warn' : 'quiet');
</script>

<svelte:head><title>{unit.digital_address} · Afe</title></svelte:head>

<a class="back" href="/landlord">← Dashboard</a>
<div class="page-head">
	<span class="mono small muted">{unit.digital_address}</span>
	<h1>{unit.unit_label || unit.property_type_label}</h1>
	<p>{unit.area.name} · {bedrooms(unit.bedrooms)} · {unit.bathrooms} bath{unit.bathrooms === 1 ? '' : 's'} · {unit.property_type_label}{unit.landmark ? ` · ${unit.landmark}` : ''}</p>
</div>

{#if data.payment}
	<p class="result {data.payment.status === 'paid' ? '' : 'no'}">
		{#if data.payment.status === 'paid'}Payment received: {data.payment.amount_display}. Receipt {data.payment.reference}.
		{:else if data.payment.status === 'pending'}We're waiting for confirmation from the payment partner. Refresh in a minute.
		{:else}The payment did not go through. You can try again.{/if}
	</p>
{/if}
{#if form?.uploaded}<p class="result">Document uploaded. An Afe reviewer reads it next.</p>{/if}

<div class="detail">
	<div class="col">
		<section aria-labelledby="ver-h">
			<h2 id="ver-h" class="sect">Verification</h2>
			<StageSteps stage={home.stage} feeRequired={home.fee_required} />
			{#if home.visit_scheduled_for}
				<div class="notice ok" style="margin: 0"><b>Visit booked.</b><span>An Afe verifier visits on {date(home.visit_scheduled_for)}. They'll call you first.</span></div>
			{/if}
			{#if home.verification && home.verification.status !== 'approved'}
				<p class="flag" style="margin: 8px 0 0">Decision on {date(home.verification.decided_at)}: {home.verification.note || home.verification.reason_codes.join(', ')}</p>
			{/if}
		</section>

		{#if home.stage === 'fee'}
			<form class="step-card" method="post" action="?/pay">
				<span class="kick">Next step</span>
				<h2>Pay the verification fee</h2>
				<p>The fee pays for an Afe verifier to visit the home. Pay by mobile money (MTN, Telecel, AT) or card on our payment partner's page.</p>
				<FormError message={form?.form === 'pay' ? form.error : null} />
				<div><button class="btn md" type="submit">Pay now</button></div>
			</form>
		{/if}

		{#if home.stage === 'verified'}
			<form class="step-card" method="post" action="?/listing" use:enhance={done}>
				<span class="kick">Next step</span>
				<h2>Create a listing</h2>
				<FormError message={form?.form === 'listing' ? form.error : null} />
				<div>
					<label for="title">Title</label>
					<input id="title" type="text" name="title" maxlength="90" minlength="5" required value={form?.form === 'listing' ? form.title : ''} placeholder="Bright 2-bedroom flat near A&C Mall" />
				</div>
				<div>
					<label for="description">Description</label>
					<textarea id="description" name="description" minlength="20" maxlength="5000" required>{form?.form === 'listing' ? form.description : ''}</textarea>
				</div>
				<div class="form-grid">
					<div>
						<label for="rent_ghs">Monthly rent (GH₵)</label>
						<input id="rent_ghs" type="number" name="rent_ghs" min="1" step="1" required value={form?.form === 'listing' ? form.rent_ghs : ''} />
					</div>
					<div>
						<label for="advance_months">Months in advance</label>
						<input id="advance_months" type="number" name="advance_months" min="0" max="24" required value={form?.form === 'listing' ? form.advance_months : '6'} />
					</div>
					<div>
						<label for="min_lease_months">Minimum lease (months)</label>
						<input id="min_lease_months" type="number" name="min_lease_months" min="1" max="60" required value={form?.form === 'listing' ? form.min_lease_months : '12'} />
					</div>
					<div>
						<label for="available_from">Available from</label>
						<input id="available_from" type="date" name="available_from" min={today()} required value={form?.form === 'listing' ? form.available_from : ''} />
					</div>
				</div>
				<p class="note" style="margin: 0">The Rent Act caps advance rent at six months for tenancies over six months. Listings asking for more are checked by a reviewer.</p>
				<div><button class="btn md" type="submit" disabled={busy}>Save as draft</button></div>
			</form>
		{/if}

		{#if home.listings.length}
			<section class="lines" aria-labelledby="list-h">
				<div class="panel-head"><h2 id="list-h">Listings</h2></div>
				{#each home.listings as l (l.id)}
					<a class="line list-row" href="/landlord/listings/{l.id}">
						<span class="l-body"><b>{l.title}</b><span class="mono small muted">{l.reference} · {cedis(l.rent_display)} / month</span></span>
						<span class="pill {listingTone(l.status)}">{l.status === 'pending_review' ? 'Awaiting review' : statusLabel(l.status)}</span>
					</a>
				{/each}
			</section>
		{/if}
	</div>

	<aside class="col">
		<section class="lines" aria-labelledby="docs-h">
			<div class="panel-head"><h2 id="docs-h">Documents</h2></div>
			{#each home.authorities as a (a.id)}
				<div class="line doc-row">
					<span class="tick {a.status === 'rejected' ? 'no' : a.status === 'pending' ? 'none' : ''}">{a.status === 'rejected' ? '✕' : a.status === 'pending' ? '…' : '✓'}</span>
					<span class="l-body"><b>{a.document_label}</b><span class="small muted">{a.relationship_label}{a.review_note ? ` · ${a.review_note}` : ''}</span></span>
					<span class="pill {a.status === 'accepted' ? 'ok' : a.status === 'rejected' ? 'bad' : 'warn'}">{a.status === 'pending' ? 'With Afe' : statusLabel(a.status)}</span>
				</div>
			{:else}
				<div class="line muted small">Upload proof that you can let this home.</div>
			{/each}
		</section>

		{#if home.stage !== 'verified'}
			<form class="box stack" method="post" action="?/document" enctype="multipart/form-data" use:enhance={done}>
				<h3 style="margin: 0">Add a document</h3>
				<FormError message={form?.form === 'document' ? form.error : null} />
				{#if isAgent}
					<div>
						<label for="relationship">You are</label>
						<select id="relationship" name="relationship">
							<option value="authorised_agent">The owner's authorised agent</option>
							<option value="caretaker">The owner's caretaker</option>
						</select>
					</div>
				{:else}
					<input type="hidden" name="relationship" value="owner" />
				{/if}
				<fieldset class="bare">
					<legend class="lbl">Document type</legend>
					<div class="chips">
						{#each docTypes as [k, label]}<label class="chip small-chip"><input type="radio" name="document_type" value={k} bind:group={docType} />{label}</label>{/each}
					</div>
				</fieldset>
				<label class="tile" class:done={docFile}>
					<input type="file" name="document" accept="application/pdf,image/jpeg,image/png" required onchange={(e) => (docFile = e.currentTarget.files?.[0]?.name ?? '')} />
					<b>{docFile ? '✓ Document added' : 'Upload document'}</b>
					<small>{docFile || 'PDF or photo, all pages'}</small>
				</label>
				<div>
					<label for="utility_reference">ECG meter or utility account number</label>
					<input id="utility_reference" type="text" name="utility_reference" maxlength="40" />
				</div>
				<p class="note" style="margin: 0">Stored privately. Only Afe reviewers can open it, and every opening is logged.</p>
				<div><button class="btn md" type="submit" disabled={busy || (js.on && !docFile)}>Upload</button></div>
			</form>
		{/if}
	</aside>
</div>

<style>
	.col {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}
	.sect {
		margin: 0 0 4px;
		font-size: 20px;
	}
	.step-card {
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: 16px;
		padding: 24px;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}
	.step-card h2 {
		margin: 0;
		font-size: 24px;
	}
	.step-card p {
		margin: 0;
		color: var(--muted);
		font-size: 15px;
	}
	.kick {
		font: 12px var(--font-mono);
		color: var(--warn);
	}
	.list-row {
		justify-content: space-between;
		color: var(--ink);
	}
	.list-row:hover {
		background: var(--paper);
		color: var(--ink);
	}
	.doc-row {
		align-items: flex-start;
	}
	.l-body {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.l-body b {
		font-weight: 600;
	}
	.bare {
		border: 0;
		padding: 0;
		margin: 0;
	}
	.lbl {
		font-size: 14px;
		font-weight: 600;
		padding: 0;
		margin-bottom: 8px;
	}
	.small-chip {
		height: 36px;
		font-size: 13.5px;
	}
	.tile {
		position: relative;
		min-height: 120px;
		border-radius: 12px;
		border: 2px dashed var(--line);
		background: repeating-linear-gradient(135deg, var(--paper) 0 10px, var(--surface) 10px 20px);
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 6px;
		font-size: 15px;
		font-weight: 400;
		cursor: pointer;
		padding: 16px;
		margin: 0;
		text-align: center;
	}
	.tile input {
		position: absolute;
		inset: 0;
		opacity: 0;
		cursor: pointer;
	}
	.tile b {
		font-weight: 600;
	}
	.tile small {
		font: 11px var(--font-mono);
		color: var(--muted);
	}
	.tile.done {
		border: 2px solid var(--ok);
		background: var(--ok-soft);
	}
	.tile:has(input:focus-visible) {
		outline: 2px solid var(--amber);
		outline-offset: 2px;
	}
</style>
