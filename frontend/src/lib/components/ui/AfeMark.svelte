<script lang="ts">
	// The Afe mark from the "Afe Mark" canvas, drawn on a 100-unit grid so it scales cleanly.
	// c = lettermark tile (the logo), a = verified home, b = held safe (keyhole).
	// At 32px and below the strokes get heavier and the "a" bigger, as the canvas specifies.
	// theme "auto" follows the page (light/dark tokens); "dark" is for marks on brand or dark surfaces.
	let {
		variant = 'c',
		size = 32,
		theme = 'auto'
	}: { variant?: 'a' | 'b' | 'c'; size?: number; theme?: 'auto' | 'light' | 'dark' } = $props();

	const sm = $derived(size <= 32);
	const house = $derived(theme === 'light' ? '#0e4a3e' : theme === 'dark' ? '#0f6b57' : 'var(--mark-tile)');
	const amber = $derived(theme === 'light' ? '#d9961a' : theme === 'dark' ? '#f0b84a' : 'var(--mark-roof)');
	const sw = $derived(variant === 'a' ? (sm ? 13 : 10) : sm ? 10 : 7);
</script>

<svg class="afe-mark" width={size} height={size} viewBox="0 0 100 100" aria-hidden="true" focusable="false">
	{#if variant === 'c'}
		<rect x="0" y="0" width="100" height="100" rx="24" style:fill={house} />
		<polyline points={sm ? '24,33 50,18 76,33' : '28,34 50,22 72,34'} fill="none" style:stroke={amber} stroke-width={sw} stroke-linecap="round" stroke-linejoin="round" />
		<text x="50" y={sm ? 86 : 81} text-anchor="middle" font-size={sm ? 66 : 58} font-weight="700" fill="#ffffff" style:font-family="var(--font-display)">a</text>
	{:else}
		<polygon points="50,12 88,43 88,88 12,88 12,43" style:fill={house} style:stroke={house} stroke-width="8" stroke-linejoin="round" />
		{#if variant === 'a'}
			<polyline points={sm ? '30,63 45,77 70,50' : '32,64 45,76 68,52'} fill="none" style:stroke={amber} stroke-width={sw} stroke-linecap="round" stroke-linejoin="round" />
		{:else}
			<circle cx="50" cy={sm ? 58 : 59} r={sm ? 13 : 10} style:fill={amber} />
			<rect x={sm ? 43.5 : 45.5} y="62" width={sm ? 13 : 9} height={sm ? 20 : 18} rx="3" style:fill={amber} />
		{/if}
	{/if}
</svg>

<style>
	.afe-mark {
		display: block;
		flex: none;
		overflow: visible;
	}
</style>
