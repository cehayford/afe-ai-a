<script lang="ts">
	// Notifications: newest first, new ones marked with an amber dot.
	import { enhance } from '$app/forms';
	import { ago } from '$lib/format';

	let { data } = $props();
	const unread = $derived(data.notifications.filter((n) => !n.read_at).length);
</script>

<svelte:head><title>Notifications · Afe</title></svelte:head>

<h2 class="sr">Notifications</h2>
{#if data.notifications.length}
	<div class="row spread">
		<span class="muted" style="font-size: 14px">{unread ? `${unread} new` : 'All read'}</span>
		{#if unread}
			<form method="post" action="?/read" use:enhance><button class="btn quiet small" type="submit">Mark all as read</button></form>
		{/if}
	</div>
	<div class="lines">
		{#each data.notifications as n (n.id)}
			<a class="line n-row" class:unseen={!n.read_at} href={n.link || '#'}>
				{#if !n.read_at}<span class="dot-new" aria-label="New"></span>{/if}
				<span class="n-body"><b>{n.title}</b><span>{n.body}</span></span>
				<time class="mono small muted" datetime={n.created_at}>{ago(n.created_at)}</time>
			</a>
		{/each}
	</div>
{:else}
	<p class="muted" style="margin: 0; font-size: 15px">Nothing yet. We'll tell you here, and by SMS or WhatsApp, when something happens.</p>
{/if}

<style>
	.n-row {
		align-items: flex-start;
		color: var(--ink);
	}
	.n-row:hover {
		background: var(--paper);
		color: var(--ink);
	}
	.n-row .dot-new {
		margin-top: 7px;
	}
	.n-body {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 2px;
		font-size: 14.5px;
	}
	.n-body b {
		font-weight: 600;
	}
	.unseen {
		background: var(--paper);
	}
</style>
