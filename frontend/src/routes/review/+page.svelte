<script lang="ts">
	// The review desk from the Admin Review canvas: the queue on the left (filter pills, one row per
	// item, the open one marked in amber), the item on the right with the verifier's report, rule flags,
	// the model's score (advisory only) and the decision.
	import { enhance } from '$app/forms';
	import { page } from '$app/state';
	import FormError from '$lib/components/FormError.svelte';
	import { bedrooms, cedis, date, dateTime, day, today } from '$lib/format';
	import { hydrated } from '$lib/hydrated.svelte';
	const js = hydrated();

	let { data, form } = $props();
	const q = $derived(data.queue);

	type Kind = 'Verification' | 'Identity' | 'Listing' | 'Flag' | 'Visit' | 'Fee' | 'Assigned';
	type Item = { key: string; kind: Kind; title: string; sub: string; at: string | null };
	const items = $derived<Item[]>([
		...q.homes_to_decide.map((h) => ({ key: `home:${h.id}`, kind: 'Verification' as Kind, title: `${h.address}, ${h.area}`, sub: `${h.landlord} · visit ${dateTime(h.last_visit)}`, at: h.last_visit })),
		...q.people.map((p) => ({ key: `person:${p.id}`, kind: 'Identity' as Kind, title: p.name, sub: `${p.role} · Ghana Card check ${dateTime(p.last_check)}`, at: p.last_check })),
		...q.flags.map((f) => ({ key: `flag:${f.id}`, kind: 'Flag' as Kind, title: f.rule.replaceAll('.', ' · ').replaceAll('_', ' '), sub: f.explanation, at: f.created_at })),
		...q.listings.map((l) => ({ key: `listing:${l.listing.id}`, kind: 'Listing' as Kind, title: l.listing.title, sub: `${l.listing.reference} · ${l.lister}${l.blockers.length ? ' · blocked' : ''}`, at: l.listing.published_at })),
		...q.homes_to_visit.map((h) => ({ key: `visit:${h.id}`, kind: 'Visit' as Kind, title: `${h.address}, ${h.area}`, sub: `${h.landlord} · needs a verifier`, at: null })),
		...q.homes_awaiting_fee.map((h) => ({ key: `fee:${h.id}`, kind: 'Fee' as Kind, title: `${h.address}, ${h.area}`, sub: `${h.landlord} · fee not paid`, at: null })),
		...q.assignments.map((a) => ({ key: `assigned:${a.id}`, kind: 'Assigned' as Kind, title: `${a.unit.digital_address} · ${a.unit.unit_label}`, sub: `${a.verifier_name} · ${day(a.scheduled_for)}${a.purpose === 'qa_recheck' ? ' · re-check' : ''}`, at: null }))
	]);
	const FILTERS: [string, string, Kind[]][] = [
		['all', 'All', []],
		['verification', 'Verification', ['Verification', 'Identity']],
		['flags', 'Flags', ['Flag']],
		['listings', 'Listings', ['Listing']],
		['visits', 'Visits', ['Visit', 'Fee', 'Assigned']]
	];
	const kinds = $derived(FILTERS.find(([k]) => k === data.filter)?.[2] ?? []);
	const shown = $derived(kinds.length ? items.filter((i) => kinds.includes(i.kind)) : items);
	const open = $derived(items.filter((i) => !['Assigned'].includes(i.kind)).length);
	const sel = $derived(items.find((i) => i.key === data.item));
	const [selKind, selId] = $derived(data.item.split(':'));
	const link = (key: string) => `?filter=${data.filter}&item=${encodeURIComponent(key)}`;
	const TONE: Record<Kind, string> = { Verification: 'k-ver', Identity: 'k-ver', Listing: 'k-ok', Flag: 'k-flag', Visit: 'k-warn', Fee: 'k-warn', Assigned: 'k-quiet' };
	function age(iso: string | null) {
		if (!iso) return '';
		const m = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
		return m < 60 ? `${Math.max(m, 1)} min` : m < 1440 ? `${Math.round(m / 60)} h` : `${Math.round(m / 1440)} d`;
	}

	// Decision: evidence ticked up front where the record shows it; a reason is required to reject.
	const approvals = $derived(data.codes.filter((c) => c.approval));
	const rejections = $derived(data.codes.filter((c) => !c.approval));
	const preset = $derived.by(() => {
		const out = new Set<string>();
		if (data.person?.identity?.status === 'passed') out.add('ID_MATCH');
		if (data.home?.authorities.some((a) => a.status === 'accepted')) out.add('DOCS_SIGHTED');
		if (data.home?.authorities.some((a) => a.owner_confirmed_at)) out.add('OWNER_CONFIRMED');
		if (data.home?.visit?.outcome === 'passed') out.add('VISIT_MATCH');
		if (data.home?.visit?.checklist?.ghana_card_seen_in_person) out.add('ID_SEEN_IN_PERSON');
		return out;
	});
	let reason = $state('');
	let second = $state(false);
	let busy = $state(false);
	$effect(() => {
		void data.item;
		reason = '';
		second = false;
	});
	const submit = () => {
		busy = true;
		return async ({ update }: { update: () => Promise<void> }) => {
			await update();
			busy = false;
		};
	};
	const note = $derived((data.home ?? data.person)?.model_notes.slice().sort((a, b) => b.score - a.score)[0]);
	const flags = $derived((data.home ?? data.person)?.flags ?? []);
	const done = $derived(form?.done ?? page.url.searchParams.get('done'));
