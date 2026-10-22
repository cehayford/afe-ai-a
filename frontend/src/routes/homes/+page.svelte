<script lang="ts">
	// Search results from the Renter canvas: a filter bar that applies as you change it, a list of
	// horizontal cards beside a sticky map, the card under the pointer lights its pin, Save toggles.
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { enhance, applyAction } from '$app/forms';
	import { goto } from '$app/navigation';
	import FormError from '$lib/components/FormError.svelte';
	import HomesMap from '$lib/components/HomesMap.svelte';
	import { bedrooms, cedis, shortDate } from '$lib/format';
	import { translate, type MessageKey } from '$lib/i18n';

	let { data, form } = $props();
	const t = (key: MessageKey) => translate(data.lang, key);
	const searched = $derived(Boolean(data.q.area || data.q.bedrooms || data.q.max_rent));

	let filters: HTMLFormElement;
	let live = $state(false);
	onMount(() => (live = true));
	// Filters apply as they change (as in the prototype); empty ones stay out of the address.
	function apply() {
		const params = new URLSearchParams();
		for (const [k, v] of new FormData(filters)) if (v) params.set(k, String(v));
		goto(`/homes${params.size ? `?${params}` : ''}`, { keepFocus: true, noScroll: true, replaceState: true });
	}

	let hovered = $state<string | null>(null);
	// Saved state is kept here so the toggle answers at once; the server confirms in the background.
	let saved = $state(new Set<string>());
	$effect(() => {
		saved = new Set(data.saved);
	});

	const beds = [
		['', 'Any'],
		['1', '1 bed'],
		['2', '2 beds'],
		['3', '3+']
	];
	const caps = $derived.by(() => {
		const base = ['2500', '4000', '6500'];
		if (data.q.max_rent && !base.includes(data.q.max_rent)) base.push(data.q.max_rent);
		return base.sort((a, b) => Number(a) - Number(b));
	});
	const count = $derived(`${data.listings.length} verified ${data.listings.length === 1 ? 'home' : 'homes'}`);
</script>

<svelte:head><title>Find a verified home · Afe</title></svelte:head>

<h1 class="sr">Find a verified home in Accra</h1>

