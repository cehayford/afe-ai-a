<script lang="ts">
	import AuthScreen from '$lib/components/auth/AuthScreen.svelte';

	let { data, form } = $props();
</script>

<svelte:head><title>Sign in · Afe</title></svelte:head>

<AuthScreen start="in" next={data.next} password={data.mode === 'password'} {form} />