</script>

<svelte:head><title>Review desk · Afe</title></svelte:head>

<div class="desk-split">
	<aside class="queue">
		<div class="q-head">
			<div class="row-b"><h1>Queue</h1><span>{open} open</span></div>
			<nav class="pills" aria-label="Filter the queue">
				{#each FILTERS as [k, label]}<a href="?filter={k}" aria-current={data.filter === k ? 'page' : undefined}>{label}</a>{/each}
			</nav>
		</div>
		<div class="q-list">
			{#each shown as i (i.key)}
				<a class="q-row" class:sel={i.key === data.item} href={link(i.key)} aria-current={i.key === data.item ? 'true' : undefined}>
					<div class="row-b"><span class="kind {TONE[i.kind]}">{i.kind}</span><span class="age">{age(i.at)}</span></div>
					<span class="t">{i.title}</span>
					<span class="s">{i.sub}</span>
				</a>
			{:else}
				<p class="q-empty">Nothing waiting here.</p>
			{/each}
		</div>
		<nav class="tools" aria-label="Review tools">
			<a href="/review/insights">Targets</a><a href="/review/workload">Workload</a><a href="/review/visit-plan">Visit plan</a><a href="/review/label-checks">Label checks</a>
		</nav>
	</aside>

	<section class="item">
		{#if done}<p class="result">{done}</p>{/if}
		<FormError message={form?.error} />
		{#if !sel}
			<div class="empty">The queue is clear. New verifications, flags and listings appear here as they arrive.</div>
		{:else}
			<div class="i-head">
				<div class="titles">
					<span class="ref">{selKind.toUpperCase()}-{selId}{data.home ? ` · ${data.home.unit.digital_address}` : ''}</span>
					<h2>{sel.title}</h2>
					<span class="sub">{sel.sub}</span>
				</div>
				<span class="kind {TONE[sel.kind]}">{sel.kind}</span>
			</div>

			{#if data.home && (selKind === 'home' || selKind === 'visit' || selKind === 'fee')}
				{@const h = data.home}
				<div class="cards">
					<div class="rcard">
						<div class="c-head"><span>Verifier report</span><span class="mono">{h.visit ? `${h.visit.verifier_name} · ${dateTime(h.visit.started_at)}` : 'Visit not yet done'}</span></div>
						{#if h.visit}
							<div class="c-line"><span class="dot ok">✓</span><span>GPS check-in within {Math.round(h.visit.checkin_distance_m)} m</span></div>
							{#each Object.entries(h.visit.checklist_items) as [key, label]}
								{@const v = h.visit.checklist[key]}
								<div class="c-line"><span class="dot {v ? 'ok' : v === false ? 'no' : ''}">{v ? '✓' : v === false ? '✕' : '–'}</span><span>{label}</span></div>
							{/each}
							{#if h.visit.notes}<div class="c-line note-line">{h.visit.notes}</div>{/if}
							<div class="thumbs4">
								{#each h.visit.photos as p (p.id)}
									<figure class:dup={p.duplicate_of_id}><img src={p.url} alt={p.caption} loading="lazy" /><figcaption>{p.caption}{p.duplicate_of_id ? ' · reused' : ''}</figcaption></figure>
								{/each}
							</div>
						{:else}
							<div class="c-line muted">{bedrooms(h.unit.bedrooms)} · {h.unit.property_type_label} · registered by {h.registered_by.name}. Fee {h.fee_settled ? 'settled' : 'not paid'}.{h.open_assignment ? ` Visit assigned to ${h.open_assignment.verifier_name} for ${day(h.open_assignment.scheduled_for)}.` : ''}</div>
						{/if}
					</div>

					<div class="col">
						{@render flagCard()}
						{@render scoreCard()}
						<div class="rcard">
							<div class="c-head"><span>Documents</span></div>
							{#each h.authorities as a (a.id)}
								<div class="c-line docrow">
									<div style="flex: 1">
										<div>{a.document_label} · {a.relationship_label}</div>
										<a class="small" href="/review/documents/{a.id}" target="_blank" rel="noopener">Open document (logged)</a>
										{#if a.owner_confirmed_at}<span class="small muted"> · owner {a.owner_name} confirmed {date(a.owner_confirmed_at)}</span>{/if}
									</div>
									{#if a.status === 'pending'}
										<form class="row" method="post" action="?/authority" use:enhance={submit}>
											<input type="hidden" name="id" value={a.id} />
											<button class="btn go small" name="accept" value="true" type="submit">Accept</button>
											<button class="btn quiet small" name="accept" value="false" type="submit">Reject</button>
										</form>
									{:else}
										<span class="pill {a.status === 'accepted' ? 'ok' : 'bad'}">{a.status}</span>
									{/if}
								</div>
								{#if a.status === 'pending' && a.relationship_type !== 'owner' && !a.owner_confirmed_at}
									<form class="c-line assign" method="post" action="?/owner" use:enhance={submit}>
										<input type="hidden" name="id" value={a.id} />
										<input type="text" name="owner_name" placeholder="Owner's name" required aria-label="Owner's name" />
										<input type="tel" name="owner_phone" placeholder="Owner's phone, found by Afe" required aria-label="Owner's phone" />
										<button class="btn secondary small" type="submit">Owner confirmed by phone</button>
									</form>
								{/if}
							{:else}
								<div class="c-line muted">None uploaded.</div>
							{/each}
						</div>
					</div>
				</div>
				{#if selKind === 'home'}
					{@render decision()}
				{:else if selKind === 'visit'}
					{@render assignForm(h.unit.id, '')}
				{:else}
					<form class="rcard pad stack" method="post" action="?/waive" use:enhance={submit}>
						<span class="c-title">Waive the verification fee</span>
						<input type="hidden" name="unit_id" value={h.unit.id} />
						<input type="text" name="note" placeholder="Why, e.g. founding landlord" required minlength="3" aria-label="Reason" style="max-width: 520px" />
						<div><button class="btn md" type="submit" disabled={busy}>Waive fee</button></div>
					</form>
				{/if}
				<a class="small" href="/review/homes/{h.unit.id}">Open the full record →</a>
			{:else if data.person && selKind === 'person'}
				{@const p = data.person}
				<div class="cards">
					<div class="rcard">
						<div class="c-head"><span>Ghana Card check</span><span class="mono">{p.identity ? `${p.identity.provider} · ${dateTime(p.identity.created_at)}` : 'No check yet'}</span></div>
						{#if p.identity}
							<div class="c-line"><span class="dot {p.identity.status === 'passed' ? 'ok' : 'no'}">{p.identity.status === 'passed' ? '✓' : '✕'}</span><span>Check {p.identity.status} · {p.identity.masked_card}</span></div>
							<div class="c-line"><span class="dot {p.identity.name_matches ? 'ok' : 'no'}">{p.identity.name_matches ? '✓' : '✕'}</span><span>Name on card: {p.identity.name_on_card}</span></div>
							<div class="c-line"><span class="dot {p.identity.liveness_passed ? 'ok' : 'no'}">{p.identity.liveness_passed ? '✓' : '✕'}</span><span>Live selfie matches the card</span></div>
							{#if p.identity.failure_reason}<div class="c-line note-line">{p.identity.failure_reason}</div>{/if}
						{/if}
						<div class="c-line muted">{p.user.role_label} · {p.user.phone ?? 'no phone'}{p.links.length ? ` · ${p.links.length} linked account${p.links.length === 1 ? '' : 's'}` : ''}</div>
					</div>
					<div class="col">
						{@render flagCard()}
						{@render scoreCard()}
					</div>
				</div>
				{@render decision()}
				<a class="small" href="/review/people/{p.user.id}">Open the full profile and account links →</a>
			{:else if selKind === 'listing'}
				{@const l = q.listings.find((x) => String(x.listing.id) === selId)}
				{#if l}
					<div class="rcard pad stack">
						<div class="row spread"><span class="c-title">{l.listing.title}</span><span class="num">{cedis(l.listing.rent_display)} / month</span></div>
						<span class="muted small">{l.listing.reference} · {bedrooms(l.listing.bedrooms)} · {l.listing.area} · listed by {l.lister}</span>
						{#if l.blockers.length}
							<ul class="blockers">{#each l.blockers as b}<li>{b}</li>{/each}</ul>
						{:else}
							<form method="post" action="?/publish" use:enhance={submit}><input type="hidden" name="id" value={l.listing.id} /><button class="btn go md" type="submit" disabled={busy}>Publish</button></form>
						{/if}
						<a class="small" href="/homes/{l.listing.reference}" target="_blank" rel="noopener">Preview the listing →</a>
					</div>
				{/if}
			{:else if selKind === 'flag'}
				{@const f = q.flags.find((x) => String(x.id) === selId)}
				{#if f}
					<div class="rcard">
						<div class="c-head"><span>Rule flag</span><span class="mono">{f.subject_type} #{f.subject_id} · {dateTime(f.created_at)}</span></div>
						<div class="c-line flag-line"><span class="sev sev-{f.severity}">{f.severity}</span><b>{f.rule}</b></div>
						<div class="c-line">{f.explanation}</div>
					</div>
					<form class="rcard pad stack" method="post" action="?/resolve" use:enhance={submit}>
						<span class="c-title">Decision</span>
						<input type="hidden" name="id" value={f.id} />
						<input type="text" name="note" placeholder="What you checked" aria-label="Note" style="max-width: 520px" />
						<div class="row">
							<button class="btn quiet md" name="outcome" value="dismiss" type="submit" disabled={busy}>Not fraud</button>
							<button class="btn danger md" name="outcome" value="confirm" type="submit" disabled={busy}>Confirm fraud</button>
						</div>
						<span class="small muted">Every decision is saved to the audit log with your name.</span>
					</form>
				{/if}
			{:else if selKind === 'assigned'}
				{@const a = q.assignments.find((x) => String(x.id) === selId)}
				{#if a}
					<div class="rcard pad stack">
						<span class="c-title">{a.unit.digital_address} · {a.unit.unit_label}</span>
						<span class="muted small">{a.verifier_name} · {day(a.scheduled_for)} · {a.purpose === 'qa_recheck' ? 'Quality re-check' : 'Verification visit'}{a.note ? ` · ${a.note}` : ''}</span>
						<form method="post" action="?/cancel" use:enhance={submit}><input type="hidden" name="id" value={a.id} /><button class="btn quiet md" type="submit" disabled={busy}>Cancel visit</button></form>
					</div>
				{/if}
			{/if}
		{/if}
	</section>
</div>

{#snippet flagCard()}
	<div class="rcard">
		<div class="c-head"><span>Rule flags</span></div>
		{#each flags as f (f.id)}
			<div class="c-line col-line">
				<div class="flag-line"><span class="sev sev-{f.severity}">{f.severity}</span><b>{f.rule}</b></div>
				<span class="small muted">{f.explanation}</span>
			</div>
		{:else}
			<div class="c-line muted">No rule hits.</div>
		{/each}
	</div>
{/snippet}

{#snippet scoreCard()}
	<div class="score">
		<div class="row-b"><b>Model score</b><span class="tag-pill">{note ? `${note.mode === 'shadow' ? 'Shadow' : note.mode} · advisory` : 'Not scored'}</span></div>
		{#if note}
			<div class="bar-row">
				<div class="bar"><div class="fill" style:width="{note.score}%" class:hi={note.score >= note.threshold} class:mid={note.score >= note.threshold / 2 && note.score < note.threshold}></div></div>
				<span class="mono">{(note.score / 100).toFixed(2)}</span>
			</div>
			<span class="small muted">{note.label}{note.reasons.length ? `: ${note.reasons.join('; ')}` : ''}</span>
		{/if}
		<span class="small muted">Logged with your decision for training. It does not approve or reject anything.</span>
	</div>
{/snippet}

{#snippet assignForm(unitId: number, noteText: string)}
	<form class="rcard pad stack" method="post" action="?/assign" use:enhance={submit}>
		<span class="c-title">{noteText ? 'Send for a second check' : 'Send a verifier'}</span>
		<input type="hidden" name="unit_id" value={unitId} />
		<input type="hidden" name="note" value={noteText} />
		{#if data.verifiers.length}
			<div class="assign assign-row">
				<select name="verifier_id" aria-label="Verifier">{#each data.verifiers as v}<option value={v.id}>{v.name}</option>{/each}</select>
				<input type="date" name="scheduled_for" value={today()} min={today()} required aria-label="Date" />
				<button class="btn md" type="submit" disabled={busy}>Assign</button>
			</div>
		{:else}
			<span class="muted small">No field verifiers yet.</span>
		{/if}
	</form>
{/snippet}

{#snippet decision()}
	<form class="rcard pad stack" method="post" action="?/decide" use:enhance={submit}>
		<span class="c-title">Decision</span>
		<input type="hidden" name="item" value={data.item} />
		<fieldset class="evidence">
			<legend class="small muted">Evidence you checked (to approve)</legend>
			<div class="chips">
				{#each approvals as c (c.code)}<label class="chip small-chip"><input type="checkbox" name="codes" value={c.code} checked={preset.has(c.code)} />{c.label}</label>{/each}
			</div>
		</fieldset>
		<select name="reason" bind:value={reason} aria-label="Reason code" style="max-width: 520px; height: 44px; font-size: 15px">
			<option value="">Reason code (required to reject)</option>
			{#each rejections as c (c.code)}<option value={c.code}>{c.code} · {c.label}</option>{/each}
		</select>
		<input type="text" name="note" maxlength="300" placeholder="Note (optional)" aria-label="Note" style="max-width: 520px; height: 44px; font-size: 15px" />
		<div class="row">
			<button class="btn go md" name="decision" value="approve" type="submit" disabled={busy}>Approve</button>
			<button class="btn danger md" name="decision" value="reject" type="submit" disabled={(js.on && !reason) || busy}>Reject</button>
			{#if data.home}<button class="btn quiet md" type="button" onclick={() => (second = !second)} aria-expanded={second}>Send for second check</button>{/if}
		</div>
		<span class="small muted">Every decision is saved to the audit log with your name and the reason code.</span>
	</form>
	{#if second && data.home}{@render assignForm(data.home.unit.id, 'Second check requested by the review desk')}{/if}
{/snippet}

<style>
	.desk-split {
		display: flex;
		flex-wrap: wrap;
		align-items: stretch;
		min-height: calc(100vh - 68px);
	}
	.queue {
		flex: 1 1 320px;
		max-width: 100%;
		border-right: 1px solid var(--line);
		background: var(--surface);
		display: flex;
		flex-direction: column;
	}
	.q-head {
		padding: 16px;
		display: flex;
		flex-direction: column;
		gap: 12px;
		border-bottom: 1px solid var(--line);
	}
	.row-b {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 8px;
	}
	.q-head h1 {
		margin: 0;
		font-size: 22px;
	}
	.q-head .row-b span {
		font-size: 13px;
		color: var(--muted);
	}
	.q-list {
		display: flex;
		flex-direction: column;
	}
	.q-row {
		text-align: left;
		padding: 14px 16px;
		border-bottom: 1px solid var(--hair);
		border-left: 4px solid transparent;
		background: var(--surface);
		display: flex;
		flex-direction: column;
		gap: 4px;
		color: var(--ink);
	}
	.q-row:hover {
		background: var(--paper);
		color: var(--ink);
	}
	.q-row.sel {
		border-left-color: var(--amber);
		background: var(--paper);
	}
	.q-row .row-b {
		align-items: center;
	}
	.q-row .t {
		font-weight: 600;
		font-size: 15px;
	}
	.q-row .s {
		font-size: 13px;
		color: var(--muted);
		overflow: hidden;
		text-overflow: ellipsis;
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
	}
	.age {
		font: 11.5px var(--font-mono);
		color: var(--muted);
	}
	.q-empty {
		padding: 16px;
		color: var(--muted);
		font-size: 14px;
	}
	.tools {
		margin-top: auto;
		padding: 14px 16px;
		display: flex;
		flex-wrap: wrap;
		gap: 6px 14px;
		font-size: 13px;
		border-top: 1px solid var(--line);
	}
	.kind {
		font: 11px var(--font-mono);
		padding: 3px 8px;
		border-radius: 4px;
		white-space: nowrap;
		align-self: flex-start;
	}
	.k-ver {
		background: var(--tint);
		color: var(--brand);
	}
	@media (prefers-color-scheme: dark) {
		.k-ver {
			color: var(--accent);
		}
	}
	.k-flag {
		background: var(--crit-soft);
		color: var(--crit);
	}
	.k-warn {
		background: var(--warn-soft);
		color: var(--warn);
	}
	.k-ok {
		background: var(--ok-soft);
		color: var(--ok);
	}
	.k-quiet {
		background: var(--tint);
		color: var(--muted);
	}
	.item {
		flex: 999 1 560px;
		min-width: 0;
		padding: 24px;
		display: flex;
		flex-direction: column;
		gap: 18px;
	}
	.item .result {
		margin: 0;
	}
	.i-head {
		display: flex;
		justify-content: space-between;
		gap: 12px;
		flex-wrap: wrap;
		align-items: flex-start;
	}
	.titles {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
	.ref {
		font: 12px var(--font-mono);
		color: var(--muted);
	}
	.titles h2 {
		margin: 0;
		font-size: 28px;
		line-height: 1.15;
	}
	.sub {
		font-size: 14.5px;
		color: var(--muted);
	}
	.cards {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr));
		gap: 16px;
		align-items: start;
	}
	.col {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}
	.rcard {
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: 12px;
	}
	.rcard.pad {
		padding: 16px;
	}
	.c-head {
		padding: 12px 16px;
		border-bottom: 1px solid var(--line);
		display: flex;
		justify-content: space-between;
		gap: 8px;
		flex-wrap: wrap;
		font-weight: 600;
	}
	.c-head .mono {
		font: 12px var(--font-mono);
		color: var(--muted);
		font-weight: 400;
	}
	.c-title {
		font-weight: 600;
	}
	.c-line {
		display: flex;
		gap: 10px;
		align-items: center;
		padding: 10px 16px;
		border-bottom: 1px solid var(--hair);
		font-size: 14.5px;
	}
	.c-line:last-child {
		border-bottom: 0;
	}
	.col-line {
		flex-direction: column;
		align-items: flex-start;
		gap: 4px;
	}
	.note-line {
		font-size: 13.5px;
		color: var(--muted);
	}
	.docrow {
		flex-wrap: wrap;
	}
	.dot {
		width: 22px;
		height: 22px;
		flex: 0 0 auto;
		border-radius: 99px;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 12px;
		font-weight: 700;
		background: var(--tint);
		color: var(--muted);
	}
	.dot.ok {
		background: var(--ok-soft);
		color: var(--ok);
	}
	.dot.no {
		background: var(--crit-soft);
		color: var(--crit);
	}
	.thumbs4 {
		padding: 12px 16px;
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 6px;
	}
	.thumbs4 figure {
		margin: 0;
		position: relative;
		aspect-ratio: 1;
		border-radius: 6px;
		overflow: hidden;
		background: var(--stripe);
	}
	.thumbs4 img {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}
	.thumbs4 figcaption {
		position: absolute;
		left: 4px;
		bottom: 4px;
		font: 9px var(--font-mono);
		color: #fff;
		text-shadow: 0 1px 2px rgba(0, 0, 0, 0.7);
	}
	.thumbs4 .dup {
		outline: 2px solid var(--crit);
		outline-offset: -2px;
	}
	.flag-line {
		display: flex;
		gap: 8px;
		align-items: center;
	}
	.sev {
		font: 10.5px var(--font-mono);
		padding: 2px 7px;
		border-radius: 4px;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}
	.sev-high {
		background: var(--crit);
		color: var(--on-crit);
	}
	.sev-medium {
		background: var(--warn-soft);
		color: var(--warn);
	}
	.sev-low {
		background: var(--tint);
		color: var(--muted);
	}
	.score {
		background: var(--tint);
		border-radius: 12px;
		padding: 14px 16px;
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	.tag-pill {
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
	.bar {
		flex: 1;
		height: 8px;
		border-radius: 4px;
		background: var(--line);
		position: relative;
		overflow: hidden;
	}
	.fill {
		position: absolute;
		left: 0;
		top: 0;
		bottom: 0;
		background: var(--ok);
	}
	.fill.mid {
		background: var(--amber);
	}
	.fill.hi {
		background: var(--crit);
	}
	.bar-row .mono {
		font: 500 14px var(--font-mono);
	}
	.evidence {
		border: 0;
		padding: 0;
		margin: 0;
	}
	.evidence legend {
		margin-bottom: 8px;
		padding: 0;
	}
	.small-chip {
		height: 36px;
		font-size: 13.5px;
	}
	.assign-row input[type='date'] {
		width: auto;
	}
</style>
