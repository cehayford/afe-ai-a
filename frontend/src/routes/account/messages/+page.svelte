<script lang="ts">
	// Messages: one card per conversation, who and which home, new ones outlined (the Landlord
	// canvas's Enquiries style, used for renters too).
	import { ago, initials } from '$lib/format';

	let { data } = $props();
</script>

<svelte:head><title>Messages · Afe</title></svelte:head>

<h2 class="sr">Messages</h2>
{#if data.threads.length}
	<div class="pcard-list">
		{#each data.threads as t (t.id)}
			<a class="pcard" class:fresh={t.unread} href="/account/messages/{t.id}">
				<span class="avatar">{initials(t.other_name)}</span>
				<div class="pcard-body">
					<div class="pcard-who">
						<b>{t.other_name}</b><span>{t.listing_reference} · {ago(t.last_message_at)}</span>
						{#if t.unread}<span class="pill warn">New</span>{/if}
					</div>
					<div class="pcard-msg">{t.role === 'renter' ? 'You asked about' : 'Asked about'} {t.listing_title}</div>
				</div>
				<span class="btn secondary sm">{t.unread ? 'Reply' : 'Open'}</span>
			</a>
		{/each}
	</div>
	<p class="note" style="margin: 0">Keep the conversation on Afe. Phone numbers are shared once a viewing is booked.</p>
{:else}
	<p class="muted" style="margin: 0; font-size: 15px">No conversations yet. Ask a landlord a question from any verified home. <a href="/homes">Find a home</a></p>
{/if}
