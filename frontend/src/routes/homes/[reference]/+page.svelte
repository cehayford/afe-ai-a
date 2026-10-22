<script lang="ts">
	// Listing detail from the Renter canvas: Afe photo grid, reference and title, facts strip, the
	// verification record, and a sticky rent ticket with Book a viewing and Save.
	import { enhance } from '$app/forms';
	import FormError from '$lib/components/FormError.svelte';
	import CheckIcon from '$lib/components/ui/CheckIcon.svelte';
	import { bedrooms, cedis, date, shortDate } from '$lib/format';

	let { data, form } = $props();
	const listing = $derived(data.listing);
	const canAct = $derived(!data.me || !['field_verifier', 'reviewer', 'admin'].includes(data.me.user.role));
	let allPhotos = $state(false);
	let saving = $state(false);
</script>

<svelte:head>
	<title>{listing.title} · Afe</title>
	<meta name="description" content="{listing.rent_display}/month · {bedrooms(listing.bedrooms)} in {listing.area}. Verified by Afe." />
	<meta property="og:type" content="website" />
	<meta property="og:site_name" content="Afe" />
	<meta property="og:title" content="{listing.title} · {listing.rent_display}/month" />
	<meta property="og:description" content="{bedrooms(listing.bedrooms)} in {listing.area}. Landlord and home checked in person by Afe. Never pay before you view." />
	{#if listing.cover_url}<meta property="og:image" content={listing.cover_url} />{/if}
</svelte:head>

<div class="page-1180 listing">
	<a class="back" href="/homes">← Back to results</a>

	<div class="gallery">
		{#each listing.photos.slice(0, 3) as photo, i (photo.id)}
			<div class="shot">
				<img src={photo.url} alt={photo.caption || listing.title} width={photo.width} height={photo.height} loading={i ? 'lazy' : 'eager'} />
				<span class="cap">{photo.caption || 'photo'}{i === 0 ? ' · photo taken by Afe' : ''}</span>
				{#if i === 2 && listing.photos.length > 3}
					<button type="button" class="more" onclick={() => (allPhotos = !allPhotos)} aria-expanded={allPhotos}>
						{allPhotos ? 'Fewer photos' : `All ${listing.photos.length} photos`}
					</button>
				{/if}
			</div>
		{:else}
			<div class="shot photo-ph">photos taken by Afe at the visit</div>
		{/each}
	</div>
	{#if allPhotos}
		<div class="all-photos">
			{#each listing.photos.slice(3) as photo (photo.id)}
				<figure><img src={photo.url} alt={photo.caption || listing.title} loading="lazy" width={photo.width} height={photo.height} /><figcaption>{photo.caption}</figcaption></figure>
			{/each}
		</div>
	{/if}

	<div class="detail">
		<div class="main-col">
			<div class="titles">
				<span class="ref">{listing.reference}</span>
				<h1>{listing.title}</h1>
				<div class="area">{listing.area}, {listing.city}</div>
			</div>
			<dl class="facts">
				<div><dt>Beds</dt><dd>{listing.bedrooms || 'Room'}</dd></div>
				<div><dt>Type</dt><dd>{listing.property_type_label}</dd></div>
				<div><dt>Available</dt><dd>{shortDate(listing.available_from)}</dd></div>
				<div><dt>Advance</dt><dd>{listing.advance_months} {listing.advance_months === 1 ? 'month' : 'months'}</dd></div>
			</dl>
			<div class="desc">
				{#each listing.description.split('\n').filter((p) => p.trim()) as para}<p>{para}</p>{/each}
			</div>

			<section class="lines" aria-labelledby="record-h">
				<div class="panel-head"><h2 id="record-h">Verification record</h2><span class="pill ok">All checks current</span></div>
				{#each listing.verification as line}
					<div class="line"><span class="tick"><CheckIcon /></span><span class="grow">{line.text}</span><time class="mono small muted" datetime={line.date}>{date(line.date)}</time></div>
				{/each}
				<div class="line ai-row">AI also watches this listing for warning signs, like reused photos or a changed payout account. It adds to these checks and never replaces them.</div>
			</section>

			{#if listing.reviews.length}
				<section class="lines" aria-labelledby="reviews-h">
					<div class="panel-head">
						<h2 id="reviews-h">From tenants who moved in</h2>
						{#if listing.landlord_rating !== null}<span class="pill featured"><span class="stars" aria-hidden="true">★</span> {listing.landlord_rating.toFixed(1)} · {listing.landlord_review_count} review{listing.landlord_review_count === 1 ? '' : 's'}</span>{/if}
					</div>
					{#each listing.reviews as r (r.id)}
						<div class="line review-row">
							<span class="stars" aria-label="{r.rating} out of 5">{'★'.repeat(r.rating)}{'☆'.repeat(5 - r.rating)}</span>
							<span class="grow">{r.body}</span>
							<span class="small muted">{r.author_name}, {date(r.created_at)}</span>
						</div>
					{/each}
					<div class="line ai-row">Only tenants who paid through Afe and moved in can review.</div>
				</section>
			{/if}

			{#if canAct}
				<section class="box" aria-labelledby="ask-h" id="contact">
					<h2 id="ask-h" class="box-title">Ask {listing.lister_name} a question</h2>
					<form class="stack" method="post" action="?/enquire" use:enhance>
						<FormError message={form?.form === 'enquire' ? form.error : null} />
						<label for="body" class="sr">Your message</label>
						<textarea id="body" name="body" maxlength="2000" required placeholder="Is it still available? Is water reliable?">{form?.form === 'enquire' ? form.body : ''}</textarea>
						<div class="row spread">
							<span class="note">Your phone number stays private. Keep the conversation on Afe so we can protect you.</span>
							<button class="btn secondary md" type="submit">{data.me ? 'Send message' : 'Sign in to send'}</button>
						</div>
					</form>
				</section>
			{/if}
		</div>

		<aside class="ticket" style="--notch: var(--paper)">
			<div class="t-top">
				<span class="label-mono">Rent / month</span>
				<span class="t-price">{cedis(listing.rent_display)}</span>
			</div>
			<div class="tear"></div>
			<div class="t-body">
				{#if canAct}
					<a class="btn big" href="/homes/{listing.reference}/viewing">Book a viewing</a>
					<form
						method="post"
						action="?/save"
						use:enhance={() => {
							saving = true;
							return async ({ update }) => {
								await update();
								saving = false;
							};
						}}
					>
						<input type="hidden" name="saved" value={String(listing.saved)} />
						<button class="btn secondary block save" type="submit" disabled={saving} aria-pressed={listing.saved}>{listing.saved ? 'Saved ✓' : 'Save this home'}</button>
					</form>
				{/if}
				<div class="notice">
					{#if listing.tenancy_available}
						Pay only through Afe. Your rent is held until you confirm you've moved in.
					{:else}
						Never pay anyone before you've viewed the home. Protected payments, where Afe holds your rent until you move in, are coming soon.
					{/if}
				</div>
				<dl class="kv small">
					<dt>Listed by</dt><dd>{listing.lister_name} ({listing.lister_role.toLowerCase()})</dd>
					<dt>Advance</dt><dd>{listing.advance_total_display}</dd>
					<dt>Minimum lease</dt><dd>{listing.min_lease_months} months</dd>
				</dl>
			</div>
		</aside>
	</div>
</div>

<style>
	.listing {
		gap: 20px;
	}
	.shot {
		position: relative;
		margin: 0;
		border-radius: 12px;
		overflow: hidden;
		background: var(--stripe);
	}
	.shot img {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}
	.shot .cap {
		position: absolute;
		left: 12px;
		bottom: 12px;
		font: 11px var(--font-mono);
		color: #fff;
		text-shadow: 0 1px 3px rgba(0, 0, 0, 0.7);
	}
	.more {
		position: absolute;
		right: 10px;
		bottom: 10px;
		height: 32px;
		padding: 0 12px;
		border: 0;
		border-radius: 6px;
		background: rgba(255, 255, 255, 0.94);
		color: #15211e;
		font: 600 13px var(--font-sans);
		cursor: pointer;
	}
	.all-photos {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
		gap: 8px;
	}
	.all-photos figure {
		margin: 0;
	}
	.all-photos img {
		width: 100%;
		aspect-ratio: 4 / 3;
		object-fit: cover;
		border-radius: 10px;
	}
	.all-photos figcaption {
		font: 11px var(--font-mono);
		color: var(--muted);
		margin-top: 4px;
	}
	.main-col {
		display: flex;
		flex-direction: column;
		gap: 24px;
	}
	.titles {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	.ref {
		font: 12px var(--font-mono);
		color: var(--muted);
	}
	.titles h1 {
		margin: 0;
	}
	.area {
		font-size: 16px;
		color: var(--muted);
	}
	.desc p {
		margin: 0 0 12px;
		font-size: 16px;
		line-height: 1.6;
		max-width: 40em;
	}
	.grow {
		flex: 1;
	}
	.ai-row {
		font-size: 13.5px;
		color: var(--muted);
	}
	.review-row {
		align-items: flex-start;
		flex-wrap: wrap;
	}
	.box-title {
		margin: 0 0 12px;
		font-size: 20px;
	}
	.ticket {
		position: sticky;
		top: 84px;
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: 16px;
		display: flex;
		flex-direction: column;
	}
	.t-top {
		padding: 20px;
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
	.t-price {
		font: 700 34px var(--font-display);
		color: var(--brand);
		font-variant-numeric: tabular-nums;
	}
	.t-body {
		padding: 20px;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.t-body .notice {
		margin: 0;
		font-size: 13.5px;
	}
	.save {
		height: 48px;
		font-size: 15px;
	}
	.t-body .kv {
		margin-top: 6px;
	}
	@media (prefers-color-scheme: dark) {
		.t-price {
			color: var(--accent);
		}
	}
	@media (max-width: 860px) {
		.ticket {
			position: static;
		}
	}
</style>
