<script lang="ts">
	// The Admin Review canvas's decision panel: evidence chips to approve, a reason code that is
	// required before Reject wakes up, an optional note, and the audit-log line.
	import { enhance } from '$app/forms';
	import type { ReasonCode } from '$lib/api/types';
	import FormError from './FormError.svelte';
	import { hydrated } from '$lib/hydrated.svelte';
	const js = hydrated();

	let { codes, error, preset = [] }: { codes: ReasonCode[]; error?: string | null; preset?: string[] } = $props();
	const approvals = $derived(codes.filter((c) => c.approval));
	const rejections = $derived(codes.filter((c) => !c.approval));
	let reason = $state('');
	let busy = $state(false);
</script>

<form
	class="case"
	method="post"
	action="?/decide"
	use:enhance={() => {
		busy = true;
		return async ({ update }) => {
			await update();
			busy = false;
		};
	}}
>
	<div class="case-head"><b>Decision</b></div>
	<div class="case-body">
		<FormError message={error} />
		<fieldset class="ev">
			<legend class="small muted">Evidence you checked (to approve)</legend>
			<div class="chips">
				{#each approvals as c (c.code)}<label class="chip ev-chip"><input type="checkbox" name="codes" value={c.code} checked={preset.includes(c.code)} />{c.label}</label>{/each}
			</div>
		</fieldset>
		<select name="reason" bind:value={reason} aria-label="Reason code">
			<option value="">Reason code (required to reject)</option>
			{#each rejections as c (c.code)}<option value={c.code}>{c.code} · {c.label}</option>{/each}
		</select>
		<input type="text" name="note" maxlength="300" placeholder="Note (optional)" aria-label="Note" />
		<div class="row">
			<button class="btn go md" name="decision" value="approve" type="submit" disabled={busy}>Approve</button>
			<button class="btn danger md" name="decision" value="reject" type="submit" disabled={(js.on && !reason) || busy}>Reject</button>
		</div>
		<span class="small muted">Every decision is saved to the audit log with your name and the reason code.</span>
	</div>
</form>

<style>
	.ev {
		border: 0;
		padding: 0;
		margin: 0;
		min-width: 0; /* a fieldset is as wide as its widest content unless told otherwise */
	}
	.ev legend {
		margin-bottom: 8px;
		padding: 0;
	}
	.ev-chip {
		height: auto;
		min-height: 36px;
		padding-block: 6px;
		font-size: 13.5px;
		white-space: normal; /* long evidence labels wrap on a narrow phone */
	}
	select,
	input[type='text'] {
		max-width: 520px;
		height: 44px;
		font-size: 15px;
	}
</style>
