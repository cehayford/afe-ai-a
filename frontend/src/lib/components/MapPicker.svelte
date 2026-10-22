<script lang="ts">
	// Pick a home's position on the map. Leaflet is loaded only on pages that need it.
	import { onMount } from 'svelte';
	import type { Area } from '$lib/api/types';

	let {
		area,
		lat = $bindable(''),
		lng = $bindable('')
	}: { area: Area | undefined; lat?: string; lng?: string } = $props();

	let el: HTMLDivElement;
	let status = $state('');
	let setPin: (la: number, ln: number) => void = () => {};
	let showArea: (a: Area | undefined) => void = () => {};

	onMount(() => {
		let map: import('leaflet').Map | undefined;
		(async () => {
			const L = (await import('leaflet')).default;
			await import('leaflet/dist/leaflet.css');
			map = L.map(el, { zoomControl: true }).setView([5.65, -0.17], 13);
			L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
				maxZoom: 19,
				attribution: '&copy; OpenStreetMap contributors'
			}).addTo(map);
			let marker: import('leaflet').CircleMarker | undefined;
			let outline: import('leaflet').Polygon | undefined;
			setPin = (la, ln) => {
				lat = la.toFixed(6);
				lng = ln.toFixed(6);
				if (marker) marker.setLatLng([la, ln]);
				else marker = L.circleMarker([la, ln], { radius: 9, color: '#0e4a3e', fillColor: '#d9961a', fillOpacity: 1 }).addTo(map!);
			};
			showArea = (a) => {
				outline?.remove();
				if (!a) return;
				outline = L.polygon(a.boundary, { color: '#0f6b57', weight: 2, fillOpacity: 0.05 }).addTo(map!);
				map!.fitBounds(outline.getBounds(), { padding: [12, 12] });
			};
			map.on('click', (e) => setPin(e.latlng.lat, e.latlng.lng));
			showArea(area);
			if (lat && lng) setPin(Number(lat), Number(lng));
		})();
		return () => map?.remove();
	});

	$effect(() => showArea(area));

	function useMyLocation() {
		if (!navigator.geolocation) {
			status = 'This browser cannot share its location.';
			return;
		}
		status = 'Finding your location…';
		navigator.geolocation.getCurrentPosition(
			(p) => {
				setPin(p.coords.latitude, p.coords.longitude);
				status = `Pin set (accurate to about ${Math.round(p.coords.accuracy)} m). Drag the map or tap to adjust.`;
			},
			() => (status = 'Could not get your location. Tap the map to place the pin.'),
			{ enableHighAccuracy: true, timeout: 15000 }
		);
	}
</script>

<div class="map" bind:this={el} role="application" aria-label="Map: tap where the home is"></div>
<div class="row" style="margin-top: 6px">
	<button class="btn secondary wraps" type="button" onclick={useMyLocation}>I'm at the home: use my location</button>
	<span class="small muted" role="status">{status || (lat ? `Pin: ${lat}, ${lng}` : 'Tap the map where the home is.')}</span>
</div>
