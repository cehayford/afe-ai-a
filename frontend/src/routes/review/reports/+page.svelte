<script lang="ts">
	// Scam reports as review cases: what happened, what it matches on Afe, and a decision footer.
	import { enhance } from '$app/forms';
	import FormError from '$lib/components/FormError.svelte';
	import { ago, cedis, dateTime, ghs } from '$lib/format';
	import Done from '$lib/components/Done.svelte';

	let { data, form } = $props();
	let busy = $state(false);
	const submit = () => {
		busy = true;
		return async ({ update }: { update: () => Promise<void> }) => {
			await update();
			busy = false;
		};
	};
</script>

<svelte:head><title>Scam reports · Afe review</title></svelte:head>

<div class="page-head">
	<div class="row spread"><h1>Scam reports</h1><span class="muted small">{data.reports.length} waiting</span></div>
	<p>
		Reports from "Check before you pay". An upheld report on an Afe account or listing flags it for the trust team and becomes a
		fraud example for the models. It never removes anyone on its own.
	</p>
</div>
<FormError message={form?.error} />
<Done message={form?.done} key={form} />

<div class="case-list page-1000" style="margin: 0">
	{#each data.reports as r (r.id)}
		<div class="case">
			<div class="case-head">
				<span class="row"><span class="ktag flag">Report</span><span class="mono">#{r.id} · {r.channel}</span></span>
				<span class="mono" title={dateTime(r.created_at)}>{ago(r.created_at)}</span>
			</div>
			<div class="case-body">
				<p style="white-space: pre-line">{r.what_happened}</p>
				{#if r.amount_lost_pesewas}<span class="row"><span class="sevtag high">Money lost</span><b>{cedis(ghs(r.amount_lost_pesewas))}</b></span>{/if}
			</div>
			{#if r.reported_phone || r.reported_reference}
				<div class="match">
					{#if r.reported_phone}
						<div class="m-row">
							<span class="tick {r.matched_user_id ? 'no' : 'none'}">{r.matched_user_id ? '!' : '–'}</span>
							<span class="m-body">
								<span class="mono small">{r.reported_phone}</span>
								{#if r.matched_user_id}<a href="/review/people/{r.matched_user_id}">{r.matched_user_name} on Afe</a>{:else}<span class="small muted">Not an Afe account</span>{/if}
							</span>
						</div>
					{/if}
					{#if r.reported_reference}
						<div class="m-row">
							<span class="tick {r.matched_listing_title ? 'no' : 'none'}">{r.matched_listing_title ? '!' : '–'}</span>
							<span class="m-body">
								<span class="mono small">{r.reported_reference}</span>
								<span class="small {r.matched_listing_title ? '' : 'muted'}">{r.matched_listing_title || 'Not an Afe listing'}</span>
							</span>
						</div>
					{/if}
				</div>
			{/if}
			<form class="case-foot" method="post" use:enhance={submit}>
				<input type="hidden" name="id" value={r.id} />
				<label for="note-{r.id}" style="margin: 0">What you checked</label>
				<input id="note-{r.id}" name="note" required minlength="10" maxlength="300" />
				<div class="row">
					<button class="btn danger md" type="submit" name="upheld" value="true" disabled={busy}>Uphold</button>
					<button class="btn secondary md" type="submit" name="upheld" value="false" disabled={busy}>Not upheld</button>
				</div>
				<span class="note">Every decision is saved to the audit log with your name.</span>
			</form>
		</div>
	{:else}
		<div class="empty">No reports waiting.</div>
	{/each}
</div>

<style>
	.match {
		border-top: 1px solid var(--hair);
		display: flex;
		flex-direction: column;
	}
	.m-row {
		display: flex;
		gap: 10px;
		align-items: center;
		padding: 10px 16px;
		border-bottom: 1px solid var(--hair);
		font-size: 14.5px;
	}
	.m-row:last-child {
		border-bottom: 0;
	}
	.m-body {
		display: flex;
		flex-wrap: wrap;
		gap: 4px 10px;
		align-items: baseline;
	}
</style>
