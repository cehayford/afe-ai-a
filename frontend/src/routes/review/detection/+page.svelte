<script lang="ts">
	// Models: each detector as a review case with its mode, how it compares with the Phase 1 rules
	// (bars like the canvas's model score), and a mode change behind a disclosure.
	import { enhance } from '$app/forms';
	import FormError from '$lib/components/FormError.svelte';
	import type { Tally } from '$lib/api/types';
	import { dateTime } from '$lib/format';
	import Done from '$lib/components/Done.svelte';

	let { data, form } = $props();
	const pct = (v: number | null) => (v === null ? '—' : `${Math.round(v * 100)}%`);
	const TONE: Record<string, string> = { active: 'ok', canary: 'warn', shadow: '', off: 'quiet' };
	const NEXT: Record<string, string> = { shadow: 'canary', canary: 'active' };
	const band = (v: number | null) => (v === null ? '' : v >= 0.8 ? '' : v >= 0.5 ? 'mid' : 'hi');
	let busy = $state(false);
	const submit = () => {
		busy = true;
		return async ({ update }: { update: () => Promise<void> }) => {
			await update();
			busy = false;
		};
	};
</script>

<svelte:head><title>Models · Afe review</title></svelte:head>

<nav class="pills" aria-label="Models">
	<a href="/review/detection" aria-current="page">Models</a><a href="/review/label-checks">Label checks</a><a href="/review/insights">Targets</a>
</nav>
<div class="page-head">
	<h1>Models</h1>
	<p>
		Every model starts in <b>shadow</b>: it scores cases but changes nothing. It can move to <b>canary</b> (acting on one case in ten)
		and then <b>active</b> only when it beats the Phase 1 rules on cases reviewers have decided, and a second reviewer approves. Acting
		means raising a flag for a person. A model never rejects anyone or holds money.
	</p>
</div>
<FormError message={form?.error} />
<Done message={form?.done} key={form} />

