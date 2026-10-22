<script lang="ts">
	// The verifier app from the "Afe Verifier" canvas: a phone-width column on a grey-green canvas,
	// Afe green header with the amber rule, back arrow inside a visit.
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import AfeMark from '$lib/components/ui/AfeMark.svelte';

	let { data, children } = $props();
	let online = $state(true);

	onMount(() => {
		online = navigator.onLine;
		const update = () => (online = navigator.onLine);
		window.addEventListener('online', update);
		window.addEventListener('offline', update);
		return () => {
			window.removeEventListener('online', update);
			window.removeEventListener('offline', update);
		};
	});

	const head = $derived((page.data as { head?: { title: string; sub: string } }).head);
	const inside = $derived(page.url.pathname !== '/field');
	const today = new Date().toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'Africa/Accra' });
</script>

<div class="canvas">
	<div class="phone">
		<header>
			{#if inside}<a class="back-arrow" href="/field" aria-label="Back to today's visits">←</a>{/if}
			<AfeMark size={28} theme="dark" />
			<div class="titles">
				<span class="t">{head?.title ?? 'Afe Verify'}</span>
				<span class="s">{head?.sub ?? `${today} · ${data.me?.user.name ?? ''}`}</span>
			</div>
			<span class="net" class:off={!online} role="status">{online ? 'Online' : 'Offline'}</span>
		</header>
		{#if !online}<p class="offline">Offline: photos and answers wait on this phone and send when you're back online.</p>{/if}
		<main id="main" tabindex="-1">
			{@render children()}
		</main>
	</div>
</div>

<style>
	.canvas {
		min-height: 100vh;
		display: flex;
		justify-content: center;
		background: var(--canvas);
	}
	.phone {
		width: 100%;
		max-width: 420px;
		min-height: 100vh;
		background: var(--paper);
		display: flex;
		flex-direction: column;
		box-shadow: 0 0 0 1px var(--line);
	}
	header {
		position: sticky;
		top: 0;
		z-index: 5;
		background: var(--brand);
		color: #fff;
		padding: 14px 16px;
		display: flex;
		align-items: center;
		gap: 12px;
		border-bottom: 4px solid var(--amber);
	}
	.back-arrow {
		width: 44px;
		height: 44px;
		margin-left: -8px;
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: 8px;
		color: #fff;
		font-size: 22px;
	}
	.back-arrow:hover {
		background: rgba(255, 255, 255, 0.08);
		color: #fff;
	}
	.titles {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
	}
	.t {
		font: 700 18px var(--font-display);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.s {
		font: 11px var(--font-mono);
		color: var(--brand-ink-soft);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.net {
		font: 11px var(--font-mono);
		padding: 3px 8px;
		border-radius: 99px;
		background: rgba(255, 255, 255, 0.14);
	}
	.net.off {
		background: var(--amber);
		color: var(--on-amber);
	}
	.offline {
		margin: 0;
		padding: 10px 16px;
		background: var(--amber-soft);
		font-size: 13.5px;
	}
	main {
		padding: 16px 16px 40px;
		display: flex;
		flex-direction: column;
		gap: 12px;
	}
	main :global(h1) {
		font-size: 24px;
		margin: 0;
	}
	main :global(h2) {
		font-size: 18px;
		margin: 8px 0 0;
	}
</style>
