<script lang="ts">
	import ListingCard from '$lib/components/ListingCard.svelte';
	import HomesMap from '$lib/components/HomesMap.svelte';
	import { bedrooms, ghs } from '$lib/format';

	let { data } = $props();
	const o = $derived(data.overview);
</script>

<svelte:head>
	<title>Renting in {o.area.name} · Afe</title>
	<meta name="description" content="Verified homes and rents in {o.area.name}, {o.area.city}. Every home visited by Afe." />
</svelte:head>

<a class="back" href="/homes">← All homes</a>
<h1>Renting in {o.area.name}</h1>
<p class="lede">{o.live} verified {o.live === 1 ? 'home' : 'homes'} live now in {o.area.name}, {o.area.city}.</p>

{#if o.ranges.length}
	<h2>What rent usually costs</h2>
	<div class="scroll">
		<table class="q">
			<thead><tr><th>Size</th><th>Usual range</th><th>Middle</th><th>From</th></tr></thead>
			<tbody>
				{#each o.ranges as r (r.bedrooms)}
					<tr>
						<td>{bedrooms(r.bedrooms)}{r.bedrooms === 3 ? ' or more' : ''}</td>
						<td>{ghs(r.low)} – {ghs(r.high)}</td>
						<td><strong>{ghs(r.median)}</strong></td>
						<td class="small muted">{r.source === 'afe' ? `${r.count} verified Afe listings` : "Afe's price survey"}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
	<p class="note">Monthly rent. A home far below these prices is a common scam: check it before you pay anything.</p>
{/if}

<h2>Homes in {o.area.name}</h2>
{#if o.listings.length}
	<div class="area-map"><HomesMap listings={o.listings} /></div>
	<div class="grid">{#each o.listings as listing (listing.id)}<ListingCard {listing} />{/each}</div>
	<p><a class="btn secondary" href="/homes?area={o.area.slug}">See all and get alerts</a></p>
{:else}
	<p class="empty">No verified homes here right now. <a href="/homes?area={o.area.slug}">Get told when one is listed</a>.</p>
{/if}

<style>
	.area-map {
		height: 380px;
		border-radius: 12px;
		overflow: hidden;
		border: 1px solid var(--line);
		margin-bottom: 20px;
	}
</style>
