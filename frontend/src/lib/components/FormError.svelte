<script lang="ts">
	let { message }: { message?: string | null } = $props();
</script>

{#if message}
	<ul class="errorlist" role="alert"><li>{message}</li></ul>
{/if}
