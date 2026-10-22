<script lang="ts">
	// Landing page, built from the "Afe Landing Page" canvas: launch-offer bar, green hero with the
	// search tray and a verified-listing ticket, inline scam check, how it works, homes ready to view,
	// protected rent, the landlord panel. Footer comes from the layout.
	import { enhance } from '$app/forms';
	import ListingCard from '$lib/components/ListingCard.svelte';
	import CheckIcon from '$lib/components/ui/CheckIcon.svelte';
	import { cedis, date, shortDate } from '$lib/format';

	let { data, form } = $props();

	const ticket = $derived(data.latest[0]);
	// The scam check answers in place; typing again clears the answer, as in the prototype.
	let q = $state('');
	let typed = $state(false);
	let checking = $state(false);
	const answer = $derived(!typed && form && 'check' in form ? form.check : null);
	// Closing the launch-offer bar hides it at once; the action remembers it in a cookie.
	let offerHidden = $state(false);

	const beds = [
		['', 'Any beds'],
		['1', '1 bed'],
		['2', '2 beds'],
		['3', '3+ beds']
	];
	const steps = [
		['We check the landlord', 'Ghana Card checked with a live selfie, ownership papers sighted, and the owner confirmed by phone.'],
		['We visit the home', 'An Afe verifier goes to the address, confirms it matches the listing and takes the photos you see.'],
		['We hold your rent', 'Pay through Afe and the money waits with us until you confirm you have moved in.']
	];
	const sampleRecord = ["Landlord's Ghana Card checked", 'Ownership papers sighted', 'Owner confirmed by phone', 'Visited by Afe', 'Photos taken by Afe'];
	const flow = [
		['01', 'You pay Afe', 'By mobile money or card, after a completed viewing.'],
		['02', 'We hold it', 'The landlord sees the payment is safe but cannot take it yet.'],
		['03', 'You move in', 'Confirm in the app or on WhatsApp once you have the keys.'],
		['04', 'Landlord is paid', 'Only to a name-matched, verified account.']
	];
</script>

<svelte:head>
	<title>Afe · Verified homes in Accra</title>
	<meta
		name="description"
		content="Every home on Afe is visited in person and its landlord checked. Find a verified home in Accra, and never pay before you view."
	/>
</svelte:head>

