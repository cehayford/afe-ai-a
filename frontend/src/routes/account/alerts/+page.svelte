<script lang="ts">
	// Search alerts: each saved search, how it reaches you, and Stop.
	import { enhance } from '$app/forms';
	import FormError from '$lib/components/FormError.svelte';
	import { date } from '$lib/format';

	let { data, form } = $props();
	const CHANNEL: Record<string, string> = { sms: 'By SMS', whatsapp: 'On WhatsApp', in_app: 'In your Afe inbox' };
</script>

<svelte:head><title>Search alerts · Afe</title></svelte:head>

<h2 class="sr">Search alerts</h2>
<p class="muted" style="margin: 0; font-size: 15px; max-width: 44em">
	We tell you once when a verified home that matches is listed. At most 3 a day come by SMS or WhatsApp; the rest wait in
	your Afe inbox.
</p>
<FormError message={form?.error} />
{#if form?.stopped}<p class="result">Alert stopped.</p>{/if}

{#if data.searches.length}
	<div class="lines">
		{#each data.searches as s (s.id)}
			<div class="line alert-row">
				<span class="a-body"><b>{s.description}</b><span class="small muted">{CHANNEL[s.channel]} · since {date(s.created_at)} · {s.alerts_sent} sent</span></span>
				<form method="post" action="?/stop" use:enhance>
					<input type="hidden" name="id" value={s.id} />
					<button class="btn quiet small" type="submit">Stop</button>
				</form>
			</div>
		{/each}
	</div>
{:else}
	<div class="empty">No alerts yet. Search for homes, then choose "Save this search". On WhatsApp, send <span class="mono">ALERT 2 bed East Legon under 5000</span>.</div>
{/if}
<a class="btn secondary md" style="align-self: flex-start" href="/homes">Search homes</a>

<style>
	.alert-row {
		flex-wrap: wrap;
	}
	.a-body {
		flex: 1 1 240px;
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.a-body b {
		font-weight: 600;
	}
</style>
