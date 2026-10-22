<script lang="ts">
	import { enhance } from '$app/forms';
	import FormError from '$lib/components/FormError.svelte';
	import MapPicker from '$lib/components/MapPicker.svelte';

	let { data, form } = $props();

	// svelte-ignore state_referenced_locally
	let areaSlug = $state(form?.area_slug ?? data.areas[0]?.slug ?? '');
	// svelte-ignore state_referenced_locally
	let lat = $state(form?.lat ?? '');
	// svelte-ignore state_referenced_locally
	let lng = $state(form?.lng ?? '');
	const area = $derived(data.areas.find((a) => a.slug === areaSlug));

	const types = [
		['single_room', 'Single room'],
		['chamber_and_hall', 'Chamber and hall'],
		['self_contained', 'Self-contained'],
		['apartment', 'Apartment'],
		['house', 'House']
	];
</script>

<svelte:head><title>Add a home · Afe</title></svelte:head>

<a class="back" href="/landlord">← Dashboard</a>
<h1>Add a home</h1>
<p class="lede">Each home is registered once. If you let several flats at one address, add each flat separately.</p>

<form class="box stack" method="post" use:enhance>
	<FormError message={form?.error} />
	<div class="form-grid">
		<div>
			<label for="area_slug">Area</label>
			<select id="area_slug" name="area_slug" bind:value={areaSlug}>
				{#each data.areas as a}<option value={a.slug}>{a.name}</option>{/each}
			</select>
		</div>
		<div>
			<label for="digital_address">GhanaPost digital address</label>
			<input id="digital_address" type="text" name="digital_address" placeholder="GA-183-8164" value={form?.digital_address ?? ''} required />
		</div>
		<div>
			<label for="unit_label">Which unit?</label>
			<input id="unit_label" type="text" name="unit_label" placeholder="Whole property, Flat 2B, Boys quarters" value={form?.unit_label ?? ''} />
		</div>
		<div>
			<label for="property_type">Type</label>
			<select id="property_type" name="property_type" value={form?.property_type ?? 'apartment'}>
				{#each types as [value, label]}<option {value}>{label}</option>{/each}
			</select>
		</div>
		<div>
			<label for="bedrooms">Bedrooms (0 for a single room)</label>
			<input id="bedrooms" type="number" name="bedrooms" min="0" max="20" value={form?.bedrooms ?? '1'} required />
		</div>
		<div>
			<label for="bathrooms">Bathrooms</label>
			<input id="bathrooms" type="number" name="bathrooms" min="0" max="20" value={form?.bathrooms ?? '1'} required />
		</div>
		<div class="wide">
			<label for="landmark">Landmark (how people find it)</label>
			<input id="landmark" type="text" name="landmark" maxlength="160" placeholder="Behind the Shell station, blue gate" value={form?.landmark ?? ''} />
		</div>
	</div>
	<label for="map-pin">Where is it?</label>
	<MapPicker {area} bind:lat bind:lng />
	<input type="hidden" name="lat" value={lat} id="map-pin" />
	<input type="hidden" name="lng" value={lng} />
	<p class="note">The exact pin is used only for Afe's visit. Renters see the area, not your address.</p>
	<button class="btn" type="submit">Add home</button>
</form>
