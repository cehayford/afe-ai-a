<script lang="ts">
	// Tenant reviews about a landlord, for reviewers (Afe Missing Features canvas): every review with
	// its stars, hidden ones marked, and a Hide form that needs a reason of at least 10 characters.
	import { enhance } from '$app/forms';
	import type { ReviewModeration } from '$lib/api/types';
	import { date } from '$lib/format';
	import FormError from './FormError.svelte';
	import { hydrated } from '$lib/hydrated.svelte';
	const js = hydrated();

	let { reviews, error = null }: { reviews: ReviewModeration[]; error?: string | null } = $props();
	// A disclosure per review, so hiding works without JavaScript too.
	let opened = $state<Record<number, boolean>>({});
	let notes = $state<Record<number, string>>({});
	let busy = $state(false);
	const stars = (n: number) => '★'.repeat(n) + '☆'.repeat(5 - n);
</script>

<section class="case" aria-labelledby="rev-h">
	<div class="case-head"><b id="rev-h">Tenant reviews</b><span class="mono">shown on their listings</span></div>
	<FormError message={error} />
	{#each reviews as r (r.id)}
		<div class="r-row" class:hid={r.hidden}>
			<div class="row spread">
				<span class="row">
					<span class="stars" aria-label="{r.rating} out of 5">{stars(r.rating)}</span>
					<b>{r.author_name}</b>
					<span class="mono small muted">{r.listing_reference} · {date(r.created_at)}</span>
				</span>
				{#if r.hidden}<span class="pill quiet">Hidden from renters</span>{/if}
			</div>
			<p>{r.body}</p>
			{#if !r.hidden}
				<details class="hide-box" bind:open={opened[r.id]}>
					<summary class="btn secondary sm">Hide this review</summary>
					<form
						class="hide-form"
						method="post"
						action="?/hideReview"
						use:enhance={() => {
							busy = true;
							return async ({ update, result }) => {
								await update();
								busy = false;
								if (result.type === 'success') opened[r.id] = false;
							};
						}}
					>
						<input type="hidden" name="id" value={r.id} />
						<label for="hide-{r.id}">Why hide it <span class="muted" style="font-weight: 400">(at least 10 characters, kept in the audit log)</span></label>
						<input id="hide-{r.id}" name="note" bind:value={notes[r.id]} minlength="10" maxlength="2000" required placeholder="Contains a phone number and a personal attack" />
						<div class="row">
							<button class="btn danger sm" type="submit" disabled={busy || (js.on && (notes[r.id] ?? '').trim().length < 10)}>Hide review</button>
						</div>
					</form>
				</details>
			{/if}
		</div>
	{:else}
		<div class="case-body small muted">No reviews yet. Tenants can review once their rent has been released.</div>
	{/each}
</section>

<style>
	.r-row {
		padding: 12px 16px;
		border-bottom: 1px solid var(--hair);
		display: flex;
		flex-direction: column;
		gap: 6px;
		font-size: 14.5px;
	}
	.r-row:last-child {
		border-bottom: 0;
	}
	.r-row p {
		margin: 0;
		line-height: 1.5;
	}
	.hid {
		opacity: 0.65;
	}
	.stars {
		color: var(--amber);
		letter-spacing: 1px;
	}
	.hide-form {
		display: flex;
		flex-direction: column;
		gap: 8px;
		background: var(--paper);
		border-radius: 8px;
		padding: 12px;
	}
	.hide-form label {
		margin: 0;
	}
	.hide-box > summary {
		list-style: none;
		width: fit-content;
	}
	.hide-box > summary::-webkit-details-marker {
		display: none;
	}
	.hide-box[open] > summary {
		margin-bottom: 8px;
	}
</style>
