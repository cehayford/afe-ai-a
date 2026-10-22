<script lang="ts">
	// Appeals as review cases: which decision, the person's reason, and the outcome they will read.
	import { enhance } from '$app/forms';
	import FormError from '$lib/components/FormError.svelte';
	import { ago, dateTime } from '$lib/format';
	import Done from '$lib/components/Done.svelte';

	let { data, form } = $props();
	const KIND: Record<string, string> = { verification: 'Verification decision', listing: 'Paused listing', report: 'Upheld scam report' };
	const TONE: Record<string, string> = { verification: '', listing: 'warn', report: 'flag' };
	let busy = $state(false);
	const submit = () => {
		busy = true;
		return async ({ update }: { update: () => Promise<void> }) => {
			await update();
			busy = false;
		};
	};
</script>

<svelte:head><title>Appeals · Afe review</title></svelte:head>

<a class="back" href="/review">← Review queue</a>
<div class="page-head">
	<div class="row spread"><h1>Appeals</h1><span class="muted small">{data.appeals.length} waiting</span></div>
	<p>Each decision can be appealed once. A reviewer who didn't make the decision decides the appeal.</p>
</div>
<FormError message={form?.error} />
<Done message={form?.done ? 'Decision sent to the person.' : null} key={form} />

<div class="case-list page-1000" style="margin: 0">
	{#each data.appeals as a (a.id)}
		<div class="case">
			<div class="case-head">
				<span class="row"><span class="ktag {TONE[a.kind] ?? ''}">Appeal</span><b>{KIND[a.kind]}</b><span class="mono">#{a.subject_id}</span></span>
				<span class="mono" title={dateTime(a.created_at)}>{ago(a.created_at)}</span>
			</div>
			<div class="case-body">
				<span class="label-mono">{a.appellant_name} says</span>
				<p style="white-space: pre-line">{a.reason}</p>
			</div>
			<form class="case-foot" method="post" use:enhance={submit}>
				<input type="hidden" name="id" value={a.id} />
				<label for="outcome-{a.id}" style="margin: 0">Outcome the person will read</label>
				<textarea id="outcome-{a.id}" name="outcome" required minlength="20" maxlength="500"></textarea>
				<div class="row">
					<button class="btn go md" type="submit" name="upheld" value="true" disabled={busy}>Uphold the appeal</button>
					<button class="btn secondary md" type="submit" name="upheld" value="false" disabled={busy}>Don't uphold</button>
				</div>
				<span class="note">The person is told the outcome by SMS and on their appeals page. Every decision is saved to the audit log with your name.</span>
			</form>
		</div>
	{:else}
		<div class="empty">No appeals waiting.</div>
	{/each}
</div>
