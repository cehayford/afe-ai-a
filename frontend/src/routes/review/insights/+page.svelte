<script lang="ts">
	// Targets: how many are met, then the canvas's table of measures with a Met / Not yet pill.
	let { data } = $props();
	const show = (v: number | null, name: string) =>
		v === null
			? '—'
			: name.includes('pesewas')
				? `GH₵${(v / 100).toLocaleString('en-GH')}`
				: name.startsWith('Share') || name.startsWith('Enquiries')
					? `${Math.round(v * 100)}%`
					: v.toLocaleString('en-GH');
	const label = (name: string) => name.replace(' (pesewas)', '');
	const met = $derived(data.targets.filter((t) => t.met === true).length);
	const judged = $derived(data.targets.filter((t) => t.met !== null && t.met !== undefined).length);
</script>

<svelte:head><title>Targets · Afe review</title></svelte:head>

<nav class="pills" aria-label="Models">
	<a href="/review/detection">Models</a><a href="/review/label-checks">Label checks</a><a href="/review/insights" aria-current="page">Targets</a>
</nav>
<div class="page-head">
	<div class="row spread"><h1>Targets</h1><span class="pill {met === judged ? 'ok' : 'warn'}">{met} of {judged} met</span></div>
	<p>The build plan's targets (§13), as they stand today.</p>
</div>

<div class="scroll">
	<table class="q">
		<thead><tr><th>Measure</th><th>Now</th><th>Target</th><th><span class="sr">Status</span></th></tr></thead>
		<tbody>
			{#each data.targets as t (t.name)}
				<tr>
					<td><b>{label(t.name)}</b>{#if t.note}<br /><small>{t.note}</small>{/if}</td>
					<td class="now">{show(t.value, t.name)}</td>
					<td class="tgt">{t.target}</td>
					<td>{#if t.met === true}<span class="pill ok">Met</span>{:else if t.met === false}<span class="pill warn">Not yet</span>{/if}</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>

<style>
	.now {
		font: 700 18px var(--font-display);
		white-space: nowrap;
		font-variant-numeric: tabular-nums;
	}
	.tgt {
		color: var(--muted);
		font-size: 14px;
	}
</style>
