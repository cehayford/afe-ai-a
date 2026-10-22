<script lang="ts">
	// "Current verification" with a revoke form, from the Afe Missing Features canvas: a reason code
	// is required before Revoke wakes up, the note goes to the person, and it's all audit-logged.
	import { enhance } from '$app/forms';
	import type { ReasonCode, Verification } from '$lib/api/types';
	import { date } from '$lib/format';
	import FormError from './FormError.svelte';
	import { hydrated } from '$lib/hydrated.svelte';
	const js = hydrated();

	let {
		current,
		codes,
		error = null,
		who = 'this person'
	}: { current: Verification | null; codes: ReasonCode[]; error?: string | null; who?: string } = $props();
	const reasons = $derived(codes.filter((c) => !c.approval));
	let reason = $state('');
	let busy = $state(false);
</script>

<section class="case" aria-labelledby="cur-h">
	<div class="case-head">
		<b id="cur-h">Current verification</b>
		{#if current}<span class="mono">approved {date(current.decided_at)} · until {date(current.expires_at)}</span>{:else}<span class="pill quiet">None</span>{/if}
	</div>
	{#if current}
		<form
			class="case-body"
			method="post"
			action="?/revoke"
			use:enhance={() => {
				busy = true;
				return async ({ update }) => {
					await update();
					busy = false;
					reason = '';
				};
			}}
		>
			<input type="hidden" name="id" value={current.id} />
			<p class="muted small">
				Revoke when new evidence shows {who} should not be verified. Their live listings pause at once, and they can appeal once.
			</p>
			<FormError message={error} />
			<div>
				<label for="revoke-reason">Reason code</label>
				<select id="revoke-reason" name="reason" bind:value={reason} class="w520" required>
					<option value="">Choose a reason (required)</option>
					{#each reasons as c (c.code)}<option value={c.code}>{c.code} · {c.label}</option>{/each}
				</select>
			</div>
			<div>
				<label for="revoke-note">Note <span class="muted" style="font-weight: 400">(the person reads it)</span></label>
				<input id="revoke-note" name="note" maxlength="300" placeholder="What you found" class="w520" />
			</div>
			<div><button class="btn danger md" type="submit" disabled={(js.on && !reason) || busy}>Revoke verification</button></div>
			<span class="small muted">Saved to the audit log with your name and the reason code.</span>
		</form>
	{:else}
		<div class="case-body small muted">Nothing to revoke: {who} has no current verification.</div>
	{/if}
</section>

<style>
	.w520 {
		max-width: 520px;
		height: 44px;
		font-size: 15px;
	}
</style>
