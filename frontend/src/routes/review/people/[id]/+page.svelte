<script lang="ts">
	// One person on the review desk, as a canvas case: who, the Ghana Card check as check rows beside
	// rule flags and model scores, the account graph, then the decision panel (and suspension for admins).
	import { enhance } from '$app/forms';
	import DecisionForm from '$lib/components/DecisionForm.svelte';
	import FormError from '$lib/components/FormError.svelte';
	import ModelNotes from '$lib/components/ModelNotes.svelte';
	import PersonGraph from '$lib/components/PersonGraph.svelte';
	import ReviewModeration from '$lib/components/ReviewModeration.svelte';
	import RevokePanel from '$lib/components/RevokePanel.svelte';
	import VerificationHistory from '$lib/components/VerificationHistory.svelte';
	import { date, dateTime, initials } from '$lib/format';
	import Done from '$lib/components/Done.svelte';

	let { data, form } = $props();
	const p = $derived(data.person);
	const id = $derived(p.identity);
	let busy = $state(false);
</script>

<svelte:head><title>{p.user.name} · Review · Afe</title></svelte:head>

<div class="page-1180 person-case">
	<a class="back" href="/review">← Review queue</a>

	<div class="c-top">
		<span class="avatar lg">{initials(p.user.name)}</span>
		<div class="c-titles">
			<span class="mono small muted">{p.user.role_label} · {p.user.phone ?? 'no phone'}</span>
			<h1>{p.user.name}</h1>
		</div>
		<span class="row">
			<span class="ktag">Identity</span>
			{#if p.current}<span class="pill ok">Verified until {date(p.current.expires_at)}</span>{/if}
			{#if !p.user.is_active}<span class="pill bad">Suspended</span>{/if}
		</span>
	</div>
	{#if !p.user.is_active}<div class="notice error"><b>Suspended.</b><span>They can't sign in, and no money is released to them.</span></div>{/if}
	{#if form?.error && !['decide', 'revoke', 'review'].includes(form?.form ?? '')}<FormError message={form.error} />{/if}
	<Done message={form?.done} key={form} />

	<div class="c-grid">
		<div class="c-side">
		<section class="case" aria-labelledby="id-h">
			<div class="case-head"><b id="id-h">Ghana Card check</b><span class="mono">{id ? `${id.provider} · ${dateTime(id.created_at)}` : 'Not done'}</span></div>
			{#if id}
				<div class="c-row"><span class="tick {id.status === 'passed' ? '' : 'no'}">{id.status === 'passed' ? '✓' : '✕'}</span><span>Card <span class="mono">{id.masked_card}</span> {id.status}{id.failure_reason ? ` · ${id.failure_reason}` : ''}</span></div>
				<div class="c-row"><span class="tick {id.name_matches ? '' : 'no'}">{id.name_matches ? '✓' : '✕'}</span><span>Name on card: {id.name_on_card || '—'}{id.name_matches ? ' (matches)' : ''}</span></div>
				<div class="c-row"><span class="tick {id.liveness_passed ? '' : 'none'}">{id.liveness_passed ? '✓' : '–'}</span><span>Selfie liveness {id.liveness_passed ? 'passed' : 'not done'}</span></div>
			{:else}
				<div class="c-row muted small">No check on file.</div>
			{/if}
		</section>
		<RevokePanel current={p.current} codes={data.codes} error={form?.form === 'revoke' ? form.error : null} who={p.user.name} />
		</div>

		<div class="c-side">
			<section class="case" aria-labelledby="fl-h">
				<div class="case-head"><b id="fl-h">Rule flags</b></div>
				{#each p.flags as f (f.id)}
					<div class="f-row"><span class="row"><span class="sevtag {f.severity}">{f.severity}</span><b>{f.rule}</b></span><span class="small muted">{f.explanation}</span></div>
				{:else}
					<div class="f-row small muted">No rule hits.</div>
				{/each}
			</section>
			<ReviewModeration reviews={p.reviews ?? []} error={form?.form === 'review' ? form.error : null} />
			<ModelNotes notes={p.model_notes} links={p.links} />
		</div>
	</div>

	<PersonGraph graph={data.graph} />
	<DecisionForm codes={data.codes} error={form?.form === 'decide' ? form.error : null} preset={id?.status === 'passed' ? ['ID_MATCH'] : []} />
	<VerificationHistory history={p.history} />

	{#if data.me?.user.role === 'admin'}
		<form
			class="case"
			method="POST"
			action="?/suspend"
			use:enhance={() => {
				busy = true;
				return async ({ update }) => {
					await update();
					busy = false;
				};
			}}
		>
			<div class="case-head"><b>{p.user.is_active ? 'Suspend account' : 'Restore account'}</b><span class="label-mono">Admin</span></div>
			<div class="case-body">
				{#if p.user.is_active}
					<p class="small">For a suspected account takeover or scam. They're signed out, can't sign in, and no money is released to them until you restore the account.</p>
					<div><label for="suspend-reason">Why</label><textarea id="suspend-reason" name="reason" rows="2" required minlength="10"></textarea></div>
					<input type="hidden" name="active" value="false" />
					<div><button class="btn danger md" type="submit" disabled={busy}>Suspend</button></div>
				{:else}
					<input type="hidden" name="active" value="true" />
					<div><button class="btn md" type="submit" disabled={busy}>Restore</button></div>
				{/if}
			</div>
		</form>
	{/if}
</div>

<style>
	.person-case {
		gap: 18px;
	}
	.c-top {
		display: flex;
		gap: 14px;
		flex-wrap: wrap;
		align-items: center;
	}
	.c-titles {
		flex: 1 1 220px;
		display: flex;
		flex-direction: column;
		gap: 2px;
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
		padding: 10px 16px;
		border-bottom: 1px solid var(--hair);
		font-size: 14.5px;
	}
	.c-row:last-child {
		border-bottom: 0;
	}
	.f-row {
		display: flex;
		flex-direction: column;
		gap: 6px;
		padding: 12px 16px;
		border-bottom: 1px solid var(--hair);
		font-size: 14.5px;
	}
	.f-row:last-child {
		border-bottom: 0;
	}
	.f-row b {
		font-weight: 600;
	}
</style>
