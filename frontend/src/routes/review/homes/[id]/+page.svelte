<script lang="ts">
	// One home on the review desk, laid out like the Admin Review canvas's case: reference and title,
	// the verifier report (checks and photos) beside rule flags and model scores, the authority
	// documents, then the decision panel.
	import { enhance } from '$app/forms';
	import DecisionForm from '$lib/components/DecisionForm.svelte';
	import FormError from '$lib/components/FormError.svelte';
	import ModelNotes from '$lib/components/ModelNotes.svelte';
	import RevokePanel from '$lib/components/RevokePanel.svelte';
	import VerificationHistory from '$lib/components/VerificationHistory.svelte';
	import { bedrooms, date, dateTime, day, statusLabel } from '$lib/format';
	import Done from '$lib/components/Done.svelte';

	let { data, form } = $props();
	const h = $derived(data.home);
	const visit = $derived(h.visit);
	const preset = $derived(
		[
			h.authorities.some((a) => a.status === 'accepted') && 'DOCS_SIGHTED',
			h.authorities.some((a) => a.owner_confirmed_at) && 'OWNER_CONFIRMED',
			visit?.outcome === 'passed' && 'VISIT_MATCH',
			visit?.checklist?.ghana_card_seen_in_person && 'ID_SEEN_IN_PERSON'
		].filter((c): c is string => typeof c === 'string')
	);
	let busy = $state(false);
	const submit = () => {
		busy = true;
		return async ({ update }: { update: () => Promise<void> }) => {
			await update();
			busy = false;
		};
	};
</script>

<svelte:head><title>{h.unit.digital_address} · Review · Afe</title></svelte:head>

