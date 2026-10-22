<script lang="ts">
	// Money desk in the Admin Review canvas's idiom: the totals, then releases and disputes as case
	// cards (kind tag, what happened, a decision footer), with money by status and reconciliation beside.
	import { enhance } from '$app/forms';
	import FormError from '$lib/components/FormError.svelte';
	import { ago, cedis, dateTime, day, ghs, TENANCY_LABELS, tenancyTone } from '$lib/format';
	import Done from '$lib/components/Done.svelte';

	let { data, form } = $props();
	const releases = $derived(data.queue.filter((t) => t.status === 'release_pending'));
	const statuses = $derived(Object.entries(data.finance.by_status).sort((a, b) => b[1].count - a[1].count));
	const money = (p: number | null) => (p === null ? '—' : cedis(ghs(p)));
	let busy = $state(false);
	const submit = () => {
		busy = true;
		return async ({ update }: { update: () => Promise<void> }) => {
			await update();
			busy = false;
		};
	};
</script>

<svelte:head><title>Money · Afe review</title></svelte:head>

<div class="page-head">
	<h1>Money</h1>
	<p>Releases waiting for approval, open disputes, and reconciliation with the payment partner.</p>
</div>
<FormError message={form?.error} />
<Done message={form?.done} key={form} />

<div class="stats-row">
	<div class="stat"><b>{money(data.finance.held_now_pesewas)}</b><span>Held by the partner now</span></div>
	<div class="stat"><b>{money(data.finance.fees_earned_pesewas)}</b><span>Fees earned</span></div>
	<div class="stat"><b>{releases.length}</b><span>Releases to approve</span></div>
	<div class="stat"><b>{data.disputes.length}</b><span>Open disputes</span></div>
</div>

<div class="detail">
	<div class="case-list">
		<h2 class="sect">Releases to approve</h2>
		{#each releases as t (t.reference)}
			<div class="case">
				<div class="case-head">
					<span class="row"><span class="ktag ok">Release</span><a class="mono" href="/tenancies/{t.reference}">{t.reference}</a></span>
					<b class="amt">{cedis(t.payout_display)}</b>
				</div>
				<div class="case-body">
					<b>{t.listing_title}</b>
					<span class="muted">{t.landlord_name} → {t.tenant_name} · move in {day(t.move_in_date)}</span>
					<span class="small">{t.close_reason}{t.tenant_confirmed_at ? ` · tenant confirmed ${dateTime(t.tenant_confirmed_at)}` : ''}</span>
					<span class="small muted">Pays to {t.payee}</span>
				</div>
				<form class="case-foot" method="post" action="?/release" use:enhance={submit}>
					<input type="hidden" name="reference" value={t.reference} />
					<label class="sr" for="rel-{t.reference}">Release note for {t.reference}</label>
					<input id="rel-{t.reference}" name="note" required minlength="10" placeholder="Why this is safe to release" />
					<div><button class="btn go md" type="submit" disabled={busy}>Release {cedis(t.payout_display)}</button></div>
				</form>
			</div>
		{:else}
			<div class="empty">Nothing to release.</div>
		{/each}

		<h2 class="sect">Open disputes</h2>
		{#each data.disputes as d (d.id)}
			<div class="case">
				<div class="case-head">
					<span class="row"><span class="ktag warn">Dispute</span><a class="mono" href="/tenancies/{d.tenancy_reference}">{d.tenancy_reference}</a></span>
					<span class="mono">{ago(d.created_at)}</span>
				</div>
				<div class="case-body">
					<b>{d.reason_label}</b>
					<p style="white-space: pre-line">{d.details}</p>
					<span class="small muted">Opened by {d.opened_by_name} · {dateTime(d.created_at)}</span>
				</div>
				<form class="case-foot" method="post" action="?/decide" use:enhance={submit}>
					<input type="hidden" name="id" value={d.id} />
					<label for="note-{d.id}" style="margin: 0">Decision note <span class="muted" style="font-weight: 400">(both sides see it)</span></label>
					<textarea id="note-{d.id}" name="note" required minlength="10" maxlength="500"></textarea>
					<div class="row">
						<button class="btn go md" type="submit" name="decision" value="release" disabled={busy}>Pay the landlord</button>
						<button class="btn secondary md" type="submit" name="decision" value="refund" disabled={busy}>Refund the tenant</button>
					</div>
					<span class="note">Every decision is saved to the audit log with your name.</span>
				</form>
			</div>
		{:else}
			<div class="empty">No open disputes.</div>
		{/each}
	</div>

	<aside class="case-list">
		<section class="case" aria-labelledby="st-h">
			<div class="case-head"><b id="st-h">By status</b></div>
			{#each statuses as [status, row] (status)}
				<div class="st-row">
					<span class="pill {tenancyTone(status)}">{TENANCY_LABELS[status] ?? status}</span>
					<span class="amt small">{row.count} · {money(row.held_pesewas)}</span>
				</div>
			{:else}
				<div class="case-body muted">No tenancies yet.</div>
			{/each}
		</section>
		<section class="case" aria-labelledby="rec-h">
			<div class="case-head"><b id="rec-h">Reconciliation</b>{#if !data.mismatches.length}<span class="pill ok">Matches</span>{/if}</div>
			{#each data.mismatches as m, i (i)}
				<div class="case-body mis">
					<span class="row"><span class="sevtag high">{m.kind}</span><span class="mono small">{m.tenancy}</span></span>
					<span>{m.problem}</span>
					<span class="small muted">Ours {money(m.ours)} · theirs {money(m.theirs)}</span>
				</div>
			{:else}
				<div class="case-body small muted">Afe's ledger and the partner's statement agree.</div>
			{/each}
		</section>
	</aside>
</div>

<style>
	.sect {
		margin: 8px 0 0;
		font-size: 20px;
	}
	.sect:first-child {
		margin-top: 0;
	}
	.amt {
		font-variant-numeric: tabular-nums;
		white-space: nowrap;
	}
	.st-row {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 8px;
		padding: 10px 16px;
		border-bottom: 1px solid var(--hair);
	}
	.st-row:last-child {
		border-bottom: 0;
	}
	.mis + .mis {
		border-top: 1px solid var(--hair);
	}
</style>
