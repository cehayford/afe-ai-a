<script lang="ts">
	// Verifier quality as the canvas's table, with the pass rate as a bar and reversals as a red pill.
	import { initials } from '$lib/format';

	let { data } = $props();
	const pct = (v: number | null) => (v === null ? '—' : `${Math.round(v * 100)}%`);
</script>

<svelte:head><title>Verifier quality · Afe review</title></svelte:head>

<nav class="pills" aria-label="Verifiers">
	<a href="/review/verifiers" aria-current="page">Quality</a><a href="/review/workload">Workload</a><a href="/review/visit-plan">Visit plan</a>
</nav>
<div class="page-head">
	<h1>Verifier quality</h1>
	<p>For the monthly review (plan §5). A share of approved homes gets an unannounced re-check by a different verifier; a failed re-check is a reversal of the first verifier's work.</p>
</div>

<div class="scroll">
	<table class="q wide-t">
		<thead><tr><th>Verifier</th><th>Visits</th><th>Passed</th><th>Pass rate</th><th>Re-checked</th><th>Reversals</th></tr></thead>
		<tbody>
			{#each data.stats as v (v.id)}
				<tr class:off={!v.active}>
					<td><span class="who"><span class="avatar sm-av">{initials(v.name)}</span><span><b>{v.name}</b>{#if !v.active}<br /><small>inactive</small>{/if}</span></span></td>
					<td class="n">{v.visits}</td>
					<td class="n">{v.passed}</td>
					<td><span class="rate"><span class="meter-bar"><span style="width: {(v.pass_rate ?? 0) * 100}%"></span></span><span class="mono">{pct(v.pass_rate)}</span></span></td>
					<td class="n">{v.rechecked}</td>
					<td>{#if v.reversals}<span class="pill bad">{v.reversals}</span>{:else}<span class="muted">0</span>{/if}</td>
				</tr>
			{:else}
				<tr><td colspan="6" class="muted">No field verifiers yet.</td></tr>
			{/each}
		</tbody>
	</table>
</div>

<style>
	.wide-t {
		min-width: 640px;
	}
	.who {
		display: flex;
		gap: 10px;
		align-items: center;
	}
	.sm-av {
		width: 32px;
		height: 32px;
		font-size: 12.5px;
	}
	.n {
		font-variant-numeric: tabular-nums;
	}
	.rate {
		display: flex;
		align-items: center;
		gap: 8px;
		min-width: 140px;
	}
	.rate .mono {
		font-size: 13px;
		width: 38px;
		text-align: right;
	}
	.off td {
		opacity: 0.6;
	}
</style>
