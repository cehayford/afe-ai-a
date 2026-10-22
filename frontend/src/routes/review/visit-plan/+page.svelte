<script lang="ts">
	// Visit plan: pick a day (it applies at once, like the web filters), then one route card per
	// verifier with numbered stops and an Assign button, and the homes no one may visit.
	import { enhance } from '$app/forms';
	import { goto } from '$app/navigation';
	import FormError from '$lib/components/FormError.svelte';
	import { day } from '$lib/format';
	import Done from '$lib/components/Done.svelte';

	let { data, form } = $props();
	const plan = $derived(data.plan);
	let busy = $state(false);
	const pick = (e: Event & { currentTarget: HTMLInputElement }) => {
		const v = e.currentTarget.value;
		if (/^\d{4}-\d{2}-\d{2}$/.test(v)) goto(`?day=${v}`, { keepFocus: true, noScroll: true });
	};
</script>

<svelte:head><title>Visit plan · Afe review</title></svelte:head>

<nav class="pills" aria-label="Verifiers">
	<a href="/review/verifiers">Quality</a><a href="/review/workload">Workload</a><a href="/review/visit-plan" aria-current="page">Visit plan</a>
</nav>
<div class="page-head">
	<div class="row spread">
		<h1>Visit plan for {day(plan.day)}</h1>
		<form class="day" method="get">
			<label for="day" class="small">Plan for</label>
			<input id="day" type="date" name="day" value={plan.day} onchange={pick} />
			<noscript><button class="btn secondary sm" type="submit">Show</button></noscript>
		</form>
	</div>
	<p>Suggested routes: each verifier stays in one area and visits up to {plan.per_verifier} nearby homes. The rules on who may visit which home still apply when you assign.</p>
</div>
<FormError message={form?.error} />
<Done message={form?.assigned !== undefined ? `Assigned ${form.assigned} visit${form.assigned === 1 ? '' : 's'}.` : null} key={form} />
{#if form?.assigned !== undefined}
	{#each form.problems ?? [] as p, i (i)}<p class="flag" style="margin: 0">{p}</p>{/each}
{/if}

<div class="routes">
	{#each plan.routes as route (route.verifier_id)}
		<form
			class="case"
			method="post"
			action="?/assign"
			use:enhance={() => {
				busy = true;
				return async ({ update }) => {
					await update();
					busy = false;
				};
			}}
		>
			<div class="case-head">
				<span class="r-head"><b>{route.verifier_name}</b><span class="mono">{route.area} · {route.stops.length} visits · about {route.km} km</span></span>
				<span class="ktag">Route</span>
			</div>
			<input type="hidden" name="verifier_id" value={route.verifier_id} />
			<input type="hidden" name="day" value={plan.day} />
			<ol class="stops">
				{#each route.stops as stop (stop.unit_id)}
					<li>
						<input type="hidden" name="unit_id" value={stop.unit_id} />
						<a href="/review/homes/{stop.unit_id}">{stop.address}</a><span class="small muted">{stop.landlord}</span>
					</li>
				{/each}
			</ol>
			<div class="case-foot"><div><button class="btn md" type="submit" disabled={busy}>Assign this route</button></div></div>
		</form>
	{:else}
		<div class="empty">No homes waiting for a visit, or no verifier free to take them.</div>
	{/each}
</div>

{#if plan.unplanned.length}
	<section class="case" aria-labelledby="un-h">
		<div class="case-head"><b id="un-h">Not planned</b><span class="pill warn">{plan.unplanned.length}</span></div>
		<div class="case-body small muted">No free verifier may visit these (rotation or a personal interest in the home). Assign them from the home page.</div>
		{#each plan.unplanned as stop (stop.unit_id)}
			<div class="u-row"><a href="/review/homes/{stop.unit_id}">{stop.address}</a><span class="small muted">{stop.landlord}</span></div>
		{/each}
	</section>
{/if}

<style>
	.day {
		display: flex;
		gap: 8px;
		align-items: center;
	}
	.day label {
		margin: 0;
		white-space: nowrap;
	}
	.day input {
		height: 40px;
		width: auto;
	}
	.routes {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 340px), 1fr));
		gap: 16px;
		align-items: start;
	}
	.r-head {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.stops {
		list-style: none;
		margin: 0;
		padding: 0;
		counter-reset: stop;
	}
	.stops li {
		counter-increment: stop;
		display: flex;
		flex-wrap: wrap;
		gap: 2px 10px;
		align-items: center;
		padding: 10px 16px;
		border-bottom: 1px solid var(--hair);
		font-size: 14.5px;
	}
	.stops li::before {
		content: counter(stop);
		width: 24px;
		height: 24px;
		flex: 0 0 auto;
		border-radius: 99px;
		background: var(--tint);
		color: var(--brand);
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 12px;
		font-weight: 700;
	}
	.u-row {
		display: flex;
		flex-wrap: wrap;
		gap: 2px 10px;
		align-items: baseline;
		padding: 10px 16px;
		border-top: 1px solid var(--hair);
		font-size: 14.5px;
	}
	@media (prefers-color-scheme: dark) {
		.stops li::before {
			color: var(--accent);
		}
	}
</style>
