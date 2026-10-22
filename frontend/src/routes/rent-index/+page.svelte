<script lang="ts">
	// The public rent index: a page head with the date, the medians as the canvas's table (each figure
	// with how many verified homes back it), and the scam warning as a notice.
	import { cedis, date, ghs } from '$lib/format';

	let { data } = $props();
	const SIZES: [string, string][] = [['0', 'Single room'], ['1', '1 bedroom'], ['2', '2 bedrooms'], ['3', '3+ bedrooms']];
	const homes = $derived(data.index.areas.reduce((n, a) => n + Object.values(a.sizes).reduce((m, s) => m + s.count, 0), 0));
</script>

<svelte:head>
	<title>Accra verified rent index · Afe</title>
	<meta name="description" content="Median monthly rents in Accra neighbourhoods, from homes Afe verified in person." />
</svelte:head>

<div class="page-1000">
	<div class="page-head">
		<span class="kicker">Rent index · {date(data.index.as_of)}</span>
		<h1>Accra verified rent index</h1>
		<p>
			Median monthly rent from homes Afe checked in person and listed in the last {data.index.period_days} days. A figure appears only when at least
			3 verified homes back it.
		</p>
	</div>

	{#if data.index.areas.length}
		<div class="stats-row">
			<div class="stat"><b>{data.index.areas.length}</b><span>Neighbourhoods with figures</span></div>
			<div class="stat"><b>{homes}</b><span>Verified homes behind them</span></div>
			<div class="stat"><b>{data.index.period_days} days</b><span>Listings counted</span></div>
		</div>
		<div class="scroll">
			<table class="q idx">
				<thead><tr><th>Area</th>{#each SIZES as [, label] (label)}<th>{label}</th>{/each}</tr></thead>
				<tbody>
					{#each data.index.areas as a (a.slug)}
						<tr>
							<td><a class="area" href="/areas/{a.slug}">{a.name}</a></td>
							{#each SIZES as [key] (key)}
								<td>
									{#if a.sizes[key]}<span class="med">{cedis(ghs(a.sizes[key].median))}</span><small>{a.sizes[key].count} homes</small>{:else}<span class="muted">—</span>{/if}
								</td>
							{/each}
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{:else}
		<div class="empty">Not enough verified homes yet to publish figures. The index fills in as Afe verifies more homes.</div>
	{/if}

	<div class="notice row spread">
		<span><b>A home far below these figures is a common scam.</b> Check the listing or number before you pay anything.</span>
		<a class="btn secondary sm" href="/check">Check before you pay</a>
	</div>
</div>

<style>
	.idx {
		min-width: 620px;
	}
	.area {
		font-weight: 600;
	}
	.med {
		display: block;
		font: 700 17px var(--font-display);
		font-variant-numeric: tabular-nums;
		white-space: nowrap;
	}
</style>
