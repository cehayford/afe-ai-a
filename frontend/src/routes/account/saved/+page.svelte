<script lang="ts">
	// Saved tab of My Afe (Renter canvas): compact cards, title then area and rent.
	import { cedis } from '$lib/format';

	let { data } = $props();
</script>

<svelte:head><title>Saved homes · Afe</title></svelte:head>

<h2 class="sr">Saved homes</h2>
{#if data.listings.length}
	<div class="saved-grid">
		{#each data.listings as l (l.id)}
			<a class="saved-card" href="/homes/{l.reference}">
				<span class="t">{l.title}</span>
				<span class="m">{l.area} · {cedis(l.rent_display)} / month</span>
				{#if l.status !== 'live'}<span class="pill warn">No longer listed</span>{/if}
			</a>
		{/each}
	</div>
{:else}
	<p class="muted" style="margin: 0; font-size: 15px">Nothing saved yet. Tap Save on any home to keep it here. <a href="/homes">Find a home</a></p>
{/if}

<style>
	.saved-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(min(100%, 280px), 1fr));
		gap: 12px;
	}
	.saved-card {
		text-align: left;
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: 12px;
		padding: 16px;
		display: flex;
		flex-direction: column;
		gap: 6px;
		color: var(--ink);
	}
	.saved-card:hover {
		border-color: var(--brand);
		color: var(--ink);
	}
	.t {
		font: 700 18px var(--font-display);
	}
	.m {
		font-size: 14px;
		color: var(--muted);
	}
</style>
