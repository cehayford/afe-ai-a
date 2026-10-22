<script lang="ts">
	// The design's check: a 12-unit polyline in the current text colour.
	let { size = 12, weight = 2 }: { size?: number; weight?: number } = $props();
</script>

<svg width={size} height={size} viewBox="0 0 12 12" aria-hidden="true" focusable="false"
	><polyline points="2,6.5 5,9 10,3" fill="none" stroke="currentColor" stroke-width={weight} stroke-linecap="round" stroke-linejoin="round" /></svg
>
