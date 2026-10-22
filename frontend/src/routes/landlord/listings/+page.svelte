<script lang="ts">
	// Listings tab from the Landlord canvas: one table, home, rent, interest and status.
	import { cedis, statusLabel } from '$lib/format';

	let { data } = $props();
	const tone = (s: string) => (s === 'live' ? 'ok' : s === 'pending_review' || s === 'draft' ? 'warn' : s === 'paused' ? 'quiet' : '');
</script>

<svelte:head><title>Listings · Afe</title></svelte:head>

<div class="row spread"><h1 style="margin: 0; font-size: 30px">Listings</h1><a class="btn md" href="/landlord/homes/new">Add a home</a></div>

{#if data.listings.length}
	<div class="scroll">
		<table class="q" style="min-width: 600px">
			<thead><tr><th>Home</th><th>Rent</th><th>Viewings</th><th>Status</th></tr></thead>
			<tbody>
				{#each data.listings as l (l.id)}
					<tr>
						<td><a class="t" href="/landlord/listings/{l.id}">{l.title}</a><div class="mono">{l.reference} · {l.area}</div></td>
						<td class="num">{cedis(l.rent_display)}</td>
						<td>{l.viewings || '—'}</td>
						<td><span class="pill {tone(l.status)}">{l.status === 'pending_review' ? 'Awaiting review' : statusLabel(l.status)}</span></td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{:else}
	<p class="empty">No listings yet. Once a home is verified, you can list it from its page.</p>
{/if}

<style>
	.t {
		font-weight: 600;
		color: var(--ink);
	}
	.t:hover {
		color: var(--brand);
	}
	@media (prefers-color-scheme: dark) {
		.t:hover {
			color: var(--primary-hover);
		}
	}
</style>
