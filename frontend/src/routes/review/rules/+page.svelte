<script lang="ts">
	// Rules as a table (the canvas's listings table): one row per setting with its value and version,
	// proposals waiting for a second reviewer under it, and a Change row that opens in place.
	import { enhance } from '$app/forms';
	import FormError from '$lib/components/FormError.svelte';
	import { dateTime } from '$lib/format';
	import Done from '$lib/components/Done.svelte';

	let { data, form } = $props();
	const show = (v: unknown) => (typeof v === 'boolean' ? (v ? 'Yes' : 'No') : String(v));
	const waiting = $derived(data.rules.reduce((n, r) => n + r.pending.length, 0));
	let editing = $state<string | null>(null);
	let busy = $state(false);
	const submit = () => {
		busy = true;
		return async ({ update, result }: { update: () => Promise<void>; result: { type: string } }) => {
			await update();
			busy = false;
			if (result.type === 'success') editing = null;
		};
	};
</script>

<svelte:head><title>Rules · Afe review</title></svelte:head>

<div class="page-head">
	<div class="row spread"><h1>Rules</h1>{#if waiting}<span class="pill warn">{waiting} waiting for a second reviewer</span>{/if}</div>
	<p>Money and legal limits, kept as settings rather than code. Every change needs two reviewers, and each tenancy records the versions it was made under.</p>
</div>
<FormError message={form?.error} />
<Done message={form?.done} key={form} />

<div class="scroll">
	<table class="q wide-t">
		<thead><tr><th>Rule</th><th>Value</th><th>Source</th><th><span class="sr">Actions</span></th></tr></thead>
		<tbody>
			{#each data.rules as r (r.key)}
				<tr>
					<td><b>{r.label}</b><br /><span class="mono">{r.key}</span></td>
					<td class="val"><b>{show(r.value)}</b> <small>v{r.version}</small></td>
					<td class="src">{r.source}</td>
					<td class="act">
						<button class="btn quiet sm" type="button" aria-expanded={editing === r.key} onclick={() => (editing = editing === r.key ? null : r.key)}>
							{editing === r.key ? 'Cancel' : 'Change'}
						</button>
					</td>
				</tr>
				{#each r.pending as p (p.id)}
					<tr class="sub">
						<td colspan="4">
							<div class="prop">
								<span class="ktag warn">Proposed</span>
								<span class="p-body"><b>{show(p.value)}</b> by {p.proposed_by_name}, {dateTime(p.proposed_at)}<br /><span class="small muted">{p.source}</span></span>
								<span class="row">
									<form method="post" action="?/reject" use:enhance={submit}><input type="hidden" name="id" value={p.id} /><button class="btn secondary sm" type="submit" disabled={busy}>Reject</button></form>
									<form method="post" action="?/approve" use:enhance={submit}><input type="hidden" name="id" value={p.id} /><button class="btn go sm" type="submit" disabled={busy}>Approve</button></form>
								</span>
							</div>
						</td>
					</tr>
				{/each}
				{#if editing === r.key}
					<tr class="sub">
						<td colspan="4">
							<form class="edit" method="post" action="?/propose" use:enhance={submit}>
								<input type="hidden" name="key" value={r.key} />
								<div class="e-val"><label for="val-{r.key}">New value</label><input id="val-{r.key}" name="value" required placeholder="Now {String(r.value)}" /></div>
								<div class="e-src"><label for="src-{r.key}">Law, decision or reason</label><input id="src-{r.key}" name="source" required minlength="5" /></div>
								<button class="btn md" type="submit" disabled={busy}>Propose</button>
							</form>
							{#if r.version > 0}
								<form class="rb" method="post" action="?/rollback" use:enhance={submit}>
									<input type="hidden" name="key" value={r.key} />
									<button class="btn quiet sm" type="submit" disabled={busy}>Propose going back to the previous version</button>
								</form>
							{/if}
						</td>
					</tr>
				{/if}
			{/each}
		</tbody>
	</table>
</div>

<style>
	.wide-t {
		min-width: 640px;
	}
	.val {
		white-space: nowrap;
		font-variant-numeric: tabular-nums;
	}
	.src {
		color: var(--muted);
		font-size: 14px;
		max-width: 320px;
	}
	.act {
		text-align: right;
		width: 1%;
	}
	.sub td {
		border-top: 0;
		padding-top: 0;
	}
	.prop {
		display: flex;
		gap: 12px;
		align-items: center;
		flex-wrap: wrap;
		background: var(--warn-soft);
		border-radius: 8px;
		padding: 10px 12px;
	}
	.p-body {
		flex: 1 1 240px;
		font-size: 14px;
	}
	.edit {
		display: flex;
		gap: 12px;
		align-items: flex-end;
		flex-wrap: wrap;
		background: var(--paper);
		border-radius: 8px;
		padding: 12px;
	}
	.e-val {
		flex: 0 1 180px;
	}
	.e-src {
		flex: 1 1 260px;
	}
	.rb {
		margin-top: 6px;
	}
</style>
