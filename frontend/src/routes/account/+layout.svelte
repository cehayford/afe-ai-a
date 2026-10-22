<script lang="ts">
	import { page } from '$app/state';
	import MyAfe from '$lib/components/shell/MyAfe.svelte';

	let { data, children } = $props();
	// A conversation is a page of its own; every other account page sits inside My Afe's tabs.
	const inThread = $derived(page.route.id === '/account/messages/[id]');
</script>

{#if inThread || !data.me}
	{@render children()}
{:else}
	<MyAfe me={data.me}>{@render children()}</MyAfe>
{/if}
