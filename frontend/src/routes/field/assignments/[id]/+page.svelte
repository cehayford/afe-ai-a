<script lang="ts">
	// Before the visit: the home, the owner, directions, then check-in (the Verifier canvas's first
	// check). Check-in uses the phone's GPS and starts the visit.
	import { goto } from '$app/navigation';
	import type { Visit } from '$lib/api/types';
	import { call } from '$lib/field/client';
	import { distanceM, locate } from '$lib/field/geo';
	import { bedrooms, day } from '$lib/format';
	import { announce } from '$lib/announce.svelte';

	let { data } = $props();
	const a = $derived(data.assignment);
	const unit = $derived(a.unit);
	let status = $state('');
	let bad = $state(false);
	let busy = $state(false);
	$effect(() => {
		if (status) announce(status);
	});

	async function start() {
		busy = true;
		bad = false;
		status = 'Finding your location…';
		try {
			const fix = await locate();
			const far = Math.round(distanceM(fix.lat, fix.lng, Number(unit.lat), Number(unit.lng)));
			if (far > data.radius) {
				bad = true;
				status = `You are about ${far} m from the home's pin (GPS accurate to ${Math.round(fix.accuracy)} m). Go to the property and try again.`;
				return;
			}
			status = 'Checking in…';
			const res = await call<Visit>('/verify/visits', { method: 'POST', json: { unit_id: unit.id, lat: fix.lat, lng: fix.lng } });
			await goto(`/field/visits/${res.data.id}`);
		} catch (err) {
			bad = true;
			status = (err as Error).message;
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head><title>{unit.digital_address} · Afe Verify</title></svelte:head>

<h1 class="sr">{unit.digital_address} · {unit.unit_label}</h1>

<div class="fcard">
	<div class="top"><span class="time">{day(a.scheduled_for)}</span>{#if a.purpose === 'qa_recheck'}<span class="tag soft">Second check</span>{/if}</div>
	<span class="title">{bedrooms(unit.bedrooms)} · {unit.bathrooms} bath{unit.bathrooms === 1 ? '' : 's'} declared</span>
	<dl class="kv small">
		<dt>Address</dt><dd>{unit.digital_address}, {unit.area.name}</dd>
		{#if unit.landmark}<dt>Landmark</dt><dd>{unit.landmark}</dd>{/if}
		<dt>Owner</dt><dd>{a.landlord_name}{#if a.landlord_phone}{" · "}<a href="tel:{a.landlord_phone}">{a.landlord_phone}</a>{/if}</dd>
		{#if a.note}<dt>Note</dt><dd>{a.note}</dd>{/if}
	</dl>
	<a class="btn quiet block" href="https://www.google.com/maps/dir/?api=1&destination={unit.lat},{unit.lng}" target="_blank" rel="noopener">Directions in Google Maps</a>
</div>

{#if a.status === 'open'}
	<div class="fcard">
		<div class="q"><span class="dot">1</span><span>Check in at the address</span></div>
		<span class="small muted">Uses your phone GPS. Must be within {data.radius} m.</span>
		<button class="btn big" type="button" onclick={start} disabled={busy}>{busy ? 'Checking in…' : 'Check in'}</button>
		{#if status}<p class="status" class:bad style="margin: 0">{status}</p>{/if}
	</div>
{:else}
	<p class="empty">This visit is {a.status === 'done' ? 'done and sent for review' : a.status}.</p>
{/if}

<style>
	.fcard {
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: 12px;
		padding: 14px;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.top {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}
	.time {
		font: 500 13px var(--font-mono);
	}
	.title {
		font: 700 18px var(--font-display);
	}
	.q {
		display: flex;
		gap: 10px;
		align-items: center;
		font-weight: 600;
		font-size: 15.5px;
	}
	.dot {
		width: 26px;
		height: 26px;
		flex: 0 0 auto;
		border-radius: 99px;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 13px;
		font-weight: 700;
		background: var(--tint);
		color: var(--muted);
	}
</style>