<div class="page-1180 home-case">
	<a class="back" href="/review">← Review queue</a>

	<div class="c-top">
		<div class="c-titles">
			<span class="mono small muted">{h.unit.digital_address}{h.unit.unit_label ? ` · ${h.unit.unit_label}` : ''}</span>
			<h1>{bedrooms(h.unit.bedrooms)} {h.unit.property_type_label.toLowerCase()}, {h.unit.area.name}</h1>
			<span class="muted">Registered by <a href="/review/people/{h.registered_by.id}">{h.registered_by.name}</a> · {h.registered_by.phone ?? 'no phone'}</span>
		</div>
		<span class="row">
			<span class="ktag">Verification</span>
			{#if h.current}<span class="pill ok">Verified until {date(h.current.expires_at)}</span>{/if}
		</span>
	</div>
	<Done message={form?.done} key={form} />

	<div class="c-grid">
		<section class="case" aria-labelledby="vr-h">
			<div class="case-head"><b id="vr-h">Verifier report</b><span class="mono">{visit ? `${visit.verifier_name} · ${dateTime(visit.completed_at)}` : 'Visit not yet done'}</span></div>
			{#if visit}
				<div class="c-row"><span class="tick {visit.checkin_distance_m <= visit.radius_m ? '' : 'no'}">{visit.checkin_distance_m <= visit.radius_m ? '✓' : '✕'}</span><span>GPS check-in within {Math.round(visit.checkin_distance_m)} m</span></div>
				{#each Object.entries(visit.checklist_items) as [key, label] (key)}
					<div class="c-row"><span class="tick {visit.checklist[key] ? '' : 'no'}">{visit.checklist[key] ? '✓' : '✕'}</span><span>{label}</span></div>
				{/each}
				<div class="c-row"><span class="pill {visit.outcome === 'passed' ? 'ok' : 'bad'}">{statusLabel(visit.outcome)}</span>{#if visit.notes}<span class="small muted">{visit.notes}</span>{/if}</div>
				{#if visit.photos.length}
					<div class="thumbs pad">
						{#each visit.photos as p (p.id)}
							<figure class="thumb" class:failed={p.duplicate_of_id}>
								<img src={p.url} alt={p.caption} loading="lazy" />
								<figcaption>{p.caption}{p.duplicate_of_id ? ' · matches another home' : ''}</figcaption>
							</figure>
						{/each}
					</div>
				{/if}
			{:else}
				<div class="c-row muted small">
					{#if h.open_assignment}Assigned to {h.open_assignment.verifier_name} for {day(h.open_assignment.scheduled_for)}.{:else}No visit assigned yet.{/if}
				</div>
			{/if}
		</section>

		<div class="c-side">
			<section class="case" aria-labelledby="fl-h">
				<div class="case-head"><b id="fl-h">Rule flags</b><span class="pill {h.fee_settled ? 'ok' : 'warn'}">Fee {h.fee_settled ? 'settled' : 'not paid'}</span></div>
				{#each h.flags as f (f.id)}
					<div class="f-row"><span class="row"><span class="sevtag {f.severity}">{f.severity}</span><b>{f.rule}</b></span><span class="small muted">{f.explanation}</span></div>
				{:else}
					<div class="f-row small muted">No rule hits.</div>
				{/each}
			</section>
			<ModelNotes notes={h.model_notes} />
		</div>
	</div>

	<section class="case" aria-labelledby="doc-h">
		<div class="case-head"><b id="doc-h">Authority documents</b><span class="mono">{h.authorities.length} uploaded</span></div>
		<FormError message={form?.form === 'authority' ? form.error : null} />
		{#each h.authorities as a (a.id)}
			<div class="d-row">
				<div class="row spread">
					<span><b>{a.document_label}</b> · {a.relationship_label}</span>
					<span class="pill {a.status === 'accepted' ? 'ok' : a.status === 'rejected' ? 'bad' : 'warn'}">{statusLabel(a.status)}</span>
				</div>
				<span class="small">
					<a href="/review/documents/{a.id}" target="_blank" rel="noopener">Open document</a> <span class="muted">(opening is logged)</span> ·
					Utility ref <span class="mono">{a.utility_reference || '—'}</span>
					{#if a.owner_confirmed_at} · owner {a.owner_name} confirmed {date(a.owner_confirmed_at)}{/if}
				</span>
				{#if a.status === 'pending'}
					{#if a.relationship_type !== 'owner' && !a.owner_confirmed_at}
						<form class="d-form" method="post" action="?/owner" use:enhance={submit}>
							<input type="hidden" name="id" value={a.id} />
							<label class="sr" for="on{a.id}">Owner name</label>
							<input id="on{a.id}" type="text" name="owner_name" placeholder="Owner's name" required />
							<label class="sr" for="op{a.id}">Owner phone (found by Afe)</label>
							<input id="op{a.id}" type="tel" name="owner_phone" placeholder="Owner's phone, found by Afe" required />
							<button class="btn secondary sm" type="submit" disabled={busy}>Owner confirmed by phone</button>
						</form>
					{/if}
					<form class="d-form" method="post" action="?/authority" use:enhance={submit}>
						<input type="hidden" name="id" value={a.id} />
						<label class="sr" for="an{a.id}">Note</label>
						<input id="an{a.id}" type="text" name="note" placeholder="Note for the landlord (optional)" />
						<button class="btn go sm" name="accept" value="true" type="submit" disabled={busy}>Accept</button>
						<button class="btn danger-line sm" name="accept" value="false" type="submit" disabled={busy}>Reject</button>
					</form>
				{/if}
			</div>
		{:else}
			<div class="d-row small muted">None uploaded.</div>
		{/each}
	</section>

	<RevokePanel current={h.current} codes={data.codes} error={form?.form === 'revoke' ? form.error : null} who="this home" />
	<DecisionForm codes={data.codes} error={form?.form === 'decide' ? form.error : null} {preset} />
	<VerificationHistory history={h.history} />
</div>

<style>
	.home-case {
		gap: 18px;
	}
	.c-top {
		display: flex;
		justify-content: space-between;
		gap: 12px;
		flex-wrap: wrap;
		align-items: flex-start;
	}
	.c-titles {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
	.c-titles h1 {
		margin: 0;
		font-size: 28px;
		line-height: 1.15;
	}
	.c-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr));
		gap: 16px;
		align-items: start;
	}
	.c-side {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}
	.c-row {
		display: flex;
		gap: 10px;
		align-items: center;
		flex-wrap: wrap;
		padding: 10px 16px;
		border-bottom: 1px solid var(--hair);
		font-size: 14.5px;
	}
	.pad {
		padding: 0 16px 16px;
	}
	.f-row,
	.d-row {
		display: flex;
		flex-direction: column;
		gap: 6px;
		padding: 12px 16px;
		border-bottom: 1px solid var(--hair);
		font-size: 14.5px;
	}
	.f-row:last-child,
	.d-row:last-child {
		border-bottom: 0;
	}
	.f-row b {
		font-weight: 600;
	}
	.d-form {
		display: flex;
		gap: 8px;
		flex-wrap: wrap;
		align-items: center;
	}
	.d-form input:not([type='hidden']) {
		flex: 1 1 180px;
		height: 40px;
		font-size: 14.5px;
	}
</style>
