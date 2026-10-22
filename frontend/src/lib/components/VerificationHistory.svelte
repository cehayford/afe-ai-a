<script lang="ts">
	// Past decisions as case rows: the outcome pill, when and by whom, the codes and the note.
	import type { Verification } from '$lib/api/types';
	import { date, statusLabel } from '$lib/format';

	let { history }: { history: Verification[] } = $props();
	const TONE: Record<string, string> = { approved: 'ok', rejected: 'bad', revoked: 'warn' };
</script>

{#if history.length}
	<section class="case" aria-label="Past decisions">
		<div class="case-head"><b>Past decisions</b></div>
		{#each history as v (v.id)}
			<div class="h-row">
				<span class="row spread"><span class="pill {TONE[v.status] ?? ''}">{statusLabel(v.status)}</span><span class="mono small muted">{date(v.decided_at)} · {v.decided_by_name}</span></span>
				{#if v.reason_codes.length}<span class="mono small">{v.reason_codes.join(', ')}</span>{/if}
				{#if v.note}<span class="small muted">{v.note}</span>{/if}
			</div>
		{/each}
	</section>
{/if}

<style>
	.h-row {
		display: flex;
		flex-direction: column;
		gap: 4px;
		padding: 10px 16px;
		border-bottom: 1px solid var(--hair);
	}
	.h-row:last-child {
		border-bottom: 0;
	}
</style>
