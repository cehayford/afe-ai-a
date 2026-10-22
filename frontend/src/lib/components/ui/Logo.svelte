<script lang="ts">
	// Mark + lowercase "afe" wordmark in Bricolage Grotesque, with an optional area tag
	// ("Landlords", "Review desk") in mono amber, as on the header canvases.
	import AfeMark from './AfeMark.svelte';

	let {
		href = '/',
		mark = 32,
		text = 24,
		theme = 'auto',
		tag = '',
		label = 'Afe home'
	}: { href?: string | null; mark?: number; text?: number; theme?: 'auto' | 'light' | 'dark'; tag?: string; label?: string } = $props();
</script>

{#if href}
	<a class="afe-logo" {href} aria-label={label}>
		<AfeMark size={mark} {theme} />
		<span class="word" style:font-size="{text}px">afe</span>
		{#if tag}<span class="area">{tag}</span>{/if}
	</a>
{:else}
	<span class="afe-logo">
		<AfeMark size={mark} {theme} />
		<span class="word" style:font-size="{text}px">afe</span>
		{#if tag}<span class="area">{tag}</span>{/if}
	</span>
{/if}

<style>
	.afe-logo {
		display: flex;
		align-items: center;
		gap: 10px;
		flex: 0 0 auto;
		color: inherit;
		text-decoration: none;
	}
	.afe-logo:hover {
		color: inherit;
	}
	.word {
		font-family: var(--font-display);
		font-weight: 700;
		letter-spacing: -0.02em;
		line-height: 1;
	}
	.area {
		font-family: var(--font-mono);
		font-size: 11px;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: #f0b84a;
	}
</style>
