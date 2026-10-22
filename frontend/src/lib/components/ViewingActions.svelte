<script lang="ts">
	import { enhance } from '$app/forms';
	import type { Viewing } from '$lib/api/types';

	let { viewing, back }: { viewing: Viewing; back: string } = $props();
	const past = $derived(new Date(viewing.requested_for).getTime() < Date.now());
</script>

<div class="row">
	{#if viewing.role === 'lister' && viewing.status === 'requested'}
		<form method="post" action="/account/viewings?/respond" use:enhance>
			<input type="hidden" name="id" value={viewing.id} /><input type="hidden" name="back" value={back} />
			<input type="hidden" name="confirm" value="true" />
			<button class="btn sm" type="submit">Confirm</button>
		</form>
		<form method="post" action="/account/viewings?/respond" use:enhance>
			<input type="hidden" name="id" value={viewing.id} /><input type="hidden" name="back" value={back} />
			<input type="hidden" name="confirm" value="false" />
			<button class="btn secondary sm" type="submit">Can't do this time</button>
		</form>
	{/if}
	{#if viewing.role === 'lister' && viewing.status === 'confirmed' && past}
		<form method="post" action="/account/viewings?/complete" use:enhance>
			<input type="hidden" name="id" value={viewing.id} /><input type="hidden" name="back" value={back} />
			<input type="hidden" name="attended" value="true" />
			<button class="btn sm" type="submit">They came</button>
		</form>
		<form method="post" action="/account/viewings?/complete" use:enhance>
			<input type="hidden" name="id" value={viewing.id} /><input type="hidden" name="back" value={back} />
			<input type="hidden" name="attended" value="false" />
			<button class="btn secondary sm" type="submit">They didn't come</button>
		</form>
	{/if}
	{#if viewing.role === 'lister' && viewing.status === 'completed'}
		<a class="btn sm" href="/landlord/offer/{viewing.id}">Offer a tenancy</a>
	{/if}
	{#if viewing.status === 'requested' || (viewing.status === 'confirmed' && !past)}
		<form method="post" action="/account/viewings?/cancel" use:enhance>
			<input type="hidden" name="id" value={viewing.id} /><input type="hidden" name="back" value={back} />
			<button class="btn quiet sm" type="submit">Cancel viewing</button>
		</form>
	{/if}
</div>
