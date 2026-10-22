<script lang="ts">
	// Viewings tab of My Afe (Renter canvas): one card per viewing, home and area, when and with whom,
	// and a status pill; actions and the "did you rent it?" question sit under the card's heading.
	import { enhance } from '$app/forms';
	import FormError from '$lib/components/FormError.svelte';
	import ViewingActions from '$lib/components/ViewingActions.svelte';
	import { dateTime } from '$lib/format';

	let { data, form } = $props();
	const upcoming = $derived(data.viewings.filter((v) => ['requested', 'confirmed'].includes(v.status)));
	const past = $derived(data.viewings.filter((v) => !['requested', 'confirmed'].includes(v.status)));
	const LABEL: Record<string, [string, string]> = {
		requested: ['Waiting to confirm', 'warn'],
		confirmed: ['Booked', ''],
		completed: ['Viewed', 'ok'],
		declined: ['Declined', 'quiet'],
		cancelled: ['Cancelled', 'quiet'],
		no_show: ['Missed', 'bad']
	};
</script>

<svelte:head><title>Viewings · Afe</title></svelte:head>

<h2 class="sr">Viewings</h2>
<FormError message={form?.error} />
{#if form?.answered}<p class="result">Thanks. Your answer helps Afe keep renters safe; it never affects you.</p>{/if}

{#snippet viewingList(items: typeof data.viewings)}
	<div class="v-list">
		{#each items as v (v.id)}
			{@const [label, tone] = LABEL[v.status] ?? [v.status, '']}
			<div class="v-card">
				<div class="v-head">
					<div class="v-titles">
						<a class="v-title" href="/homes/{v.listing_reference}">{v.listing_title}</a>
						<span class="muted">{dateTime(v.requested_for)} · {v.role === 'renter' ? `with ${v.other_name} (verified)` : `${v.other_name} wants to view`}</span>
						{#if v.note}<span class="small muted">“{v.note}”</span>{/if}
					</div>
					<span class="pill {tone}">{label}</span>
				</div>
				<div class="row">
					<ViewingActions viewing={v} back="/account/viewings" />
					<a class="btn quiet sm" href="/account/messages/{v.thread_id}">Messages</a>
				</div>
				{#if v.role === 'renter' && v.status === 'completed'}
					<form class="row" method="post" action="?/outcome" use:enhance>
						<input type="hidden" name="id" value={v.id} />
						<label class="small" for="answer-{v.id}" style="margin: 0">Did you rent it?</label>
						<select id="answer-{v.id}" name="answer" value={v.outcome ?? ''} style="width: auto; height: 40px; font-size: 14px">
							<option value="" disabled>Choose</option>
							<option value="rented_through_afe">Yes, and I paid through Afe</option>
							<option value="paid_directly">Yes, but I paid the landlord directly</option>
							<option value="not_renting">No</option>
							<option value="still_deciding">Still deciding</option>
						</select>
						<button class="btn secondary sm" type="submit">{v.outcome ? 'Update' : 'Answer'}</button>
					</form>
				{/if}
			</div>
		{/each}
	</div>
{/snippet}

{#if upcoming.length}{@render viewingList(upcoming)}{:else}<p class="muted" style="margin: 0; font-size: 15px">No viewings booked yet. <a href="/homes">Find a home</a> and book one.</p>{/if}

{#if past.length}
	<h3 class="past">Past and cancelled</h3>
	{@render viewingList(past)}
{/if}

<style>
	.v-list {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}
	.v-card {
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: 12px;
		padding: 18px;
		display: flex;
		flex-direction: column;
		gap: 12px;
	}
	.v-head {
		display: flex;
		justify-content: space-between;
		gap: 12px;
		flex-wrap: wrap;
		align-items: center;
	}
	.v-titles {
		display: flex;
		flex-direction: column;
		gap: 4px;
		font-size: 14px;
	}
	.v-title {
		font: 700 18px var(--font-display);
		color: var(--ink);
	}
	.v-card .pill {
		font-size: 13px;
		padding: 5px 12px;
	}
	.past {
		margin: 12px 0 0;
		font-size: 18px;
	}
</style>
