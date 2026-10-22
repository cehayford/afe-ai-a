<script lang="ts">
	import { enhance } from '$app/forms';
	import FormError from '$lib/components/FormError.svelte';
	import { date, statusLabel } from '$lib/format';

	let { data, form } = $props();
	const l = $derived(data.listing);
	const editable = $derived(!['let', 'archived'].includes(l.status));
</script>

<svelte:head><title>{l.title} · Afe</title></svelte:head>

<a class="back" href="/landlord">← Dashboard</a>
<div class="row spread">
	<h1>{l.title}</h1>
	<span class="pill {l.status === 'live' ? 'ok' : l.status === 'pending_review' ? 'warn' : ''}">{statusLabel(l.status)}</span>
</div>
<p class="lede">{l.reference} · {l.area}{l.status_reason ? ` · ${l.status_reason}` : ''}</p>

<FormError message={form?.error} />
{#if form?.saved}<p class="result ok">Saved.{l.status === 'pending_review' ? ' Live listings go back to review after an edit.' : ''}</p>{/if}
{#if form?.submitted}<p class="result ok">Sent for review. We'll SMS you when it's live.</p>{/if}

<div class="detail">
	<form class="box stack" method="post" action="?/save" use:enhance>
		<h2 style="margin-top: 0">Details</h2>
		<label for="title">Title</label>
		<input id="title" type="text" name="title" value={l.title} minlength="5" maxlength="90" disabled={!editable} />
		<label for="description">Description</label>
		<textarea id="description" name="description" minlength="20" maxlength="5000" disabled={!editable}>{l.description}</textarea>
		<div class="form-grid">
			<div><label for="rent_ghs">Monthly rent (GH₵)</label><input id="rent_ghs" type="number" name="rent_ghs" min="1" value={l.rent_pesewas / 100} disabled={!editable} /></div>
			<div><label for="advance_months">Months in advance</label><input id="advance_months" type="number" name="advance_months" min="0" max="24" value={l.advance_months} disabled={!editable} /></div>
			<div><label for="min_lease_months">Minimum lease</label><input id="min_lease_months" type="number" name="min_lease_months" min="1" max="60" value={l.min_lease_months} disabled={!editable} /></div>
			<div><label for="available_from">Available from</label><input id="available_from" type="date" name="available_from" value={l.available_from} disabled={!editable} /></div>
		</div>
		{#if editable}<button class="btn" type="submit">Save changes</button>{/if}
	</form>

	<aside>
		{#if l.status === 'draft' || l.status === 'paused'}
			<form class="box" method="post" action="?/submit" use:enhance>
				<h2 style="margin-top: 0">Publish</h2>
				<p>An Afe reviewer checks every listing before it goes live.</p>
				<button class="btn" type="submit">Send for review</button>
			</form>
		{/if}
		{#if data.blockers.length && l.status !== 'live'}
			<div class="box">
				<h3>Before it can go live</h3>
				<ul>{#each data.blockers as b}<li class="small">{b}</li>{/each}</ul>
			</div>
		{/if}
		{#if data.flags.length}
			<div class="box">
				<h3>Checks raised</h3>
				{#each data.flags as f}<p class="flag small">{f}</p>{/each}
				<p class="note">A reviewer looks at these. Remove pay-first wording and phone numbers from the text.</p>
			</div>
		{/if}
		{#if l.status === 'live'}
			<form class="box" method="post" action="?/feature" use:enhance>
				<h2 style="margin-top: 0">Feature this listing</h2>
				{#if l.featured_until}
					<p><span class="pill featured">Featured</span> until {date(l.featured_until)}. Paying again adds more time.</p>
				{:else}
					<p>Show it first in search results in its area. Only verified, live listings can be featured. Free during the launch offer.</p>
				{/if}
				<button class="btn" type="submit">Feature listing</button>
			</form>
			<p><a class="btn secondary" href="/homes/{l.reference}">View public page</a></p>
		{/if}
		{#if editable}
			<form method="post" action="?/archive" use:enhance>
				<button class="btn secondary" type="submit">Take down (archive)</button>
			</form>
		{/if}
	</aside>
</div>