<div class="results-page">
	<form
		class="filters vt-search"
		method="get"
		role="search"
		bind:this={filters}
		onsubmit={(e) => {
			e.preventDefault();
			apply();
		}}
	>
		<select name="area" value={data.q.area} onchange={apply} aria-label={t('search.area')}>
			<option value="">Any neighbourhood</option>
			{#each data.areas as area}<option value={area.slug}>{area.name}</option>{/each}
		</select>
		<div class="chips" role="radiogroup" aria-label="Bedrooms">
			{#each beds as [value, label]}
				<label class="chip"><input type="radio" name="bedrooms" {value} checked={(data.q.bedrooms || '') === value} onchange={apply} />{label}</label>
			{/each}
		</div>
		<select name="max_rent" value={data.q.max_rent} onchange={apply} aria-label="Rent per month">
			<option value="">Any rent</option>
			{#each caps as cap}<option value={cap}>Up to GH₵ {Number(cap).toLocaleString('en-GB')}</option>{/each}
		</select>
		{#if !live}<button class="btn md" type="submit">Apply</button>{/if}
		<span class="res-count" role="status">{count}</span>
	</form>

	<div class="split">
		<div class="res-list">
			{#each data.listings as l (l.id)}
				{@const on = saved.has(l.reference)}
				<article
					class="res-card"
					class:hot={hovered === l.reference}
					onmouseenter={() => (hovered = l.reference)}
					onmouseleave={() => (hovered = null)}
				>
					<a class="res-ph" href="/homes/{l.reference}" tabindex="-1" aria-hidden="true">
						{#if l.cover_url}<img src={l.cover_url} alt="" loading="lazy" width="132" height="132" />{/if}
						<span>photo by Afe</span>
					</a>
					<div class="info">
						<div class="top">
							<h2><a href="/homes/{l.reference}">{l.title}</a></h2>
							{#if data.me?.user.role !== 'landlord' && data.me?.user.role !== 'agent'}
								<form
									method="post"
									action="/homes/{l.reference}?/save"
									use:enhance={() => {
										const was = saved.has(l.reference);
										const next = new Set(saved);
										if (was) next.delete(l.reference);
										else next.add(l.reference);
										saved = next;
										return async ({ result }) => {
											if (result.type === 'redirect' || result.type === 'error') await applyAction(result);
											else if (result.type === 'failure') saved = new Set(data.saved);
										};
									}}
								>
									<input type="hidden" name="saved" value={String(on)} />
									<button class="save" class:on type="submit" aria-pressed={on} aria-label="{on ? 'Saved' : 'Save'}: {l.title}">{on ? 'Saved' : 'Save'}</button>
								</form>
							{/if}
						</div>
						<div class="res-meta">{l.area}, Accra · {bedrooms(l.bedrooms)} · {l.property_type_label} · From {shortDate(l.available_from)}</div>
						{#if l.status === 'live'}
							<div class="vchips"><span>✓ Landlord verified</span><span>✓ Property verified</span>{#if l.featured}<em>Featured</em>{/if}</div>
						{/if}
						<div class="bottom">
							<span class="rent">{cedis(l.rent_display)}<small>{' / month'}</small></span>
							<a class="btn secondary sm" href="/homes/{l.reference}">View home</a>
						</div>
					</div>
				</article>
			{:else}
				<div class="empty">No verified homes match these filters yet. Try a wider rent range.</div>
			{/each}

			{#if searched}
				<div class="box alert-box">
					<strong>{t('alerts.title')}</strong>
					{#if form?.alertSaved}
						<p class="small" style="margin: 0">Saved: {form.alertSaved}. <a href="/account/alerts">Manage alerts</a></p>
					{:else if data.me}
						<FormError message={form?.error} />
						<form class="row" method="post" action="?/alert" use:enhance>
							<input type="hidden" name="area" value={data.q.area} />
							<input type="hidden" name="bedrooms" value={data.q.bedrooms} />
							<input type="hidden" name="max_rent" value={data.q.max_rent} />
							<select name="channel" aria-label="How to tell you" style="width: auto; height: 40px; font-size: 14px">
								{#if data.me.user.phone}<option value="whatsapp">On WhatsApp</option><option value="sms">By SMS</option>{/if}
								<option value="in_app">In my Afe inbox</option>
							</select>
							<button class="btn secondary sm" type="submit">{t('alerts.save')}</button>
						</form>
					{:else}
						<p class="small" style="margin: 0"><a href="/signin?next={encodeURIComponent('/homes' + page.url.search)}">{t('alerts.sign_in')}</a></p>
					{/if}
				</div>
			{/if}

			{#if data.areas.length}
				<div class="areas">
					<span class="label-mono">Neighbourhoods</span>
					<div class="row">
						{#each data.areas as area}<a class="btn quiet small" href="/areas/{area.slug}">{area.name}</a>{/each}
						<a class="btn quiet small" href="/rent-index">Accra rent index</a>
					</div>
				</div>
			{/if}
		</div>

		<div class="map-col">
			<HomesMap listings={data.listings} {hovered} onhover={(r) => (hovered = r)} />
		</div>
	</div>
</div>

<style>
	.results-page {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}
	.filters {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
		align-items: center;
	}
	.filters select {
		width: auto;
		height: 44px;
		font-size: 15px;
	}
	.res-count {
		margin-left: auto;
		font-size: 14px;
		color: var(--muted);
	}
	.split {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 440px), 1fr));
		gap: 20px;
		align-items: start;
	}
	.res-list {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}
	.res-card {
		display: flex;
		gap: 14px;
		padding: 12px;
		background: var(--surface);
		border-radius: 14px;
		border: 1px solid var(--line);
		transition: box-shadow 0.2s, border-color 0.2s;
	}
	.res-card.hot {
		border-color: var(--brand);
		box-shadow: 0 8px 24px rgba(14, 74, 62, 0.12);
	}
	.res-ph {
		position: relative;
		flex: 0 0 132px;
		min-height: 132px;
		border-radius: 10px;
		overflow: hidden;
		background: var(--stripe);
		display: flex;
		align-items: flex-end;
		padding: 8px;
	}
	.res-ph img {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		object-fit: cover;
	}
	.res-ph span {
		position: relative;
		font: 10px var(--font-mono);
		color: var(--muted);
	}
	.res-ph img + span {
		color: #fff;
		text-shadow: 0 1px 3px rgba(0, 0, 0, 0.6);
	}
	.info {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.top {
		display: flex;
		justify-content: space-between;
		gap: 8px;
		align-items: flex-start;
	}
	.top h2 {
		margin: 0;
		font-size: 19px;
		line-height: 1.15;
	}
	.top h2 a {
		color: var(--ink);
	}
	.save {
		white-space: nowrap;
		height: 32px;
		padding: 0 10px;
		border-radius: 6px;
		border: 1px solid var(--line);
		background: var(--surface);
		color: var(--ink);
		font: 600 13px var(--font-sans);
		cursor: pointer;
		flex: 0 0 auto;
	}
	.save.on {
		border-color: var(--amber);
		background: var(--amber-soft);
	}
	.res-meta {
		font-size: 14px;
		color: var(--muted);
	}
	.vchips {
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
	}
	.vchips span,
	.vchips em {
		background: var(--ok-soft);
		color: var(--ok);
		font-size: 12px;
		font-weight: 600;
		font-style: normal;
		padding: 3px 9px;
		border-radius: 99px;
	}
	.vchips em {
		background: var(--amber-soft);
		color: var(--ink);
	}
	.bottom {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 8px;
		margin-top: auto;
	}
	.rent {
		white-space: nowrap;
		font: 700 21px var(--font-display);
		color: var(--brand);
		font-variant-numeric: tabular-nums;
	}
	.rent small {
		font: 400 13px var(--font-sans);
		color: var(--muted);
	}
	.areas {
		display: flex;
		flex-direction: column;
		gap: 8px;
		margin-top: 12px;
	}
	.map-col {
		position: sticky;
		top: 84px;
		height: min(640px, calc(100vh - 110px));
		min-height: 360px;
		border-radius: 12px;
		overflow: hidden;
		border: 1px solid var(--line);
		background: var(--tint);
	}
	@media (prefers-color-scheme: dark) {
		.rent {
			color: var(--accent);
		}
		.res-card.hot {
			border-color: var(--accent);
		}
	}
	@media (max-width: 520px) {
		.res-card {
			gap: 12px;
			padding: 10px;
		}
		.res-ph {
			flex-basis: 88px;
			min-height: 88px;
			align-self: flex-start;
			aspect-ratio: 1;
		}
		.top h2 {
			font-size: 17px;
		}
		.bottom {
			flex-wrap: wrap;
		}
		.rent {
			font-size: 19px;
		}
		.res-count {
			margin-left: 0;
			width: 100%;
		}
	}
</style>
