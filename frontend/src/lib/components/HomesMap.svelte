<script lang="ts">
	// Search-results map from the Renter canvas: light-grey tiles, a price pin per home ("✓ 3.5k"),
	// the pin of the card under the pointer turns amber and comes to the front, clicking a pin opens
	// the home. Pins sit on each home's approximate position (the API never sends the exact one).
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import type { Listing } from '$lib/api/types';

	let { listings, hovered = null, onhover = () => {} }: { listings: Listing[]; hovered?: string | null; onhover?: (ref: string | null) => void } = $props();
	let el: HTMLDivElement;
	let L: typeof import('leaflet') | undefined;
	let map: import('leaflet').Map | undefined;
	let layer: import('leaflet').LayerGroup | undefined;
	const markers = new Map<string, import('leaflet').Marker>();

	const pinText = (l: Listing) => `✓ ${(l.rent_pesewas / 100_000).toFixed(1)}k`;

	function draw() {
		if (!L || !map || !layer) return;
		layer.clearLayers();
		markers.clear();
		const shown = listings.filter((l) => l.approx_lat !== null && l.approx_lng !== null);
		for (const l of shown) {
			const icon = L.divIcon({ html: `<span class="pin">${pinText(l)}</span>`, className: 'pin-wrap', iconSize: [0, 0] });
			const name = `${l.title}, verified, ${l.rent_display} a month`;
			const m = L.marker([l.approx_lat!, l.approx_lng!], { icon, title: name, keyboard: true })
				.on('click', () => goto(`/homes/${l.reference}`))
				.on('mouseover', () => onhover(l.reference))
				.on('mouseout', () => onhover(null))
				.addTo(layer);
			// A pin is a button (Leaflet pans to it on focus and opens it on Enter). Screen readers would read its
			// text, "✓ 3.5k", before its title, so it gets the full name; keyboard focus marks its card like hover.
			const pin = m.getElement();
			pin?.setAttribute('aria-label', name);
			pin?.addEventListener('focus', () => onhover(l.reference));
			pin?.addEventListener('blur', () => onhover(null));
			markers.set(l.reference, m);
		}
		if (shown.length) map.fitBounds(L.latLngBounds(shown.map((l) => [l.approx_lat!, l.approx_lng!])), { padding: [48, 48], maxZoom: 14 });
		else map.setView([5.6, -0.18], 12);
		mark(hovered);
	}

	function mark(ref: string | null) {
		for (const [r, m] of markers) {
			const on = r === ref;
			m.getElement()?.querySelector('.pin')?.classList.toggle('on', on);
			m.setZIndexOffset(on ? 1000 : 0);
		}
	}

	onMount(() => {
		(async () => {
			L = (await import('leaflet')).default;
			await import('leaflet/dist/leaflet.css');
			map = L.map(el, { scrollWheelZoom: false }).setView([5.6, -0.18], 12);
			L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
				attribution: 'Tiles &copy; Esri',
				maxZoom: 16
			}).addTo(map);
			layer = L.layerGroup().addTo(map);
			draw();
			setTimeout(() => map?.invalidateSize(), 100);
		})();
		return () => map?.remove();
	});

	$effect(() => {
		void listings;
		draw();
	});
	$effect(() => mark(hovered));
</script>

<div class="map-frame">
	<div class="map-el" bind:this={el} role="region" aria-label="Map of the homes in these results"></div>
	<span class="approx">Pins show the neighbourhood, not the exact home</span>
</div>

<style>
	.map-frame {
		position: relative;
		width: 100%;
		height: 100%;
	}
	.map-el {
		width: 100%;
		height: 100%;
		background: var(--tint);
	}
	.approx {
		position: absolute;
		left: 10px;
		bottom: 10px;
		z-index: 500;
		font: 11px var(--font-mono);
		background: rgba(255, 255, 255, 0.9);
		color: #56665f;
		padding: 3px 8px;
		border-radius: 4px;
	}
	:global(.pin-wrap) {
		background: none;
		border: 0;
	}
	:global(.pin) {
		transform: translate(-50%, -50%);
		display: inline-block;
		white-space: nowrap;
		padding: 5px 9px;
		border-radius: 99px;
		font: 600 13px var(--font-sans);
		box-shadow: 0 2px 6px rgba(21, 33, 30, 0.25);
		background: #0e4a3e;
		color: #fff;
		cursor: pointer;
	}
	:global(.pin.on) {
		background: #d9961a;
		color: #15211e;
	}
	/* The pin's wrapper is the focusable element but has no size: draw the ring on the pin. The tiles are always
	   light, so the ring is dark in both themes. */
	:global(.pin-wrap:focus-visible) {
		outline: none;
	}
	:global(.pin-wrap:focus-visible .pin) {
		outline: 2px solid #15211e;
		outline-offset: 2px;
	}
	/* Leaflet's blue link is too faint on its grey attribution strip. */
	.map-frame :global(.leaflet-control-attribution a) {
		color: #0e4a3e;
		text-decoration: underline;
	}
</style>
