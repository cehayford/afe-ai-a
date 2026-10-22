<script lang="ts">
	// The canvas's "Model score" card: each model's score as a bar, its mode as a tag (shadow is
	// advisory), the reasons, and any linked accounts.
	import type { AccountLink, ModelNote } from '$lib/api/types';
	import { dateTime } from '$lib/format';

	let { notes, links = null }: { notes: ModelNote[]; links?: AccountLink[] | null } = $props();
	const KIND: Record<string, string> = {
		ghana_card: 'Same Ghana Card',
		payout_account: 'Same payout account',
		photo: 'Same photo',
		phone_in_message: 'Phone number given in a message'
	};
	const band = (n: ModelNote) => (n.score >= n.threshold ? 'hi' : n.score >= n.threshold / 2 ? 'mid' : '');
</script>

<section class="score-card" aria-label="Model notes">
	{#each notes as n (n.detector + n.subject)}
		<div class="m-note">
			<div class="row spread"><b>{n.label}</b><span class="mode">{n.mode === 'shadow' ? 'Shadow · advisory' : n.mode}</span></div>
			<div class="bar-row">
				<span class="meter-bar"><span class={band(n)} style="width: {n.score}%"></span></span>
				<span class="mono sc">{n.score}/100</span>
			</div>
			<span class="small muted">{n.subject}{n.acted ? ' · raised a flag' : ''} · {n.version} · {dateTime(n.created_at)}</span>
			{#if n.reasons.length}<ul class="why">{#each n.reasons as r, i (i)}<li>{r}</li>{/each}</ul>{/if}
		</div>
	{:else}
		<div class="m-note"><b>Model score</b><span class="small muted">No model has scored this yet.</span></div>
	{/each}
	<span class="small muted">Logged with your decision for training. Models in shadow don't approve or reject anything.</span>
</section>

{#if links}
	<section class="case" aria-label="Linked accounts">
		<div class="case-head"><b>Linked accounts</b></div>
		{#each links as l, i (i)}
			<div class="l-row"><a href="/review/people/{l.other_user_id}">{l.other_name}</a><span class="small">{KIND[l.kind] ?? l.kind}</span><span class="mono small muted">{l.evidence}</span></div>
		{:else}
			<div class="l-row small muted">No links to other accounts.</div>
		{/each}
	</section>
{/if}

<style>
	.score-card {
		background: var(--tint);
		border-radius: 12px;
		padding: 14px 16px;
		display: flex;
		flex-direction: column;
		gap: 12px;
	}
	.m-note {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	.m-note b {
		font-weight: 600;
	}
	.mode {
		font: 11px var(--font-mono);
		background: var(--surface);
		color: var(--muted);
		padding: 3px 8px;
		border-radius: 99px;
	}
	.bar-row {
		display: flex;
		align-items: center;
		gap: 10px;
	}
	.sc {
		font-size: 14px;
		font-weight: 500;
	}
	.why {
		margin: 0;
		padding-left: 18px;
		font-size: 13.5px;
	}
	.l-row {
		display: flex;
		flex-wrap: wrap;
		gap: 4px 10px;
		align-items: baseline;
		padding: 10px 16px;
		border-bottom: 1px solid var(--hair);
		font-size: 14.5px;
	}
	.l-row:last-child {
		border-bottom: 0;
	}
</style>
