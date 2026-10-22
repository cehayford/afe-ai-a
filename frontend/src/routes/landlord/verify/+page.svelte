<script lang="ts">
	// "Get verified" from the Landlord canvas: a four-step list beside one card per step, Back and
	// Continue underneath. Each step is the real thing: the Ghana Card check, ownership documents for a
	// home, the payout account, and the home visit (fee first, where it applies).
	import { tick } from 'svelte';
	import { enhance } from '$app/forms';
	import type { SubmitFunction } from '@sveltejs/kit';
	import FormError from '$lib/components/FormError.svelte';
	import { date } from '$lib/format';
	import { announce } from '$lib/announce.svelte';

	let { data, form } = $props();
	const me = $derived(data.me!);
	const isAgent = $derived(me.user.role === 'agent');
	const check = $derived(data.check);
	const idDone = $derived(check?.status === 'passed' || Boolean(me.verification?.verified));
	const docsDone = $derived(data.homes.some((h) => h.authorities.length > 0));
	const payDone = $derived(Boolean(data.payee));
	const visitDone = $derived(data.homes.some((h) => ['review', 'verified'].includes(h.stage)));
	const done = $derived([idDone, docsDone, payDone, visitDone]);

	const titles: [string, string][] = [
		['Ghana Card', 'Card number and live selfie'],
		['Ownership', 'Indenture or letter of authority'],
		['Payout account', 'Name-matched mobile money'],
		['Home visit', 'Verifier meets you there']
	];
	// svelte-ignore state_referenced_locally
	let step = $state(Math.max(0, [idDone, docsDone, payDone, visitDone].indexOf(false)));
	// Another step replaces the card without a new page: move to its heading, so a screen reader starts there.
	// svelte-ignore state_referenced_locally
	let shown = step;
	$effect(() => {
		if (step === shown) return;
		shown = step;
		tick().then(() => document.querySelector<HTMLElement>('.s-head h2')?.focus());
	});
	const allDone = $derived(done.every(Boolean));

	// Documents go to one home at a time: the first that still needs them.
	// svelte-ignore state_referenced_locally
	let homeId = $state(data.homes.find((h) => h.authorities.length === 0)?.unit.id ?? data.homes[0]?.unit.id);
	const home = $derived(data.homes.find((h) => h.unit.id === homeId));
	let docType = $state('indenture');
	let selfie = $state('');
	let docFile = $state('');
	let errors = $state<Record<number, string>>({});
	let busy = $state(false);

	// Steps 2 and 3 post to the home and payout pages' own actions; the answer is handled here.
	const saved = ['', 'Document uploaded.', 'Payout account saved.'];
	const post =
		(n: number): SubmitFunction =>
		() => {
			busy = true;
			errors = { ...errors, [n]: '' };
			return async ({ result, update }) => {
				busy = false;
				if (result.type === 'failure') errors = { ...errors, [n]: String((result.data as { error?: string })?.error ?? 'Something went wrong.') };
				else {
					await update();
					announce(saved[n]);
				}
			};
		};
	const idSubmit: SubmitFunction = () => {
		busy = true;
		return async ({ result, update }) => {
			await update();
			busy = false;
			// A refused form shows its error in an alert. A finished check comes back to this page (a redirect) and
			// shows its result above; it is read out here.
			if ((result.type === 'success' || result.type === 'redirect') && data.check)
				announce(data.check.status === 'passed' ? 'Ghana Card check passed.' : `Ghana Card check did not pass. ${data.check.failure_reason ?? ''}`.trim());
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
	const stageLine: Record<string, string> = {
		documents: 'Upload ownership documents first',
		fee: 'Pay the verification fee to book the visit',
		visit: 'Waiting for the visit',
		review: 'Visit done. Afe is reviewing',
		verified: 'Verified',
		rejected: 'Not verified: see the reason on the home page'
	};
</script>

<svelte:head><title>Get verified · Afe</title></svelte:head>

<div class="verify">
	<aside class="v-aside">
		<div class="v-head">
			<h1>Get verified</h1>
			<p>About 10 minutes, then one visit from an Afe verifier.{data.free ? ' Free during the launch offer.' : ''}</p>
		</div>
		<ol class="v-steps">
			{#each titles as [title, note], i}
				<li>
					<button type="button" class="v-row" class:cur={step === i} onclick={() => (step = i)} aria-current={step === i ? 'step' : undefined}>
						<span class="dot" class:ok={done[i]} class:now={!done[i] && step === i} aria-hidden="true">{done[i] ? '✓' : i + 1}</span>
						<span class="v-t"><b><span class="sr">Step {i + 1}, {done[i] ? 'done' : 'to do'}: </span>{title}</b><small>{note}</small></span>
					</button>
				</li>
			{/each}
		</ol>
		<a class="back" href="/landlord">← Dashboard</a>
	</aside>

	<section class="v-card">
		{#if step === 0}
			<div class="s-head">
				<span class="kick">Step 1 of 4</span>
				<h2 tabindex="-1">Your Ghana Card</h2>
				<p>We match your card with a live selfie through a licensed identity partner. We store the card number masked and never show it to renters.</p>
			</div>
			{#if check}
				<div style="margin: 0" class="notice {check.status === 'passed' ? 'ok' : 'error'}">
					<b>{check.status === 'passed' ? '✓ Check passed' : 'Check did not pass'}</b>
					<span>{check.masked_card} · {check.name_on_card} · {date(check.created_at)}{check.status === 'failed' ? `. ${check.failure_reason} Try again below.` : me.verification?.verified ? `. You're verified until ${date(me.verification.expires_at)}.` : '. An Afe reviewer confirms it next.'}</span>
				</div>
			{/if}
			{#if check?.status !== 'passed'}
				<form id="id-form" class="s-body" method="post" enctype="multipart/form-data" use:enhance={idSubmit}>
					<FormError message={form?.error} />
					<div class="form-grid">
						<div>
							<label for="card_number">Ghana Card number</label>
							<input id="card_number" class="mono-in" type="text" name="card_number" placeholder="GHA-000000000-0" value={form?.card_number ?? ''} required />
						</div>
						<div>
							<label for="full_name">Full name, exactly as on the card</label>
							<input id="full_name" type="text" name="full_name" value={form?.full_name ?? me.user.display_name} required />
						</div>
					</div>
					<label class="tile" class:done={selfie}>
						<input type="file" name="selfie" accept="image/*" capture="user" required onchange={(e) => (selfie = e.currentTarget.files?.[0]?.name ?? '')} />
						<b>{selfie ? '✓ Selfie added' : 'Take live selfie'}</b>
						<small>{selfie || 'live check, face the camera in good light'}</small>
					</label>
				</form>
			{/if}
		{:else if step === 1}
			<div class="s-head">
				<span class="kick">Step 2 of 4</span>
				<h2 tabindex="-1">Proof you can rent it out</h2>
				<p>Our verifier will see the original at the visit. A clear photo is enough for now.</p>
			</div>
			{#if !data.homes.length}
				<div class="empty">Add the home first: its GhanaPost GPS address, size and type. <div style="margin-top: 12px"><a class="btn md" href="/landlord/homes/new">Add a home</a></div></div>
			{:else}
				{#if data.homes.length > 1}
					<div>
						<label for="home">Home</label>
						<select id="home" bind:value={homeId}>
							{#each data.homes as h (h.unit.id)}<option value={h.unit.id}>{h.unit.digital_address} · {h.unit.unit_label}</option>{/each}
						</select>
					</div>
				{/if}
				{#if home?.authorities.length}
					<div class="lines">
						{#each home.authorities as a (a.id)}
							<div class="line"><span class="tick {a.status === 'rejected' ? 'no' : a.status === 'pending' ? 'none' : ''}">{a.status === 'rejected' ? '✕' : a.status === 'pending' ? '…' : '✓'}</span><span style="flex: 1">{a.document_label}</span><span class="pill {a.status === 'accepted' ? 'ok' : a.status === 'rejected' ? 'bad' : 'warn'}">{a.status === 'pending' ? 'With Afe' : a.status}</span></div>
						{/each}
					</div>
				{/if}
				{#if home && home.stage !== 'verified'}
					<form id="doc-form" class="s-body" method="post" action="/landlord/homes/{home.unit.id}?/document" enctype="multipart/form-data" use:enhance={post(1)}>
						<FormError message={errors[1]} />
						<input type="hidden" name="relationship" value={isAgent ? 'authorised_agent' : 'owner'} />
						<div class="fld">
							<span class="lbl" id="doc-type">Document type</span>
							<div class="chips" role="radiogroup" aria-labelledby="doc-type">
								{#each docTypes as [k, label]}<label class="chip"><input type="radio" name="document_type" value={k} bind:group={docType} />{label}</label>{/each}
							</div>
						</div>
						<label class="tile" class:done={docFile}>
							<input type="file" name="document" accept="application/pdf,image/jpeg,image/png" required onchange={(e) => (docFile = e.currentTarget.files?.[0]?.name ?? '')} />
							<b>{docFile ? '✓ Document added' : 'Upload document'}</b>
							<small>{docFile || 'PDF or photo, all pages'}</small>
						</label>
						<div>
							<label for="utility_reference">ECG meter or utility account number</label>
							<input id="utility_reference" type="text" name="utility_reference" maxlength="40" />
						</div>
						<p class="note" style="margin: 0">Documents are stored privately. Only Afe reviewers can open them, and every opening is logged.</p>
					</form>
				{/if}
			{/if}
		{:else if step === 2}
			<div class="s-head">
				<span class="kick">Step 3 of 4</span>
				<h2 tabindex="-1">Where we send your rent</h2>
				<p>The name on this account must match your Ghana Card.</p>
			</div>
			{#if data.payee}
				<div class="notice ok" style="margin: 0"><b>✓</b><span>Name on account: <b>{data.payee.account_name.toUpperCase()}</b>. Matches your Ghana Card. {data.payee.masked}</span></div>
			{:else}
				<form id="pay-form" class="s-body" method="post" action="/landlord/payouts" use:enhance={post(2)}>
					<FormError message={errors[2]} />
					<div class="form-grid">
						<div>
							<label for="channel">Network</label>
							<select id="channel" name="channel" required>
								<option value="momo_mtn">MTN Mobile Money</option>
								<option value="momo_telecel">Telecel Cash</option>
								<option value="momo_at">AT Money</option>
								<option value="bank">Bank account</option>
							</select>
						</div>
						<div>
							<label for="account_number">Wallet number</label>
							<input id="account_number" name="account_number" inputmode="numeric" autocomplete="off" placeholder="24 555 0142" required />
						</div>
					</div>
					<div>
						<label for="code">Authenticator code</label>
						<input id="code" name="code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" style="max-width: 200px" />
					</div>
				</form>
			{/if}
			<p class="note" style="margin: 0">If you change this account later, payouts pause for 72 hours and we confirm the change with you by phone.</p>
		{:else}
			<div class="s-head">
				<span class="kick">Step 4 of 4</span>
				<h2 tabindex="-1">The home visit</h2>
				<p>A verifier checks the address, meets you there, looks at the original documents and takes the listing photos. Plan for 45 minutes; we call you to agree the time.</p>
			</div>
			{#if data.homes.length}
				<div class="lines">
					{#each data.homes as h (h.unit.id)}
						<div class="line visit-row">
							<div style="flex: 1"><b>{h.unit.digital_address} · {h.unit.unit_label}</b><div class="small muted">{h.visit_scheduled_for ? `Visit on ${date(h.visit_scheduled_for)}` : stageLine[h.stage]}</div></div>
							{#if h.stage === 'fee'}
								<form method="post" action="/landlord/homes/{h.unit.id}?/pay"><button class="btn sm" type="submit">Pay the fee</button></form>
							{:else}
								<a class="btn quiet sm" href="/landlord/homes/{h.unit.id}">Open</a>
							{/if}
						</div>
					{/each}
				</div>
			{:else}
				<div class="empty">Add a home and its documents first. <a href="/landlord/homes/new">Add a home</a></div>
			{/if}
			{#if allDone}
				<div class="notice ok" style="margin: 0"><b>✓ Submitted.</b><span>Your listing goes live once the visit passes review, usually within 2 working days.</span></div>
			{/if}
		{/if}

		<div class="s-nav">
			<button type="button" class="btn ghost md" onclick={() => (step = Math.max(0, step - 1))} disabled={step === 0}>Back</button>
			{#if step === 0 && check?.status !== 'passed'}
				<button class="btn md" type="submit" form="id-form" disabled={busy}>{busy ? 'Checking…' : 'Check my Ghana Card'}</button>
			{:else if step === 1 && home && home.stage !== 'verified' && docFile}
				<button class="btn md" type="submit" form="doc-form" disabled={busy}>{busy ? 'Uploading…' : 'Upload and continue'}</button>
			{:else if step === 2 && !data.payee}
				<button class="btn md" type="submit" form="pay-form" disabled={busy}>Save payout account</button>
			{:else if step < 3}
				<button type="button" class="btn md" onclick={() => (step += 1)}>Continue</button>
			{:else}
				<a class="btn md" href="/landlord">Go to dashboard</a>
			{/if}
		</div>
	</section>
</div>

<style>
	.verify {
		max-width: 1080px;
		margin: 0 auto;
		padding-top: 8px;
		display: flex;
		flex-wrap: wrap;
		gap: 32px;
		align-items: flex-start;
	}
	.v-aside {
		flex: 1 1 260px;
		display: flex;
		flex-direction: column;
		gap: 16px;
	}
	.v-head {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	.v-head h1 {
		margin: 0;
		font-size: 30px;
		line-height: 1.1;
	}
	.v-head p {
		margin: 0;
		font-size: 14.5px;
		color: var(--muted);
	}
	.v-steps {
		list-style: none;
		margin: 0;
		padding: 0;
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: 12px;
		overflow: hidden;
	}
	.v-steps li + li {
		border-top: 1px solid var(--hair);
	}
	.v-row {
		width: 100%;
		display: flex;
		gap: 12px;
		align-items: center;
		padding: 14px 16px;
		border: 0;
		background: transparent;
		text-align: left;
		font-family: var(--font-sans);
		color: var(--ink);
		cursor: pointer;
	}
	.v-row.cur {
		background: var(--paper);
	}
	.dot {
		width: 28px;
		height: 28px;
		flex: 0 0 auto;
		border-radius: 99px;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 13px;
		font-weight: 700;
		background: var(--tint);
		color: var(--muted);
	}
	.dot.now {
		background: var(--brand);
		color: #fff;
	}
	.dot.ok {
		background: var(--ok);
		color: var(--on-ok);
	}
	.v-t {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.v-t b {
		font-weight: 600;
		font-size: 15px;
	}
	.v-t small {
		font-size: 13px;
		color: var(--muted);
	}
	.v-card {
		flex: 999 1 520px;
		min-width: 0;
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: 16px;
		padding: 28px;
		display: flex;
		flex-direction: column;
		gap: 22px;
	}
	.s-head {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	.kick {
		font: 12px var(--font-mono);
		color: var(--warn);
	}
	.s-head h2 {
		margin: 0;
		font-size: 26px;
	}
	.s-head h2:focus {
		outline: none; /* focused only to move the screen reader; it isn't a control */
	}
	.s-head p {
		margin: 0;
		font-size: 15px;
		color: var(--muted);
	}
	.s-body {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}
	.mono-in {
		font-family: var(--font-mono);
	}
	.lbl {
		display: block;
		font-size: 14px;
		font-weight: 600;
		margin-bottom: 8px;
	}
	.tile {
		position: relative;
		min-height: 140px;
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
	.visit-row {
		flex-wrap: wrap;
	}
	.s-nav {
		display: flex;
		justify-content: space-between;
		gap: 12px;
		border-top: 1px solid var(--hair);
		padding-top: 20px;
	}
	.s-nav .btn.ghost:disabled {
		background: transparent;
		visibility: hidden;
	}
</style>
