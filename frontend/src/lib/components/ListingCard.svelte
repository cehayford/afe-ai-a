<script lang="ts">
	// A verified home as a ticket, from the Landing Page canvas ("Homes ready to view"): Afe photo with
	// the reference, title and area, the two verified chips, a tear line, then rent and "View home".
	import type { Listing } from '$lib/api/types';
	import { bedrooms, cedis, shortDate } from '$lib/format';
	import CheckIcon from '$lib/components/ui/CheckIcon.svelte';

	let { listing, href = `/homes/${listing.reference}`, notch = 'var(--surface)' }: { listing: Listing; href?: string; notch?: string } = $props();
	const live = $derived(listing.status === 'live');
</script>

<article class="card" style:--notch={notch}>
	<a class="shot" {href} tabindex="-1" aria-hidden="true">
		{#if listing.cover_url}
			<img class="ph" src={listing.cover_url} alt="" loading="lazy" width="400" height="300" />
		{:else}
			<div class="ph"></div>
		{/if}
		<span class="by">photo taken by Afe</span>
		<span class="tag ref">{listing.reference}</span>
	</a>
	<div class="body">
		<div class="head">
			<h3><a {href}>{listing.title}</a></h3>
			<div class="meta">{listing.area}, Accra</div>
		</div>
		<div class="facts-line">
			<span>{bedrooms(listing.bedrooms)}</span><span>{listing.property_type_label}</span><span class="muted">From {shortDate(listing.available_from)}</span>
		</div>
		{#if live || listing.featured}
			<div class="chipline">
				{#if live}
					<span class="badge sm plain"><CheckIcon size={11} />Landlord verified</span>
					<span class="badge sm plain"><CheckIcon size={11} />Property verified</span>
				{/if}
				{#if listing.featured}<span class="pill featured">Featured</span>{/if}
			</div>
		{/if}
	</div>
	<div class="tear"></div>
	<div class="foot">
		<div class="rent"><span class="label-mono">Rent / month</span><span class="price">{cedis(listing.rent_display)}</span></div>
		<a class="btn md" {href}>View home</a>
	</div>
</article>

<style>
	.shot {
		position: relative;
		display: block;
	}
	.by {
		position: absolute;
		left: 12px;
		bottom: 12px;
		font: 11px var(--font-mono);
		color: var(--muted);
	}
	.shot img + .by {
		color: #fff;
		text-shadow: 0 1px 3px rgba(0, 0, 0, 0.6);
	}
	.shot .tag {
		position: absolute;
		right: 12px;
		bottom: 12px;
		padding: 3px 8px;
	}
	.head {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	h3 {
		margin: 0;
		font-size: 21px;
		line-height: 1.15;
	}
	h3 a {
		color: var(--ink);
	}
	h3 a:hover {
		color: var(--brand);
	}
	@media (prefers-color-scheme: dark) {
		h3 a:hover {
			color: var(--primary-hover);
		}
	}
	.facts-line {
		display: flex;
		flex-wrap: wrap;
		gap: 4px 16px;
		font-size: 14px;
	}
	.chipline {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
	}
	.foot {
		padding: 14px 20px 18px;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
	}
	.rent {
		display: flex;
		flex-direction: column;
	}
</style>
