<script lang="ts">
	import { onMount } from 'svelte';
	import { invalidateAll } from '$app/navigation';
	import type { Photo, Visit } from '$lib/api/types';
	import { call, FieldError } from '$lib/field/client';
	import { distanceM, locate } from '$lib/field/geo';
	import { deletePhoto, newRef, photosFor, putPhoto, shrink, type QueuedPhoto } from '$lib/field/queue';
	import { dateTime, statusLabel } from '$lib/format';
	import CheckIcon from '$lib/components/ui/CheckIcon.svelte';
	import { announce } from '$lib/announce.svelte';

	let { data } = $props();
	const visit = $derived(data.visit);
	const inProgress = $derived(visit.outcome === 'in_progress');

	// Photos already on the server, and photos still on this phone.
	// svelte-ignore state_referenced_locally
	let uploaded = $state<Photo[]>([...data.visit.photos]);
	let queued = $state<(QueuedPhoto & { url: string })[]>([]);
	let caption = $state('Living room');
	let status = $state('');
	let bad = $state(false);
	let camera = $state<HTMLInputElement>();
	$effect(() => {
		if (status) announce(status);
	});
	// Each check is answered Yes or No (unanswered blocks sending), as on the Verifier canvas.
	let answers = $state<Record<string, boolean | null>>({});
	let notes = $state('');
	let travelMinutes = $state<number | null>(null);
	let fares = $state<number | null>(null);
	let result = $state<'pass' | 'fail' | null>(null);
	let failReason = $state('');
	let sent = $state(false);
	let submitting = $state(false);
	let pumping = false;
	let retryTimer: ReturnType<typeof setTimeout> | undefined;

	const waiting = $derived(queued.filter((q) => q.state === 'queued').length);
	const keys = $derived(Object.keys(visit.checklist_items));
	const allAnswered = $derived(keys.every((k) => answers[k] === true || answers[k] === false));
	const allYes = $derived(keys.every((k) => answers[k] === true));
	const ready = $derived(allAnswered && result !== null && (result === 'fail' || (allYes && uploaded.length >= visit.min_photos)) && !waiting);
	const submitLabel = $derived(
		!allAnswered
			? 'Answer every check'
			: !result
				? 'Choose pass or fail'
				: result === 'pass' && uploaded.length + waiting < visit.min_photos
					? `Take at least ${visit.min_photos} photos`
					: waiting
						? 'Wait for photos to upload'
						: 'Send report'
	);
	const REASONS: [string, string][] = [
		['ID_MISMATCH', 'Person is not the card holder'],
		['DOCS_MISSING', 'No original document shown'],
		['DOCS_SUSPECT', 'Document looks altered'],
		['OWNER_UNREACHABLE', 'Owner could not be reached'],
		['UNIT_NOT_FOUND', 'Address not found'],
		['UNIT_OCCUPIED', 'Home is occupied'],
		['UNIT_MISMATCH', "Home doesn't match the listing"],
		['OTHER', 'Something else (explain in notes)']
	];
	const answer = (k: string, v: boolean) => {
		answers = { ...answers, [k]: v };
		if (!v && result === 'pass') result = null;
	};

	function say(text: string, isBad = false) {
		status = text;
		bad = isBad;
	}

	async function refreshQueue() {
		for (const q of queued) URL.revokeObjectURL(q.url);
		queued = (await photosFor(visit.id)).map((q) => ({ ...q, url: URL.createObjectURL(q.blob) }));
	}

	async function pump() {
		if (pumping || !navigator.onLine) return;
		pumping = true;
		try {
			for (const item of (await photosFor(visit.id)).filter((q) => q.state === 'queued')) {
				const form = new FormData();
				form.append('photo', item.blob, `${item.ref}.jpg`);
				form.append('lat', String(item.lat));
				form.append('lng', String(item.lng));
				form.append('taken_at', item.takenAt);
				form.append('caption', item.caption);
				form.append('client_ref', item.ref);
				try {
					const res = await call<Photo>(`/verify/visits/${visit.id}/photos`, { method: 'POST', form });
					await deletePhoto(item.ref);
					if (!uploaded.some((p) => p.id === res.data.id)) uploaded = [...uploaded, res.data];
					if (res.meta.duplicate) say('One photo matches a photo of another home. The reviewer will check it.', true);
					else say(`Photo saved${res.data.caption ? `: ${res.data.caption}` : ''}. ${uploaded.length} of at least ${visit.min_photos}.`);
				} catch (err) {
					if (err instanceof FieldError && err.retryable) {
						say('Upload paused: no connection. Photos are saved on this phone and will retry.');
						clearTimeout(retryTimer);
						retryTimer = setTimeout(pump, 15000);
						break;
					}
					await putPhoto({ ...item, state: 'failed', error: (err as Error).message });
					say(`Photo not saved: ${(err as Error).message} Remove it and take it again.`, true);
				}
				await refreshQueue();
			}
		} finally {
			pumping = false;
			await refreshQueue();
		}
	}

	async function onPhoto(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const files = [...(input.files ?? [])];
		input.value = '';
		if (!files.length) return;
		say('Checking your location…');
		let fix;
		try {
			fix = await locate();
		} catch (err) {
			say(`Photo not kept: ${(err as Error).message}`, true);
			return;
		}
		const far = Math.round(distanceM(fix.lat, fix.lng, Number(visit.unit.lat), Number(visit.unit.lng)));
		if (far > visit.radius_m) {
			say(`Photo not kept: you are about ${far} m from the home. Photos must be taken at the property.`, true);
			return;
		}
		const takenAt = new Date().toISOString();
		for (const file of files) {
			await putPhoto({ ref: newRef(), visitId: visit.id, blob: await shrink(file), lat: fix.lat, lng: fix.lng, takenAt, caption, state: 'queued' });
		}
		say(navigator.onLine ? 'Uploading…' : 'Saved on this phone. It will upload when you have signal.');
		await refreshQueue();
		pump();
	}

	async function remove(ref: string) {
		await deletePhoto(ref);
		await refreshQueue();
	}

	async function finish() {
		if (!ready) return;
		submitting = true;
		try {
			const payload = Object.fromEntries(keys.map((k) => [k, answers[k] === true]));
			await call<Visit>(`/verify/visits/${visit.id}/complete`, {
				method: 'POST',
				json: {
					checklist: payload,
					notes,
					travel_minutes: travelMinutes,
					transport_ghs: fares,
					result,
					fail_reason: result === 'fail' && failReason ? failReason : null
				}
			});
			sent = true;
			scrollTo(0, 0);
			await invalidateAll();
		} catch (err) {
			say(err instanceof FieldError && err.retryable ? 'No connection. Try again when you have signal.' : (err as Error).message, true);
		} finally {
			submitting = false;
		}
	}

	onMount(() => {
		refreshQueue().then(pump);
		const onOnline = () => pump();
		window.addEventListener('online', onOnline);
		const timer = setInterval(pump, 30000);
		return () => {
			window.removeEventListener('online', onOnline);
			clearInterval(timer);
			clearTimeout(retryTimer);
		};
	});
