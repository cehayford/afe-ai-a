<script lang="ts">
	// One tenancy kept on Afe, for the landlord and the tenant: the terms as a fact strip, then
	// underline tabs for payments, repairs, agreements and renewals (each with its own form), and
	// beside them what the landlord does most (record a payment).
	import { enhance } from '$app/forms';
	import { page } from '$app/state';
	import FormError from '$lib/components/FormError.svelte';
	import { cedis, date, dateTime, day, ghs, initials } from '$lib/format';
	import Done from '$lib/components/Done.svelte';

	let { data, form } = $props();
	const d = $derived(data.d);
	const r = $derived(d.rental);
	const landlord = $derived(d.role === 'landlord');
	const me = $derived(data.me!.user.name);
	const STATUS: Record<string, string> = { open: 'Open', in_progress: 'In progress', done: 'Done' };
	const METHOD: Record<string, string> = { afe: 'Through Afe', momo: 'Mobile money', bank: 'Bank', cash: 'Cash' };
	const today = new Date().toISOString().slice(0, 10);
	const overdue = $derived(r.status === 'active' && r.next_due_date < today);
	const money = (p: number) => cedis(ghs(p));

	type Tab = 'payments' | 'repairs' | 'agreements' | 'renewals';
	// The tab lives in the URL (?tab=repairs), so it works without JavaScript, survives a form post
	// and can be linked to.
	const TABS: Tab[] = ['payments', 'repairs', 'agreements', 'renewals'];
	const tab = $derived<Tab>(TABS.find((k) => k === page.url.searchParams.get('tab')) ?? 'payments');
	const openRepairs = $derived(d.maintenance.filter((m) => m.status !== 'done').length);
	const toSign = $derived(d.agreements.filter((a) => (landlord ? !a.landlord_signed_at : !a.tenant_signed_at)).length);
	const tabs = $derived<[Tab, string, number][]>([
		['payments', 'Payments', 0],
		['repairs', 'Repairs', openRepairs],
		['agreements', 'Agreements', toSign],
		['renewals', 'Renewals', d.renewals.filter((x) => x.status === 'offered').length]
	]);

	let busy = $state(false);
	let photo = $state('');
	const submit = () => {
		busy = true;
		return async ({ update, result }: { update: () => Promise<void>; result: { type: string } }) => {
			await update();
			busy = false;
			if (result.type === 'success') photo = '';
		};
	};
</script>

<svelte:head><title>{landlord ? r.tenant_name : 'My home'} · Afe</title></svelte:head>

<a class="back" href={landlord ? '/landlord/rentals' : '/account/home'}>← {landlord ? 'Tenants and rent' : 'My home'}</a>

