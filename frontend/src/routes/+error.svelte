<script lang="ts">
	// Errors as an empty-state card: the status in mono, what went wrong, any reasons, and the way back.
	import { page } from '$app/state';
</script>

<svelte:head><title>{page.status === 404 ? 'Not found' : 'Something went wrong'} · Afe</title></svelte:head>

<div class="page-640 err">
	<div class="err-card">
		<span class="kicker">Error {page.status}</span>
		<h1>{page.error?.message ?? 'Something went wrong.'}</h1>
		{#if page.error?.reasons?.length}
			<ul>{#each page.error.reasons as reason, i (i)}<li>{reason}</li>{/each}</ul>
		{:else if page.status === 404}
			<p class="muted">The page may have moved, or the listing may no longer be live.</p>
		{/if}
		<div class="row">
			<a class="btn md" href="/homes">Find a verified home</a>
			<a class="btn quiet md" href="/">Afe home</a>
		</div>
	</div>
</div>

<style>
	.err {
		padding: 40px 0;
	}
	.err-card {
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: 16px;
		padding: 32px 28px;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}
	.err-card h1 {
		margin: 0;
		font-size: 30px;
		line-height: 1.15;
	}
	.err-card p,
	.err-card ul {
		margin: 0;
	}
</style>
