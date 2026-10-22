<script lang="ts">
	import AuthScreen from '$lib/components/auth/AuthScreen.svelte';

	let { data, form } = $props();
</script>

<svelte:head><title>Create an account · Afe</title></svelte:head>

<AuthScreen start="up" initialRole={data.role} freeVerification={data.freeVerification} {form} />
