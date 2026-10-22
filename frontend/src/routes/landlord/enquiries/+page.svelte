<script lang="ts">
	// Enquiries tab from the Landlord canvas: who asked, about which home, and when, with the next step.
	import ViewingActions from '$lib/components/ViewingActions.svelte';
	import { ago, dateTime, initials } from '$lib/format';

	let { data } = $props();
</script>

<svelte:head><title>Enquiries · Afe</title></svelte:head>

<h1>Enquiries</h1>

{#if data.requests.length}
	<h2 class="sub">Viewing requests</h2>
	<div class="pcard-list">
		{#each data.requests as v (v.id)}
			<div class="pcard fresh">
				<span class="avatar">{initials(v.other_name)}</span>
				<div class="pcard-body">
					<div class="pcard-who"><b>{v.other_name}</b><span>{v.listing_reference} · wants to view {dateTime(v.requested_for)}</span></div>
					{#if v.note}<div class="pcard-msg">{v.note}</div>{/if}
				</div>
				<ViewingActions viewing={v} back="/landlord/enquiries" />
			</div>
		{/each}
	</div>
	<h2 class="sub">Messages</h2>
{/if}

<div class="pcard-list">
	{#each data.threads as t (t.id)}
		<a class="pcard" class:fresh={t.unread} href="/account/messages/{t.id}">
			<span class="avatar">{initials(t.other_name)}</span>
			<div class="pcard-body">
				<div class="pcard-who"><b>{t.other_name}</b><span>{t.listing_reference} · {ago(t.last_message_at)}</span>{#if t.unread}<span class="pill warn">New</span>{/if}</div>
				<div class="pcard-msg">Asked about {t.listing_title}</div>
			</div>
			<span class="btn secondary sm">{t.unread ? 'Reply' : 'Open'}</span>
		</a>
	{:else}
		<p class="muted" style="margin: 0">No enquiries yet. They appear here when a renter asks about one of your homes.</p>
	{/each}
</div>
<p class="note" style="margin: 0">Phone numbers are shared once a viewing is booked through Afe.</p>

<style>
	.sub {
		margin: 4px 0 0;
		font-size: 18px;
	}
</style>
