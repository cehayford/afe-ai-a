<script lang="ts">
	// The confirmation after a form action: shown where it was, and read out by screen readers through the site's
	// announcer. Pass the action's result as `key`, so the same message after a second action is read again.
	import { announce } from '$lib/announce.svelte';

	let { message, key }: { message?: string | null; key?: unknown } = $props();

	$effect(() => {
		void key;
		if (message) announce(message);
	});
</script>

{#if message}<div class="notice ok"><b aria-hidden="true">✓</b><span>{message}</span></div>{/if}
