<script lang="ts">
	// Scam check from the Renter canvas: one field, one button, and a verdict card: green border and
	// "Verified by Afe" for a match, amber border and "Not verified by Afe" with advice otherwise.
	import { enhance } from '$app/forms';
	import FormError from '$lib/components/FormError.svelte';
	import { announce } from '$lib/announce.svelte';

	let { data, form } = $props();
	const looksLikePhone = $derived(/^[+\d\s-]{9,}$/.test(data.q));
	// The verdict appears without a new page title, so screen readers are told the answer.
	$effect(() => {
		if (data.result) announce(`${data.result.verified ? 'Verified by Afe' : 'Not verified by Afe'}. ${data.result.headline}`);
	});
</script>

<svelte:head><title>Scam check · Afe</title></svelte:head>

<div class="page-720 scam-page">
	<div class="page-head">
		<h1>Scam check</h1>
		<p>Paste the phone number or Afe listing reference someone sent you. We'll tell you if Afe has verified that landlord or home.</p>
	</div>

	<form class="ask" method="get">
		<label for="q" class="sr">Phone number or listing reference</label>
		<input id="q" type="text" name="q" maxlength="20" value={data.q} placeholder="Phone number or listing reference" autocomplete="off" />
		<button class="btn lg" type="submit">Check</button>
	</form>

	{#if data.result}
		<section class="verdict" class:hit={data.result.verified}>
			{#if data.result.verified}
				<span class="pill ok big-pill">✓ Verified by Afe</span>
			{:else}
				<span class="tag warn">Not verified by Afe</span>
			{/if}
			<h2>{data.result.headline}</h2>
			{#each data.result.details as detail}<p class="muted">{detail}</p>{/each}
			{#if data.result.advice.length}<ul>{#each data.result.advice as a}<li>{a}</li>{/each}</ul>{/if}
			<div class="row">
				{#if data.result.listings.length}
					{#each data.result.listings.slice(0, 3) as l}<a class="btn md" href="/homes/{l.reference}">See {l.reference} on Afe</a>{/each}
				{:else}
					<a class="btn md" href="/homes">Browse verified homes</a>
					<a class="btn quiet md" href="?q={encodeURIComponent(data.q)}" data-section="report">Report this {looksLikePhone ? 'number' : 'listing'}</a>
				{/if}
			</div>
		</section>
	{/if}

	<section id="report" class="report" aria-labelledby="report-h">
		<div class="page-head">
			<h2 id="report-h">Report a scam</h2>
			<p>Lost money, or asked to pay before viewing? Tell us. Reports help us warn other renters.</p>
		</div>
		{#if form?.reported}
			<p class="result">Reported. Thank you. Your report has gone to the Afe trust team.</p>
		{:else}
			<form class="box stack" method="post" action="?/report" use:enhance>
				<FormError message={form?.error} />
				<div>
					<label for="what_happened">What happened?</label>
					<textarea id="what_happened" name="what_happened" required>{form?.report?.what_happened ?? ''}</textarea>
				</div>
				<div class="form-grid">
					<div>
						<label for="reported_phone">Their phone number (if you have it)</label>
						<input id="reported_phone" type="tel" name="reported_phone" value={form?.report?.reported_phone ?? (looksLikePhone ? data.q : '')} />
					</div>
					<div>
						<label for="reported_reference">Afe listing reference (if any)</label>
						<input id="reported_reference" type="text" name="reported_reference" value={form?.report?.reported_reference ?? (!looksLikePhone ? data.q : '')} />
					</div>
				</div>
				<div><button class="btn" type="submit">Send report</button></div>
			</form>
		{/if}
	</section>
</div>

<style>
	.scam-page {
		padding-top: 28px;
	}
	.ask {
		display: flex;
		gap: 8px;
		flex-wrap: wrap;
	}
	.ask input {
		flex: 1 1 240px;
		width: auto;
		height: 52px;
	}
	.verdict {
		background: var(--surface);
		border: 2px solid var(--warn-strong);
		border-radius: 12px;
		padding: 24px;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}
	.verdict.hit {
		border-color: var(--ok);
	}
	.verdict .tag {
		font-size: 12px;
		padding: 5px 10px;
	}
	.big-pill {
		font-size: 13px;
		padding: 5px 12px;
	}
	.verdict h2 {
		margin: 0;
		font-size: 22px;
		line-height: 1.2;
	}
	.verdict p {
		margin: 0;
		font-size: 15px;
	}
	.verdict ul {
		margin: 0;
		padding-left: 20px;
		font-size: 15px;
		line-height: 1.7;
	}
	.report {
		display: flex;
		flex-direction: column;
		gap: 16px;
		margin-top: 16px;
	}
	.report h2 {
		font-size: 24px;
	}
</style>