{#if data.closed}
	<div class="wrap" style="padding-top: 16px"><p class="result">Your account is closed and you've been signed out everywhere.</p></div>
{/if}

{#if data.pricing?.launch_offer && !data.offerClosed && !offerHidden}
	<div class="offer">
		<div class="offer-in">
			<span class="tag amber">Launch offer</span>
			<span class="offer-text">Verification, protection and featured listings are free until {date(data.pricing.free_until)}.</span>
			<form
				method="post"
				action="?/closeOffer"
				use:enhance={() => {
					offerHidden = true;
					// Nothing on the page depends on the answer, so don't reload it (the scam check keeps its result).
					return async () => {};
				}}
			>
				<button class="offer-close" type="submit" aria-label="Close the launch offer message">
					<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M3.5 3.5l9 9M12.5 3.5l-9 9" /></svg>
				</button>
			</form>
		</div>
	</div>
{/if}

<section class="hero" aria-labelledby="hero-title">
	<div class="hero-in">
		<div class="hero-copy">
			<div class="kicker on-brand">Verified homes in Accra</div>
			<h1 id="hero-title">Find a home in Accra without getting scammed.</h1>
			<p class="hero-lede">We check every landlord and visit every home before it goes live. When you pay, we hold your rent until you've moved in.</p>
			<form class="hero-search vt-search" method="get" action="/homes" role="search">
				<select name="area" aria-label="Neighbourhood">
					<option value="">Any neighbourhood</option>
					{#each data.areas as area}<option value={area.slug}>{area.name}</option>{/each}
				</select>
				<select name="bedrooms" aria-label="Bedrooms">
					{#each beds as [value, label]}<option {value}>{label}</option>{/each}
				</select>
				<button class="btn accent" type="submit">Search homes</button>
			</form>
		</div>
		<div class="hero-ticket-wrap">
			<div class="hero-ticket">
				<div class="ht-top">
					<span>{ticket ? 'Verified listing' : 'Example listing'}</span><span>{ticket?.reference ?? 'AFE-EXAMPLE'}</span>
				</div>
				<div class="ht-body">
					<div>
						<div class="ht-title">{ticket?.title ?? '2-bedroom apartment'}</div>
						<div class="ht-area">{ticket?.area ?? 'East Legon'}, Accra</div>
					</div>
					<dl class="ht-cells">
						<div><dt>Beds</dt><dd>{ticket ? ticket.bedrooms || 'Room' : 2}</dd></div>
						<div><dt>Advance</dt><dd>{ticket?.advance_months ?? 6} mo</dd></div>
						<div><dt>Available</dt><dd>{ticket ? shortDate(ticket.available_from) : '1 Nov'}</dd></div>
					</dl>
					<div class="ht-checks">
						<div><span class="pop" style="--d: .9s"><CheckIcon /></span>Landlord verified</div>
						<div><span class="pop" style="--d: 1.05s"><CheckIcon /></span>Property verified</div>
					</div>
				</div>
				<div class="tear flush" style="--notch: var(--brand)"></div>
				<div class="ht-foot">
					<div class="ht-rent"><span class="label-mono">Rent / month</span><span>{ticket ? cedis(ticket.rent_display) : 'GH₵ 3,500'}</span></div>
					<a class="btn md" href={ticket ? `/homes/${ticket.reference}` : '/homes'}>{ticket ? 'View home' : 'See homes'}</a>
				</div>
			</div>
		</div>
	</div>
</section>

<section id="scam-check" class="scam" aria-labelledby="scam-title">
	<div class="scam-in">
		<div class="scam-copy">
			<h2 id="scam-title">Found a place on WhatsApp? Check it first.</h2>
			<p>Paste a phone number or listing link. We'll tell you if Afe has verified that landlord or home.</p>
		</div>
		<div class="scam-form">
			<form
				method="post"
				action="?/check"
				use:enhance={() => {
					checking = true;
					typed = false;
					return async ({ update }) => {
						await update({ reset: false });
						checking = false;
					};
				}}
			>
				<input type="text" name="q" bind:value={q} oninput={() => (typed = true)} maxlength="20" placeholder="e.g. 024 123 4567" aria-label="Phone number or listing reference" autocomplete="off" />
				<button class="btn" type="submit" disabled={checking}>Check</button>
			</form>
			<div aria-live="polite">
				{#if form && 'error' in form && form.error && !typed}
					<p class="notice error">{form.error}</p>
				{:else if answer}
					{#if answer.verified}
						<div class="notice ok answer">
							<span class="badge">Verified by Afe</span><span>{answer.headline}</span>
							{#each answer.listings.slice(0, 3) as l}<a href="/homes/{l.reference}">See {l.reference} on Afe</a>{/each}
						</div>
					{:else}
						<div class="notice answer">
							<span class="tag warn">Not verified by Afe</span><span>We have no verified landlord or home for this number. Don't send money before a viewing.</span>
							<a href="/check?q={encodeURIComponent(q)}">What to do next</a>
						</div>
					{/if}
				{/if}
			</div>
		</div>
	</div>
</section>

<section id="how" class="band" aria-labelledby="how-title">
	<div class="band-head">
		<div class="kicker">How it works</div>
		<h2 id="how-title">Checked by people. Watched by software.</h2>
	</div>
	<div class="how-steps">
		{#each steps as [title, body], i}
			<div class="how-step">
				<span class="step-num">{i + 1}</span>
				<h3>{title}</h3>
				<p>{body}</p>
			</div>
		{/each}
	</div>
	<div class="record">
		<div>
			<div class="label-mono">What you see on every listing</div>
			<p>A plain-words record of each check, with the date it was done.</p>
		</div>
		<ul class="record-lines">
			{#if data.record.length}
				{#each data.record.slice(0, 5) as line}
					<li><span class="tick"><CheckIcon /></span>{line.text} {date(line.date)}</li>
				{/each}
			{:else}
				{#each sampleRecord as line}<li><span class="tick"><CheckIcon /></span>{line}</li>{/each}
			{/if}
		</ul>
	</div>
</section>

<section id="listings" class="homes" aria-labelledby="homes-title">
	<div class="homes-in">
		<div class="homes-head">
			<div class="band-head">
				<div class="kicker">Verified this week</div>
				<h2 id="homes-title">Homes ready to view</h2>
			</div>
			<a class="btn secondary md" href="/homes">See all homes</a>
		</div>
		{#if data.latest.length}
			<div class="grid">
				{#each data.latest as listing (listing.id)}<ListingCard {listing} />{/each}
			</div>
		{:else}
			<p class="empty">The first verified homes are being checked now. Check back soon.</p>
		{/if}
	</div>
</section>

<section class="band" aria-labelledby="protect-title">
	<div class="band-head wide">
		<div class="row"><span class="kicker">Protected rent</span><span class="tag soft">Pilot from March 2027</span></div>
		<h2 id="protect-title">Your rent goes to the landlord only after you move in.</h2>
	</div>
	<div class="flow">
		{#each flow as [n, title, body]}
			<div><span class="n">{n}</span><div class="t">{title}</div><p>{body}</p></div>
		{/each}
	</div>
	<p class="ai-note">AI helps us spot warning signs, like reused photos or one phone number behind many listings. It works on top of the in-person checks and never replaces them.</p>
</section>

<section id="landlords" class="landlords" aria-labelledby="ll-title">
	<div class="ll-panel">
		<div class="ll-copy">
			<div class="kicker on-brand">For landlords and agents</div>
			<h2 id="ll-title">Get verified and stand out to renters who are ready to pay.</h2>
			<p>
				We check your ID and documents, visit the home and take the photos.{#if data.pricing?.launch_offer}
					Verification is free during the launch offer.{/if}
			</p>
		</div>
		<div class="ll-acts">
			<a class="btn accent" href="/signup?role=landlord">List your home</a>
			<a class="btn on-brand" href="/" data-section="how">How verification works</a>
		</div>
	</div>
</section>

<style>
	.offer {
		background: var(--amber-soft);
		border-bottom: 1px solid var(--amber-line);
	}
	.offer-in {
		max-width: 1180px;
		margin: 0 auto;
		padding: 10px 24px;
		display: flex;
		gap: 10px;
		align-items: center;
		flex-wrap: wrap;
		font-size: 14px;
	}
	.offer .tag {
		padding: 3px 8px;
	}
	.offer-text {
		flex: 1 1 240px;
		min-width: 0;
	}
	.offer-close {
		display: grid;
		place-items: center;
		width: 36px;
		height: 36px;
		margin: -6px -8px -6px 0;
		border: 0;
		border-radius: 8px;
		background: none;
		color: var(--ink);
		cursor: pointer;
		transition:
			background-color 150ms ease,
			transform 160ms var(--ease-out-fluid);
	}
	.offer-close svg {
		fill: none;
		stroke: currentColor;
		stroke-width: 1.75;
		stroke-linecap: round;
	}
	.offer-close:hover {
		background: var(--amber-line);
	}
	.offer-close:active {
		transform: scale(0.94);
	}

	/* Hero */
	.hero {
		background: var(--brand);
		color: #fff;
		border-bottom: 5px solid var(--amber);
	}
	.hero-in {
		max-width: 1180px;
		margin: 0 auto;
		padding: 72px 24px 80px;
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 420px), 1fr));
		gap: 56px;
		align-items: center;
	}
	.hero-copy {
		display: flex;
		flex-direction: column;
		gap: 24px;
	}
	.hero h1 {
		margin: 0;
		font-size: clamp(40px, 6vw, 64px);
		line-height: 1.02;
		letter-spacing: -0.02em;
	}
	.hero-lede {
		margin: 0;
		font-size: 19px;
		line-height: 1.55;
		max-width: 34em;
		color: var(--brand-ink-soft);
	}
	.hero-search {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
		background: #fff;
		padding: 8px;
		border-radius: 12px;
		max-width: 560px;
	}
	.hero-search select {
		flex: 1 1 180px;
		width: auto;
		font-size: 15px;
		color: #15211e;
		background: #fff;
		border-color: #d5dfdb;
	}
	.hero-search select + select {
		flex: 1 1 120px;
	}
	.hero-search .btn {
		flex: 0 0 auto;
		padding: 0 24px;
	}
	.hero-ticket-wrap {
		display: flex;
		justify-content: center;
	}
	.hero-ticket {
		width: 340px;
		max-width: 100%;
		background: #fff;
		color: #15211e;
		border-radius: 16px;
		box-shadow: 0 24px 60px rgba(0, 0, 0, 0.25);
		animation: ticket-in 0.8s var(--ease-snap) 0.2s both;
		--line: #d5dfdb;
		--muted: #56665f;
	}
	.ht-top {
		background: #e7f0ec;
		border-radius: 16px 16px 0 0;
		padding: 14px 20px;
		display: flex;
		justify-content: space-between;
		align-items: center;
		font: 10.5px var(--font-mono);
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: #0e4a3e;
	}
	.ht-body {
		padding: 20px;
		display: flex;
		flex-direction: column;
		gap: 16px;
	}
	.ht-title {
		font: 700 24px/1.1 var(--font-display);
	}
	.ht-area {
		font-size: 15px;
		color: #56665f;
		margin-top: 4px;
	}
	.ht-cells {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		border: 1px solid #d5dfdb;
		border-radius: 8px;
		margin: 0;
	}
	.ht-cells div {
		padding: 10px 12px;
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.ht-cells div + div {
		border-left: 1px solid #d5dfdb;
	}
	.ht-cells dt {
		font: 10.5px var(--font-mono);
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: #56665f;
	}
	.ht-cells dd {
		margin: 0;
		font-size: 16px;
		font-weight: 600;
	}
	.ht-checks {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.ht-checks div {
		display: flex;
		align-items: center;
		gap: 10px;
		font-size: 14px;
	}
	.pop {
		width: 20px;
		height: 20px;
		border-radius: 99px;
		background: #e3f4ea;
		color: #16794c;
		display: flex;
		align-items: center;
		justify-content: center;
		animation: pop 0.45s var(--ease-snap) var(--d) both;
	}
	.ht-foot {
		padding: 18px 20px 20px;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
	}
	.ht-rent {
		display: flex;
		flex-direction: column;
	}
	.ht-rent span:last-child {
		font: 700 26px var(--font-display);
		color: #0e4a3e;
		font-variant-numeric: tabular-nums;
	}
	.hero-ticket .btn {
		background: #0e4a3e;
		color: #fff;
	}
	.hero-ticket .btn:hover {
		background: #0f6b57;
	}
	@keyframes ticket-in {
		0% {
			opacity: 0;
			transform: translateY(28px) rotate(-1deg);
		}
		100% {
			opacity: 1;
			transform: none;
		}
	}
	@keyframes pop {
		0% {
			opacity: 0;
			transform: scale(0.6);
		}
		70% {
			transform: scale(1.06);
		}
		100% {
			opacity: 1;
			transform: none;
		}
	}

	/* Scam check */
	.scam {
		background: var(--surface);
		border-bottom: 1px solid var(--line);
	}
	.scam-in {
		max-width: 1180px;
		margin: 0 auto;
		padding: 48px 24px;
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 380px), 1fr));
		gap: 32px;
		align-items: center;
	}
	.scam-copy {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.scam h2 {
		margin: 0;
		font-size: 30px;
		line-height: 1.15;
	}
	.scam-copy p {
		margin: 0;
		color: var(--muted);
		max-width: 36em;
	}
	.scam-form {
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.scam-form form {
		display: flex;
		gap: 8px;
		flex-wrap: wrap;
	}
	.scam-form input {
		flex: 1 1 220px;
		width: auto;
		background: var(--paper);
	}
	.answer {
		margin: 0;
		align-items: flex-start;
		font-size: 14.5px;
	}
	.answer .tag {
		padding: 3px 8px;
	}

	/* Bands */
	.band {
		max-width: 1180px;
		margin: 0 auto;
		padding: 88px 24px;
		width: 100%;
		display: flex;
		flex-direction: column;
		gap: 40px;
	}
	.band-head {
		display: flex;
		flex-direction: column;
		gap: 8px;
		max-width: 640px;
	}
	.band-head.wide {
		max-width: 680px;
	}
	.band-head h2 {
		margin: 0;
		font-size: clamp(30px, 4vw, 40px);
		line-height: 1.1;
		text-wrap: balance;
	}
	.how-steps {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr));
		gap: 16px;
	}
	.how-step {
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: 12px;
		padding: 24px;
		display: flex;
		flex-direction: column;
		gap: 12px;
	}
	.step-num {
		font: 700 15px var(--font-display);
		width: 32px;
		height: 32px;
		border-radius: 8px;
		background: var(--tint);
		color: var(--brand);
		display: flex;
		align-items: center;
		justify-content: center;
	}
	.how-step h3 {
		margin: 0;
		font-size: 21px;
		line-height: 1.2;
	}
	.how-step p {
		margin: 0;
		font-size: 15.5px;
		line-height: 1.55;
		color: var(--muted);
	}
	.record {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 380px), 1fr));
		gap: 24px;
		align-items: center;
		background: var(--tint);
		border-radius: 12px;
		padding: 28px;
	}
	.record p {
		margin: 8px 0 0;
		font-size: 15.5px;
		max-width: 34em;
	}
	.record-lines {
		list-style: none;
		margin: 0;
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: 10px;
		padding: 16px 18px;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.record-lines li {
		display: flex;
		gap: 10px;
		align-items: center;
		font-size: 14.5px;
	}
	.record-lines .tick {
		width: 20px;
		height: 20px;
	}

	/* Homes */
	.homes {
		background: var(--surface);
		border-top: 1px solid var(--line);
		border-bottom: 1px solid var(--line);
	}
	.homes-in {
		max-width: 1180px;
		margin: 0 auto;
		padding: 88px 24px;
		display: flex;
		flex-direction: column;
		gap: 32px;
	}
	.homes-head {
		display: flex;
		justify-content: space-between;
		align-items: flex-end;
		gap: 16px 24px;
		flex-wrap: wrap;
	}

	/* Protected rent */
	.flow {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 200px), 1fr));
		gap: 1px;
		border: 1px solid var(--line);
		border-radius: 12px;
		background: var(--line);
		overflow: hidden;
	}
	.flow > div {
		padding: 22px;
		display: flex;
		flex-direction: column;
		gap: 8px;
		background: var(--surface);
	}
	.flow .n {
		font: 12px var(--font-mono);
		color: var(--warn);
	}
	.flow .t {
		font: 700 19px var(--font-display);
	}
	.flow p {
		margin: 0;
		font-size: 14.5px;
		color: var(--muted);
		line-height: 1.5;
	}
	.ai-note {
		margin: -4px 0 0;
		font-size: 15px;
		color: var(--muted);
		max-width: 44em;
	}

	/* Landlords */
	.landlords {
		max-width: 1180px;
		margin: 0 auto 88px;
		padding: 0 24px;
		width: 100%;
	}
	.ll-panel {
		background: var(--brand);
		color: #fff;
		border-radius: 16px;
		padding: 48px;
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 360px), 1fr));
		gap: 32px;
		align-items: center;
	}
	.ll-copy {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}
	.ll-copy h2 {
		margin: 0;
		font-size: clamp(28px, 3.6vw, 36px);
		line-height: 1.12;
		text-wrap: balance;
	}
	.ll-copy p {
		margin: 0;
		color: var(--brand-ink-soft);
		max-width: 34em;
	}
	.ll-acts {
		display: flex;
		gap: 10px;
		flex-wrap: wrap;
	}
	@media (max-width: 560px) {
		.hero-in {
			padding: 48px 20px 56px;
			gap: 40px;
		}
		.ll-panel {
			padding: 32px 24px;
		}
		.band,
		.homes-in {
			padding-block: 64px;
		}
	}
	@media (prefers-color-scheme: dark) {
		.step-num {
			color: var(--accent);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.hero-ticket,
		.pop {
			animation: none;
		}
		.offer-close:active {
			transform: none;
		}
	}
</style>