<div class="who">
	<span class="avatar lg">{initials(landlord ? r.tenant_name : r.landlord_name)}</span>
	<div class="who-t">
		<h1>{landlord ? r.tenant_name : r.home || `Home let by ${r.landlord_name}`}</h1>
		<span class="muted">{landlord ? r.home || 'Home not on Afe' : `Landlord ${r.landlord_name}`}</span>
	</div>
	{#if r.status === 'active'}
		<span class="pill {overdue ? 'bad' : 'ok'}">{overdue ? 'Rent overdue' : 'Active'}</span>
	{:else}
		<span class="pill quiet">Ended</span>
	{/if}
</div>

<dl class="facts">
	<div><dt>Rent / month</dt><dd>{money(r.rent_pesewas)}</dd></div>
	<div><dt>Paid</dt><dd>{r.pay_every_months === 1 ? 'Monthly' : `Every ${r.pay_every_months} months`}</dd></div>
	<div><dt>Lease</dt><dd>{date(r.start_date)} – {date(r.end_date)}</dd></div>
	<div><dt>Next due</dt><dd style={overdue ? 'color: var(--crit)' : ''}>{r.status === 'active' ? day(r.next_due_date) : '—'}</dd></div>
</dl>
{#if r.status === 'active'}
	<div class="row">
		<a class="btn secondary sm" href="/rentals/{r.id}/invoice" target="_blank" rel="noopener">Rent invoice for {day(r.next_due_date)} (PDF)</a>
		<span class="small muted">{landlord ? 'Send it to your tenant, or print it.' : 'What you owe next, from your landlord.'}</span>
	</div>
{/if}

{#if landlord && !r.tenant_on_afe}
	<div class="notice"><b>Only you see this.</b><span>The tenant isn't on Afe with this number. When they sign up with it, they see receipts and can ask for repairs.</span></div>
{/if}
{#if form?.error}<FormError message={form.error} />{/if}
<Done message={form?.done} key={form} />

<div class="detail">
	<div class="col">
		<nav class="tabs" aria-label="This tenancy" style="margin: 0">
			{#each tabs as [k, label, n] (k)}
				<a href="?tab={k}" aria-current={tab === k ? 'page' : undefined} data-sveltekit-noscroll data-sveltekit-replacestate>
					{label}{#if n}<span class="tabn">{n}</span>{/if}
				</a>
			{/each}
		</nav>

		<section class="col" aria-label={tabs.find(([k]) => k === tab)?.[1]}>
			{#if tab === 'payments'}
				{#if d.payments.length}
					<div class="lines">
						{#each d.payments as p (p.id)}
							<div class="line">
								<span class="l-body">
									<b class="amt">{money(p.amount_pesewas)}</b>
									<span class="small muted">{date(p.paid_on)} · {METHOD[p.method] ?? p.method} · covers {p.covers_months} month{p.covers_months === 1 ? '' : 's'}{p.note ? ` · ${p.note}` : ''}</span>
								</span>
								<a class="btn quiet sm" href="/rentals/{r.id}/receipt/{p.id}" target="_blank" rel="noopener">Receipt <span class="mono">{p.receipt_no}</span></a>
							</div>
						{/each}
					</div>
				{:else}
					<div class="empty">No payments recorded yet.{landlord ? ' Record one and Afe makes the receipt.' : ''}</div>
				{/if}
			{:else if tab === 'repairs'}
				{#each d.maintenance as m (m.id)}
					<div class="item">
						<div class="row spread"><b>{m.title}</b><span class="pill {m.status === 'done' ? 'ok' : m.status === 'in_progress' ? '' : 'warn'}">{STATUS[m.status]}</span></div>
						<p class="small" style="margin: 0; white-space: pre-line">{m.details}</p>
						<span class="mono small muted">{dateTime(m.created_at)}</span>
						{#if m.landlord_note}<div class="reply"><span class="label-mono">Landlord</span>{m.landlord_note}</div>{/if}
						{#if m.has_photo}<a class="small" href="/rentals/{r.id}/repair-photo/{m.id}" target="_blank" rel="noopener">See the photo</a>{/if}
						{#if landlord && m.status !== 'done'}
							<form class="upd" method="post" action="?tab=repairs&/repairStatus" use:enhance={submit}>
								<input type="hidden" name="id" value={m.id} />
								<input name="note" placeholder="Note for the tenant" aria-label="Note for the tenant" maxlength="500" />
								{#if m.status === 'open'}<button class="btn secondary sm" name="status" value="in_progress" type="submit" disabled={busy}>In progress</button>{/if}
								<button class="btn sm" name="status" value="done" type="submit" disabled={busy}>Mark done</button>
							</form>
						{/if}
					</div>
				{:else}
					<div class="empty">No repair requests.</div>
				{/each}

				<form class="box stack" method="post" action="?tab=repairs&/repair" enctype="multipart/form-data" use:enhance={submit}>
					<h3 style="margin: 0">{landlord ? 'Log a repair' : 'Ask for a repair'}</h3>
					<div><label for="title">What needs fixing</label><input id="title" name="title" required minlength="3" maxlength="120" placeholder="Kitchen tap leaking" /></div>
					<div><label for="details">Where and what's wrong</label><textarea id="details" name="details" required minlength="10" maxlength="4000"></textarea></div>
					<label class="tile" class:done={photo}>
						<input name="photo" type="file" accept="image/*" onchange={(e) => (photo = e.currentTarget.files?.[0]?.name ?? '')} />
						<b>{photo ? '✓ Photo added' : 'Add a photo'}</b>
						<small>{photo || 'optional'}</small>
					</label>
					<div><button class="btn md" type="submit" disabled={busy}>Send</button></div>
				</form>
			{:else if tab === 'agreements'}
				{#each d.agreements as a (a.id)}
					<div class="item">
						<div class="agree-body">{a.body}</div>
						<div class="sigs">
							<span class="sig"><span class="tick {a.landlord_signed_at ? '' : 'none'}">{a.landlord_signed_at ? '✓' : '·'}</span><span><b>Landlord</b><br /><span class="small muted">{a.landlord_signed_at ? `${a.landlord_signed_name}, ${dateTime(a.landlord_signed_at)}` : 'Not signed yet'}</span></span></span>
							<span class="sig"><span class="tick {a.tenant_signed_at ? '' : 'none'}">{a.tenant_signed_at ? '✓' : '·'}</span><span><b>Tenant</b><br /><span class="small muted">{a.tenant_signed_at ? `${a.tenant_signed_name}, ${dateTime(a.tenant_signed_at)}` : 'Not signed yet'}</span></span></span>
						</div>
						<div class="row">
							<a class="btn quiet sm" href="/rentals/{r.id}/agreement/{a.id}" target="_blank" rel="noopener">Download PDF</a>
							<span class="mono small muted" title="Fingerprint of the signed text">#{a.body_hash.slice(0, 12)}</span>
						</div>
						{#if (landlord && !a.landlord_signed_at) || (!landlord && !a.tenant_signed_at)}
							<form class="upd" method="post" action="?tab=agreements&/sign" use:enhance={submit}>
								<input type="hidden" name="id" value={a.id} />
								<label class="sr" for="typed-{a.id}">Type your full name to sign</label>
								<input id="typed-{a.id}" name="typed_name" required placeholder="Type your full name: {me}" />
								<button class="btn sm" type="submit" disabled={busy}>Sign</button>
							</form>
						{/if}
					</div>
				{:else}
					<div class="empty">No agreement yet.{landlord && r.tenant_on_afe ? ' Prepare one from these terms and you both sign it here.' : ''}</div>
				{/each}
				{#if landlord && r.status === 'active' && r.tenant_on_afe}
					<form method="post" action="?tab=agreements&/agreement" use:enhance={submit}>
						<button class="btn secondary md" type="submit" disabled={busy}>Prepare an agreement from these terms</button>
					</form>
				{/if}
			{:else}
				{#if d.renewals.length}
					<div class="lines">
						{#each d.renewals as rn (rn.id)}
							<div class="line">
								<span class="l-body"><b>Until {date(rn.new_end_date)}</b><span class="small muted">{money(rn.new_rent_pesewas)} / month · {rn.advance_months} months in advance</span></span>
								{#if rn.status === 'offered' && !landlord}
									<form class="row" method="post" action="?tab=renewals&/decideRenewal" use:enhance={submit}>
										<input type="hidden" name="id" value={rn.id} />
										<button class="btn secondary sm" name="answer" value="decline" type="submit" disabled={busy}>Decline</button>
										<button class="btn sm" name="answer" value="accept" type="submit" disabled={busy}>Accept</button>
									</form>
								{:else}
									<span class="pill {rn.status === 'accepted' ? 'ok' : rn.status === 'declined' ? 'quiet' : 'warn'}">{rn.status === 'offered' ? 'Waiting for tenant' : rn.status === 'accepted' ? 'Accepted' : 'Declined'}</span>
								{/if}
							</div>
						{/each}
					</div>
				{:else}
					<div class="empty">No renewal offers.</div>
				{/if}
				{#if landlord && r.status === 'active'}
					<form class="box stack" method="post" action="?tab=renewals&/renew" use:enhance={submit}>
						<h3 style="margin: 0">Offer a renewal</h3>
						<div class="form-grid">
							<div><label for="new_end_date">New end date</label><input id="new_end_date" name="new_end_date" type="date" required min={r.end_date} /></div>
							<div><label for="new_rent_ghs">Rent a month (GH₵)</label><input id="new_rent_ghs" name="new_rent_ghs" type="number" min="1" required value={r.rent_pesewas / 100} /></div>
							<div><label for="advance_months">Months in advance</label><input id="advance_months" name="advance_months" type="number" min="0" max="6" required value="6" /></div>
						</div>
						<p class="note" style="margin: 0">The law caps advance rent at 6 months for a renewal over 6 months.</p>
						<div><button class="btn md" type="submit" disabled={busy}>Send renewal offer</button></div>
					</form>
				{/if}
			{/if}
		</section>
	</div>

	<aside class="col">
		{#if landlord && r.status === 'active'}
			<form class="box stack" method="post" action="?/pay" use:enhance={submit}>
				<div class="row spread"><h2 class="bx">Record a payment</h2><span class="label-mono">Makes a receipt</span></div>
				<div class="form-grid">
					<div><label for="amount_ghs">Amount (GH₵)</label><input id="amount_ghs" name="amount_ghs" type="number" step="0.01" min="1" required value={(r.rent_pesewas * r.pay_every_months) / 100} /></div>
					<div><label for="covers_months">Months it covers</label><input id="covers_months" name="covers_months" type="number" min="1" max="24" required value={r.pay_every_months} /></div>
					<div><label for="paid_on">Paid on</label><input id="paid_on" name="paid_on" type="date" max={today} required value={today} /></div>
					<div>
						<label for="method">How</label>
						<select id="method" name="method"><option value="momo">Mobile money</option><option value="bank">Bank</option><option value="cash">Cash</option></select>
					</div>
				</div>
				<div><label for="pay-note">Note <span class="muted" style="font-weight: 400">(optional)</span></label><input id="pay-note" name="note" maxlength="300" /></div>
				<button class="btn md block" type="submit" disabled={busy}>Record and make receipt</button>
			</form>
		{:else if !landlord}
			<div class="box stack">
				<h2 class="bx">Your landlord</h2>
				<p class="small" style="margin: 0">{r.landlord_name} records your payments here, and Afe makes a receipt for each one. Ask for repairs from the <a href="?tab=repairs">Repairs</a> tab.</p>
			</div>
		{/if}
		{#if !landlord || r.status !== 'active'}
			<p class="note" style="margin: 0">Afe never asks you to pay rent to a new number. If anyone does, <a href="/check" data-section="report">report it</a>.</p>
		{/if}
		{#if landlord && r.status === 'active'}
			<form method="post" action="?/end" use:enhance={submit}>
				<button class="btn danger-line sm" type="submit" disabled={busy}>Mark tenancy ended</button>
			</form>
		{/if}
	</aside>
</div>

<style>
	.who {
		display: flex;
		gap: 14px;
		align-items: center;
		flex-wrap: wrap;
	}
	.who-t {
		flex: 1 1 200px;
		display: flex;
		flex-direction: column;
		gap: 2px;
		min-width: 0;
	}
	.who-t h1 {
		margin: 0;
		font-size: 30px;
		line-height: 1.1;
	}
	.col {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}
	.tabn {
		margin-left: 6px;
		min-width: 20px;
		height: 20px;
		padding: 0 6px;
		border-radius: 99px;
		background: var(--amber);
		color: var(--on-amber);
		font: 600 12px var(--font-sans);
		display: inline-flex;
		align-items: center;
		justify-content: center;
	}
	.l-body {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.amt {
		font-variant-numeric: tabular-nums;
	}
	.item {
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: 12px;
		padding: 16px 18px;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.reply {
		background: var(--paper);
		border-radius: 8px;
		padding: 10px 12px;
		font-size: 14px;
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.upd {
		display: flex;
		gap: 8px;
		flex-wrap: wrap;
		align-items: center;
	}
	.upd input:not([type='hidden']) {
		flex: 1 1 200px;
		height: 40px;
	}
	.agree-body {
		max-height: 260px;
		overflow: auto;
		background: var(--paper);
		border: 1px solid var(--hair);
		border-radius: 8px;
		padding: 14px;
		font-size: 14px;
		line-height: 1.55;
		white-space: pre-line;
	}
	.sigs {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
		gap: 10px;
	}
	.sig {
		display: flex;
		gap: 10px;
		align-items: flex-start;
		font-size: 14.5px;
	}
	.bx {
		margin: 0;
		font-size: 20px;
	}
	.tile {
		position: relative;
		min-height: 96px;
		border-radius: 12px;
		border: 2px dashed var(--line);
		background: repeating-linear-gradient(135deg, var(--paper) 0 10px, var(--surface) 10px 20px);
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 4px;
		font-size: 15px;
		font-weight: 400;
		cursor: pointer;
		padding: 14px;
		margin: 0;
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