</script>

<svelte:head><title>Visit · {visit.unit.digital_address} · Afe Verify</title></svelte:head>

{#if inProgress && !sent}
	<h1 class="sr">Visit report</h1>
	<div class="vcard">
		<div class="q"><span class="dot yes" aria-hidden="true">✓</span><span><span class="sr">Done: </span>Check in at the address</span></div>
		<span class="small muted">Within {Math.round(visit.checkin_distance_m)} m of {visit.unit.digital_address} at {dateTime(visit.started_at)}</span>
	</div>

	{#each Object.entries(visit.checklist_items) as [key, label], i (key)}
		{@const a = answers[key]}
		<div class="vcard" role="group" aria-labelledby="q-{key}">
			<div class="q"><span class="dot" class:yes={a === true} class:no={a === false} aria-hidden="true">{a === true ? '✓' : a === false ? '✕' : i + 2}</span><span id="q-{key}">{label}</span></div>
			<div class="pick">
				<button type="button" class="yes" class:on={a === true} aria-pressed={a === true} onclick={() => answer(key, true)}>Yes</button>
				<button type="button" class="no" class:on={a === false} aria-pressed={a === false} onclick={() => answer(key, false)}>No</button>
			</div>
		</div>
	{/each}

	<div class="vcard">
		<div class="row spread"><span class="q-t">Listing photos</span><span class="mono small muted" aria-hidden="true">{uploaded.length} / {visit.min_photos} min</span><span class="sr">{uploaded.length} saved, at least {visit.min_photos} needed</span></div>
		<label for="caption" class="sr">What is this photo of?</label>
		<select id="caption" bind:value={caption} style="height: 44px; font-size: 15px">{#each visit.captions as c}<option>{c}</option>{/each}</select>
		<div class="shots">
			{#each uploaded as p (p.id)}
				<figure class="shot done" title={p.caption}><img src={p.url} alt="{p.caption}, saved" /><span aria-hidden="true">✓</span></figure>
			{/each}
			{#each queued as q (q.ref)}
				<figure class="shot {q.state}" title={q.state === 'failed' ? `Not saved: ${q.error}` : 'Waiting to upload'}>
					<img src={q.url} alt="{q.caption}, {q.state === 'failed' ? 'not saved' : 'waiting to upload'}" />
					{#if q.state === 'failed'}<button type="button" class="rm" onclick={() => remove(q.ref)} aria-label="Remove photo">✕</button>{:else}<span aria-hidden="true">…</span>{/if}
				</figure>
			{/each}
			{#each Array(Math.max(1, visit.min_photos - uploaded.length - queued.length)) as _, i (i)}
				<button type="button" class="shot add" aria-label="Take a photo" onclick={() => camera?.click()}>+</button>
			{/each}
		</div>
		<input id="camera" type="file" accept="image/*" capture="environment" hidden onchange={onPhoto} bind:this={camera} />
		{#if status}<p class="status" class:bad style="margin: 0">{status}</p>{/if}
		<span class="small muted">Camera only. Photos are stamped with time and GPS.{waiting ? ` ${waiting} waiting to upload.` : ''}</span>
	</div>

	<div class="vcard">
		<span class="q-t" id="result-q">Result</span>
		<div class="pick" role="group" aria-labelledby="result-q">
			<button type="button" class="yes" class:on={result === 'pass'} aria-pressed={result === 'pass'} disabled={allAnswered && !allYes} onclick={() => (result = 'pass')}>Pass</button>
			<button type="button" class="no" class:on={result === 'fail'} aria-pressed={result === 'fail'} onclick={() => (result = 'fail')}>Fail</button>
		</div>
		{#if allAnswered && !allYes}<span class="small muted">A “No” answer means the visit fails.</span>{/if}
		{#if result === 'fail'}
			<select bind:value={failReason} aria-label="Why it failed" style="font-size: 15px">
				<option value="">Reason (optional)</option>
				{#each REASONS as [code, label]}<option value={code}>{code} · {label}</option>{/each}
			</select>
		{/if}
		<textarea placeholder="Notes for the reviewer" aria-label="Notes for the reviewer" rows="3" maxlength="1800" bind:value={notes}></textarea>
		<details>
			<summary class="small">Travel for this visit (for costing)</summary>
			<div class="form-grid" style="margin-top: 10px">
				<div>
					<label for="travel">Travel time (minutes)</label>
					<input id="travel" type="number" inputmode="numeric" min="0" max="600" bind:value={travelMinutes} />
				</div>
				<div>
					<label for="fares">Fares or fuel (GH₵)</label>
					<input id="fares" type="number" inputmode="decimal" min="0" max="2000" step="0.5" bind:value={fares} />
				</div>
			</div>
		</details>
	</div>

	<div class="sendbar">
		<button class="btn big" type="button" onclick={finish} disabled={!ready || submitting}>{submitting ? 'Sending…' : submitLabel}</button>
	</div>
{:else}
	<span class="done-mark" style="margin-top: 8px"><CheckIcon size={24} weight={2.2} /></span>
	<h1>{sent ? 'Report sent for review' : `Visit ${statusLabel(visit.outcome).toLowerCase()}`}</h1>
	<p class="lead">
		{sent ? 'A reviewer at Afe makes the final decision.' : `Submitted ${dateTime(visit.completed_at)} with ${visit.photos.length} photos.`}
		You can't edit this report now; add notes by calling the review desk.
	</p>
	<a class="btn big" href="/field">Next visit</a>
	{#if visit.photos.length}
		<div class="shots">
			{#each visit.photos as p (p.id)}<figure class="shot done"><img src={p.url} alt={p.caption} /></figure>{/each}
		</div>
	{/if}
{/if}

<style>
	.vcard {
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: 12px;
		padding: 14px;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.q {
		display: flex;
		gap: 10px;
		align-items: center;
		font-weight: 600;
		font-size: 15.5px;
	}
	.q-t {
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
	.dot.yes {
		background: var(--ok);
		color: var(--on-ok);
	}
	.dot.no {
		background: var(--crit);
		color: var(--on-crit);
	}
	.pick {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 8px;
	}
	.pick button {
		height: 48px;
		border-radius: 8px;
		border: 1px solid var(--line);
		background: var(--surface);
		color: var(--ink);
		font: 600 15px var(--font-sans);
		cursor: pointer;
	}
	.pick .yes.on {
		border: 2px solid var(--ok);
		background: var(--ok-soft);
		color: var(--ok);
	}
	.pick .no.on {
		border: 2px solid var(--crit);
		background: var(--crit-soft);
		color: var(--crit);
	}
	.pick button:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
	.shots {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 6px;
	}
	.shot {
		position: relative;
		margin: 0;
		aspect-ratio: 1;
		border-radius: 8px;
		overflow: hidden;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 18px;
		font-weight: 700;
		background: var(--tint);
	}
	.shot img {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		object-fit: cover;
	}
	/* The marks sit on a photo of any colour: a solid badge keeps them readable. */
	.shot span {
		position: relative;
		width: 26px;
		height: 26px;
		border-radius: 99px;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 14px;
		background: rgba(21, 33, 30, 0.75);
		color: #fff;
	}
	.shot.done span {
		background: var(--ok);
		color: var(--on-ok);
	}
	.shot.queued img {
		opacity: 0.55;
	}
	.shot.failed {
		outline: 2px solid var(--crit);
		outline-offset: -2px;
	}
	.shot.add {
		border: 2px dashed var(--line);
		background: var(--paper);
		color: var(--muted);
		cursor: pointer;
		margin: 0;
		padding: 0;
		font: inherit;
		font-size: 18px;
		font-weight: 700;
		width: 100%;
	}
	.rm {
		position: relative;
		width: 28px;
		height: 28px;
		border: 0;
		border-radius: 99px;
		background: var(--crit);
		color: var(--on-crit);
		cursor: pointer;
	}
	.sendbar {
		position: sticky;
		bottom: 0;
		margin: 0 -16px -40px;
		padding: 12px 16px 20px;
		background: var(--head-bg);
		border-top: 1px solid var(--line);
	}
	.lead {
		margin: 0;
		font-size: 15px;
		color: var(--muted);
		line-height: 1.55;
	}
</style>
