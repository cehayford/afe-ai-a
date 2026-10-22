<script lang="ts">
	// Label checks as review cases: the decision being checked (outcome, source, reasons) and an
	// agree / disagree footer.
	import { enhance } from '$app/forms';
	import FormError from '$lib/components/FormError.svelte';
	import { ago, dateTime } from '$lib/format';
	import Done from '$lib/components/Done.svelte';

	let { data, form } = $props();
	let busy = $state(false);
	const submit = () => {
		busy = true;
		return async ({ update }: { update: () => Promise<void> }) => {
			await update();
			busy = false;
		};
	};
</script>

<svelte:head><title>Label checks · Afe review</title></svelte:head>

<nav class="pills" aria-label="Models">
	<a href="/review/detection">Models</a><a href="/review/label-checks" aria-current="page">Label checks</a><a href="/review/insights">Targets</a>
</nav>
<div class="page-head">
	<div class="row spread"><h1>Label checks</h1><span class="muted small">{data.checks.length} waiting</span></div>
	<p>5% of decisions get a second look from another reviewer. If you'd have decided differently, the label is left out of model training until a senior reviewer settles it.</p>
</div>
<FormError message={form?.error} />
<Done message={form?.done ? 'Saved.' : null} key={form} />

<div class="case-list page-1000" style="margin: 0">
	{#each data.checks as c (c.id)}
		<div class="case">
			<div class="case-head">
				<span class="row"><span class="ktag quiet">Label</span><b>{c.subject}</b></span>
				<span class="mono" title={dateTime(c.decided_at)}>{c.source} · {ago(c.decided_at)}</span>
			</div>
			<div class="case-body">
				<span class="row">Decided <span class="pill {c.outcome === 'fraud' ? 'bad' : 'ok'}">{c.outcome}</span></span>
				{#if c.reasons.length}<span class="mono small">{c.reasons.join(', ')}</span>{/if}
			</div>
			<form class="case-foot" method="post" use:enhance={submit}>
				<input type="hidden" name="id" value={c.id} />
				<input name="note" placeholder="Note (optional)" maxlength="300" aria-label="Note" />
				<div class="row">
					<button class="btn go md" type="submit" name="agree" value="true" disabled={busy}>I agree</button>
					<button class="btn secondary md" type="submit" name="agree" value="false" disabled={busy}>I'd decide differently</button>
				</div>
			</form>
		</div>
	{:else}
		<div class="empty">Nothing to check. Decisions you made yourself are never shown to you here.</div>
	{/each}
</div>
