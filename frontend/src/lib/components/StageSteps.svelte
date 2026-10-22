<script lang="ts">
	import type { HomeStage } from '$lib/api/types';

	let { stage, feeRequired }: { stage: HomeStage; feeRequired: boolean } = $props();

	const all: [HomeStage, string][] = [
		['documents', 'Upload ownership or authority documents'],
		['fee', 'Pay the verification fee'],
		['visit', 'Afe verifier visits the home'],
		['review', 'Afe reviews the visit'],
		['verified', 'Verified: you can publish listings']
	];
	const steps = $derived(all.filter(([key]) => key !== 'fee' || feeRequired));
	const at = $derived(stage === 'rejected' ? steps.findIndex(([k]) => k === 'review') : steps.findIndex(([k]) => k === stage));
</script>

<ol class="steps">
	{#each steps as [key, label], i (key)}
		<li class:done={i < at || stage === 'verified'} class:now={i === at && stage !== 'verified'}>{label}</li>
	{/each}
</ol>
{#if stage === 'rejected'}
	<p class="flag">Afe could not verify this home. See the reason below, fix it, and ask for a new visit.</p>
{/if}
