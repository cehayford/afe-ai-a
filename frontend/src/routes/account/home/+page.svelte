<script lang="ts">
	// My home: homes where the landlord keeps the rent on Afe (receipts, repairs, renewals).
	import { cedis, date, day, ghs } from '$lib/format';

	let { data } = $props();
	const soon = (d: string) => new Date(d).getTime() - Date.now() < 7 * 86_400_000;
</script>

<svelte:head><title>My home · Afe</title></svelte:head>

<h2 class="sr">My home</h2>
<p class="muted" style="margin: 0; font-size: 15px">Homes where your landlord keeps your rent on Afe: receipts, repairs, agreements and renewals.</p>
{#if data.homes.length}
	<div class="pcard-list">
		{#each data.homes as h (h.id)}
			<a class="home-card" href="/rentals/{h.id}">
				<div class="row spread">
					<span class="t">{h.home || `Let by ${h.landlord_name}`}</span>
					<span class="pill {soon(h.next_due_date) ? 'warn' : ''}">Next rent {day(h.next_due_date)}</span>
				</div>
				<span class="m">{cedis(ghs(h.rent_pesewas))} / month · until {date(h.end_date)} · landlord {h.landlord_name}</span>
			</a>
		{/each}
	</div>
{:else}
	<div class="empty">Nothing here yet. When your landlord adds you on Afe with this phone number, your home appears here.</div>
{/if}

<style>
	.home-card {
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: 12px;
		padding: 18px;
		display: flex;
		flex-direction: column;
		gap: 6px;
		color: var(--ink);
	}
	.home-card:hover {
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
