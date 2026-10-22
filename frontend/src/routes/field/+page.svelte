<script lang="ts">
	// Today's visits, from the Verifier canvas: one card per visit, the next one outlined in green.
	import { dateTime, day } from '$lib/format';

	let { data } = $props();
	const open = $derived(data.work.assignments.filter((a) => a.status === 'open'));
</script>

<svelte:head><title>Your visits · Afe Verify</title></svelte:head>

<div class="head-row">
	<h1>Today's visits</h1>
	<span>{open.length} to do</span>
</div>

{#each data.work.in_progress as v (v.id)}
	<a class="visit next" href="/field/visits/{v.id}">
		<div class="top"><span class="time">Started {dateTime(v.started_at)}</span><span class="pill next">In progress</span></div>
		<span class="title">Visit in progress</span>
		<span class="sub">Continue where you left off →</span>
	</a>
{/each}

{#each data.work.assignments as a, i (a.id)}
	{@const next = !data.work.in_progress.length && i === data.work.assignments.findIndex((x) => x.status === 'open')}
	<a class="visit" class:next class:sent={a.status !== 'open'} href="/field/assignments/{a.id}">
		<div class="top">
			<span class="time">{day(a.scheduled_for)}</span>
			<span class="pill {a.status !== 'open' ? 'ok' : next ? 'next' : 'quiet'}">{a.status !== 'open' ? 'Sent' : next ? 'Next' : 'Later'}</span>
		</div>
		<span class="title">{a.unit.unit_label} · {a.unit.property_type_label}</span>
		<span class="sub">{a.unit.digital_address}, {a.unit.area.name} · Owner: {a.landlord_name}</span>
		{#if a.purpose === 'qa_recheck'}<span class="tag soft">Second check · re-verify another verifier's pass</span>{/if}
	</a>
{:else}
	{#if !data.work.in_progress.length}<p class="empty">No visits assigned. A reviewer will add them here, and you'll get an SMS.</p>{/if}
{/each}

<style>
	.head-row {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
	}
	.head-row span {
		font-size: 13px;
		color: var(--muted);
	}
	.visit {
		text-align: left;
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: 12px;
		padding: 14px;
		display: flex;
		flex-direction: column;
		gap: 6px;
		color: var(--ink);
	}
	.visit:hover {
		color: var(--ink);
		border-color: var(--brand);
	}
	.visit.next {
		border: 2px solid var(--brand);
		padding: 13px;
	}
	.visit.sent {
		opacity: 0.6;
	}
	.top {
		display: flex;
		justify-content: space-between;
		gap: 8px;
		align-items: center;
	}
	.time {
		font: 500 13px var(--font-mono);
	}
	.top .pill {
		font-size: 12px;
		padding: 3px 9px;
	}
	.title {
		font: 700 18px var(--font-display);
	}
	.sub {
		font-size: 14px;
		color: var(--muted);
	}
</style>