{#snippet tally(name: string, t: Tally)}
	<div class="t-row" title="{t.tp} caught, {t.fp} false alarms, {t.fn} missed">
		<span class="t-name">{name}</span>
		<span class="t-bars">
			<span class="t-bar"><span class="label-mono">Precision</span><span class="meter-bar"><span class={band(t.precision)} style="width: {(t.precision ?? 0) * 100}%"></span></span><span class="mono t-v">{pct(t.precision)}</span></span>
			<span class="t-bar"><span class="label-mono">Recall</span><span class="meter-bar"><span class={band(t.recall)} style="width: {(t.recall ?? 0) * 100}%"></span></span><span class="mono t-v">{pct(t.recall)}</span></span>
		</span>
		<span class="small muted">{t.fp} false alarm{t.fp === 1 ? '' : 's'} · {t.fn} missed</span>
	</div>
{/snippet}

<div class="det-grid">
	{#each data.detectors as d (d.name)}
		<div class="case">
			<div class="case-head">
				<span class="t-head"><b>{d.label}</b><span class="mono">{d.name} · {d.version ?? 'no scores yet'}</span></span>
				<span class="ktag {TONE[d.mode] ?? ''}">{d.mode}</span>
			</div>
			<div class="case-body">
				<span class="small muted">
					Flags at {d.threshold}/100 · {d.scores} scored{d.acted ? `, ${d.acted} acted on` : ''}{d.pending ? ` · ${d.pending} waiting` : ''}{d.failed ? ` · ${d.failed} failed` : ''}
				</span>
				<div class="versus">
					<span class="row spread"><span class="c-title">On decided cases</span><span class="mono small muted">{d.evaluation.labels} labelled · {d.evaluation.fraud} fraud</span></span>
					{@render tally('Model', d.evaluation.model)}
					{@render tally('Phase 1 rules', d.evaluation.rules)}
				</div>
				<div class="notice {d.evaluation.promotable ? 'ok' : ''}" style="margin: 0">
					<b>{d.evaluation.promotable ? 'Ready to leave shadow.' : 'Stays in shadow.'}</b><span>{d.evaluation.reason}.</span>
				</div>
			</div>
			<details class="case-foot">
				<summary class="btn quiet sm">Change mode</summary>
				<form class="stack" method="post" action="?/mode" use:enhance={submit} style="margin-top: 12px">
					<input type="hidden" name="name" value={d.name} />
					<div><label for="source-{d.name}">Why <span class="muted" style="font-weight: 400">(the second reviewer sees this)</span></label><input id="source-{d.name}" name="source" required minlength="5" /></div>
					<div class="row">
						{#if NEXT[d.mode]}
							<button class="btn md" type="submit" name="mode" value={NEXT[d.mode]} disabled={busy || !d.evaluation.promotable}>Propose {NEXT[d.mode]}</button>
						{/if}
						{#if d.mode === 'canary' || d.mode === 'active'}
							<button class="btn secondary md" type="submit" name="mode" value="shadow" disabled={busy}>Back to shadow</button>
						{/if}
						{#if d.mode !== 'off'}
							<button class="btn danger-line md" type="submit" name="mode" value="off" disabled={busy}>Turn off</button>
						{:else}
							<button class="btn secondary md" type="submit" name="mode" value="shadow" disabled={busy}>Turn on in shadow</button>
						{/if}
					</div>
				</form>
			</details>
		</div>
	{/each}
</div>

<section class="case" aria-labelledby="hist-h">
	<div class="case-head">
		<b id="hist-h">Weekly reports</b>
		<span class="small muted">Every Monday at 05:00, kept for 12 weeks</span>
	</div>
	{#if data.history.length}
		<div class="scroll">
			<table class="q hist-t">
				<thead>
					<tr><th>Week</th><th>Model</th><th>Decided cases</th><th>Precision</th><th>Recall</th><th>Rules recall</th><th>Seeded recall</th><th>Ready</th></tr>
				</thead>
				<tbody>
					{#each data.history as h (h.week + h.detector)}
						<tr>
							<td class="mono">{h.week}</td>
							<td>{h.detector}</td>
							<td class="mono">{h.labels} · {h.fraud} fraud</td>
							<td class="mono">{pct(h.model.precision)}</td>
							<td class="mono">{pct(h.model.recall)}</td>
							<td class="mono">{pct(h.rules.recall)}</td>
							<td class="mono">{h.seeded ? `${pct(h.seeded.model.recall)} of ${h.seeded.fraud}` : '—'}</td>
							<td>{#if h.promotable}<span class="pill ok">Ready</span>{:else}<span class="small muted">No</span>{/if}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{:else}
		<div class="case-body small muted">No weekly report yet. The first one runs on Monday at 05:00.</div>
	{/if}
</section>

<section class="case" aria-labelledby="cop-h">
	<div class="case-head">
		<b id="cop-h">Reviewer copilot</b>
		{#if data.copilot}<span class="small muted">{data.copilot.level} · last {data.copilot.days} days</span>{/if}
	</div>
	{#if !data.copilot}
		<div class="case-body small muted">The copilot's numbers couldn't be loaded.</div>
	{:else if data.copilot.level === 'off' && !data.copilot.runs}
		<div class="case-body small muted">
			Off. It runs in shadow once counsel clears B11 and two reviewers set the rule agent_copilot_level. Its suggestions stay
			hidden; only these numbers show.
		</div>
	{:else}
		<div class="scroll">
			<table class="q hist-t">
				<thead>
					<tr><th>Homes</th><th>Decided</th><th>Agreed</th><th>False approvals</th><th>Code overlap</th><th>Failed or refused</th><th>Cost</th></tr>
				</thead>
				<tbody>
					<tr>
						<td class="mono">{data.copilot.runs}</td>
						<td class="mono">{data.copilot.decided}</td>
						<td class="mono">{pct(data.copilot.agreement)}</td>
						<td class="mono">{data.copilot.false_approvals}</td>
						<td class="mono">{pct(data.copilot.code_overlap)}</td>
						<td class="mono">{data.copilot.failed + data.copilot.refused}</td>
						<td class="mono">US${data.copilot.cost_usd.toFixed(2)}</td>
					</tr>
				</tbody>
			</table>
		</div>
	{/if}
</section>

<section class="case" aria-labelledby="ver-h">
	<div class="case-head">
		<b id="ver-h">Scam-wording versions</b>
		<form method="post" action="?/train" use:enhance={submit}><button class="btn secondary sm" type="submit" disabled={busy}>Train a new version</button></form>
	</div>
	<div class="case-body small muted">
		Trained from listings and messages reviewers have decided. It needs at least 5 fraud and 5 genuine examples, and it's judged on its own
		results before it can leave shadow.
	</div>
	{#each data.versions as v, i (i)}
		<div class="v-row"><span class="mono">{v.version}</span><span class="v-notes">{v.notes}</span><span class="mono small muted">{dateTime(v.created_at)}</span></div>
	{/each}
</section>

<style>
	.hist-t {
		min-width: 720px;
	}
	.det-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 440px), 1fr));
		gap: 16px;
		align-items: start;
	}
	.t-head {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.c-title {
		font-weight: 600;
	}
	.versus {
		background: var(--tint);
		border-radius: 12px;
		padding: 14px 16px;
		display: flex;
		flex-direction: column;
		gap: 12px;
	}
	.t-row {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	.t-name {
		font-size: 14px;
		font-weight: 600;
	}
	.t-bars {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
		gap: 6px 16px;
	}
	.t-bar {
		display: flex;
		align-items: center;
		gap: 8px;
	}
	.t-bar .label-mono {
		width: 68px;
		flex: none;
	}
	.t-v {
		width: 38px;
		text-align: right;
		font-size: 13px;
	}
	details.case-foot {
		display: block;
	}
	details > summary {
		list-style: none;
		width: fit-content;
	}
	details > summary::-webkit-details-marker {
		display: none;
	}
	details[open] > summary {
		background: var(--tint);
	}
	.v-row {
		display: flex;
		flex-wrap: wrap;
		gap: 4px 12px;
		align-items: baseline;
		padding: 10px 16px;
		border-top: 1px solid var(--hair);
		font-size: 14.5px;
	}
	.v-notes {
		flex: 1 1 200px;
	}
</style>
