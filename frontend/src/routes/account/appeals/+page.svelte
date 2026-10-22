<script lang="ts">
	// Appeals: ask a different reviewer to look again at a decision about you.
	import { enhance } from '$app/forms';
	import FormError from '$lib/components/FormError.svelte';
	import { date } from '$lib/format';

	let { data, form } = $props();
	const STATUS: Record<string, [string, string]> = { open: ['Waiting', 'warn'], upheld: ['Upheld', 'ok'], rejected: ['Not upheld', 'quiet'] };
</script>

<svelte:head><title>Appeals · Afe</title></svelte:head>

<h2 class="sr">Appeals</h2>
<p class="muted" style="margin: 0; font-size: 15px; max-width: 44em">
	If you think Afe got a decision about you wrong, you can appeal it once. A different reviewer looks at it and writes to
	you with the outcome.
</p>
<FormError message={form?.error} />
{#if form?.sent}<p class="result">Appeal sent. We'll tell you the outcome by SMS.</p>{/if}

{#if data.appealable.length}
	<form class="box stack" method="post" use:enhance style="max-width: 640px">
		<div>
			<label for="decision">Decision</label>
			<select id="decision" name="decision" required>
				{#each data.appealable as d}<option value="{d.kind}:{d.subject_id}">{d.label}{d.date ? ` (${date(d.date)})` : ''}</option>{/each}
			</select>
		</div>
		<div>
			<label for="reason">What was wrong, and what evidence do you have?</label>
			<textarea id="reason" name="reason" required minlength="30" maxlength="4000">{form?.reason ?? ''}</textarea>
		</div>
		<div><button class="btn md" type="submit">Send appeal</button></div>
	</form>
{:else}
	<div class="empty">There are no decisions about you to appeal.</div>
{/if}

{#if data.appeals.length}
	<section class="lines" aria-labelledby="your-appeals">
		<div class="panel-head"><h3 id="your-appeals">Your appeals</h3></div>
		{#each data.appeals as a (a.id)}
			{@const [label, tone] = STATUS[a.status] ?? [a.status, '']}
			<div class="line appeal-row">
				<span class="a-body"><b>{a.kind} #{a.subject_id}</b>{#if a.outcome}<span class="small muted">{a.outcome}</span>{/if}</span>
				<span class="pill {tone}">{label}</span>
			</div>
		{/each}
	</section>
{/if}

<style>
	.appeal-row {
		align-items: flex-start;
	}
	.a-body {
		flex: 1;
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.a-body b {
		font-weight: 600;
	}
</style>
