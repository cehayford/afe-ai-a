<script lang="ts">
	// "My Afe", the renter dashboard frame from the Renter canvas: "Hello, <name>" and underline tabs.
	// Saved, Viewings and Payments come first, as in the design; the rest of the account follows.
	// Sign out sits beside the greeting, so it is at the top of every tab.
	import type { Snippet } from 'svelte';
	import { page } from '$app/state';
	import type { Me } from '$lib/api/types';

	let { me, children }: { me: Me; children: Snippet } = $props();

	const path = $derived(page.url.pathname);
	const renter = $derived(me.user.role === 'renter');
	const tabs = $derived(
		[
			renter && ['/account/saved', 'Saved'],
			['/account/viewings', 'Viewings'],
			renter && ['/tenancies', 'Payments'],
			['/account/messages', 'Messages'],
			renter && ['/account/home', 'My home'],
			renter && ['/account/alerts', 'Search alerts'],
			['/account/notifications', `Notifications${me.unread_notifications ? ` (${me.unread_notifications})` : ''}`],
			!renter && ['/account/payments', 'Fees paid'],
			['/account/appeals', 'Appeals'],
			['/account', 'Account']
		].filter(Boolean) as [string, string][]
	);
	const first = $derived(me.user.name.split(/\s+/)[0] || me.user.name);
</script>

<div class="page-1000 my-afe">
	<div class="my-afe-head">
		<h1>Hello, {first}</h1>
		<!-- A plain form post (no enhance): the page reloads, so nothing of the session stays in the browser. -->
		<form method="post" action="/signout"><button class="btn secondary sm" type="submit">Sign out</button></form>
	</div>
	<nav class="tabs" aria-label="My Afe">
		{#each tabs as [href, label]}<a {href} aria-current={path === href ? 'page' : undefined}>{label}</a>{/each}
	</nav>
	<div class="tab-body">{@render children()}</div>
</div>

<style>
	.my-afe {
		padding-top: 12px;
	}
	.my-afe-head {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
	}
	.my-afe h1 {
		font-size: 34px;
		line-height: 1.1;
		margin: 0;
	}
	.my-afe .tabs {
		margin: 0;
	}
	.tab-body {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}
	.tab-body :global(> h2:first-child) {
		margin-top: 0;
	}
</style>
