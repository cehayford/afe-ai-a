<script lang="ts">
	// Workload: the time-to-live numbers as stat cards, the queues as the canvas's table, and each
	// reviewer's decisions this week as bars.
	let { data } = $props();
	const w = $derived(data.w);
	const most = $derived(Math.max(1, ...w.decisions_last_7_days.map((r) => r.decisions)));
	const onTarget = $derived(w.median_days_to_live !== null && w.median_days_to_live <= 7);
</script>

<svelte:head><title>Workload · Afe review</title></svelte:head>

<nav class="pills" aria-label="Verifiers">
	<a href="/review/verifiers">Quality</a><a href="/review/workload" aria-current="page">Workload</a><a href="/review/visit-plan">Visit plan</a>
</nav>
<div class="page-head">
	<h1>Workload</h1>
	<p>Items waiting longer than {w.sla_days} days are over the service target. The plan's target from registering a home to its first live listing is 7 days or less.</p>
</div>

<div class="stats-row">
	<div class="stat"><b style={w.median_days_to_live === null ? '' : onTarget ? 'color: var(--ok)' : 'color: var(--crit)'}>{w.median_days_to_live ?? '—'}{w.median_days_to_live === null ? '' : ' days'}</b><span>Median to first live listing (30 days)</span></div>
	<div class="stat"><b>{w.homes_live_last_30_days}</b><span>Homes live in the last 30 days</span></div>
	<div class="stat"><b>{w.queues.reduce((n, q) => n + q.count, 0)}</b><span>Waiting in all queues</span></div>
	<div class="stat"><b>{w.queues.reduce((n, q) => n + q.over_sla, 0)}</b><span>Over {w.sla_days} days</span></div>
</div>

<div class="scroll">
	<table class="q">
		<thead><tr><th>Queue</th><th>Waiting</th><th>Oldest</th><th>Over {w.sla_days} days</th></tr></thead>
		<tbody>
			{#each w.queues as q (q.queue)}
				<tr>
					<td><b>{q.queue}</b></td>
					<td class="n">{q.count}</td>
					<td class="n">{q.oldest_days === null ? '—' : `${q.oldest_days} days`}</td>
					<td>{#if q.over_sla}<span class="pill bad">{q.over_sla}</span>{:else}<span class="muted">0</span>{/if}</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>

<section class="case" aria-labelledby="dec-h">
	<div class="case-head"><b id="dec-h">Decisions in the last 7 days</b></div>
	{#each w.decisions_last_7_days as r (r.reviewer)}
		<div class="d-row">
			<span class="d-name">{r.reviewer}</span>
			<span class="meter-bar"><span style="width: {(r.decisions / most) * 100}%"></span></span>
			<b class="n">{r.decisions}</b>
		</div>
	{:else}
		<div class="case-body muted small">No decisions yet this week.</div>
	{/each}
</section>

<style>
	.n {
		font-variant-numeric: tabular-nums;
	}
	.d-row {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 10px 16px;
		border-bottom: 1px solid var(--hair);
		font-size: 14.5px;
	}
	.d-row:last-child {
		border-bottom: 0;
	}
	.d-name {
		flex: 0 0 160px;
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.d-row b {
		width: 32px;
		text-align: right;
	}
	@media (max-width: 480px) {
		.d-name {
			flex-basis: 110px;
		}
	}
</style>
