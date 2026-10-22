<script lang="ts">
	// One conversation: who, which home, any viewings between you, the messages, and a reply box.
	import { enhance } from '$app/forms';
	import FormError from '$lib/components/FormError.svelte';
	import ViewingActions from '$lib/components/ViewingActions.svelte';
	import { dateTime, initials, statusLabel } from '$lib/format';
	import { hydrated } from '$lib/hydrated.svelte';
	const js = hydrated();

	let { data, form } = $props();
	const t = $derived(data.thread);
	let draft = $state('');
	let sending = $state(false);
	const TONE: Record<string, string> = { requested: 'warn', confirmed: '', completed: 'ok', declined: 'quiet', cancelled: 'quiet', no_show: 'bad' };
</script>

<svelte:head><title>{t.other_name} · Messages · Afe</title></svelte:head>

<div class="page-720 thread">
	<a class="back" href={data.me?.user.role === 'landlord' || data.me?.user.role === 'agent' ? '/landlord/enquiries' : '/account/messages'}>← Messages</a>

	<div class="who">
		<span class="avatar lg">{initials(t.other_name)}</span>
		<div>
			<h1>{t.other_name}</h1>
			<a class="about" href="/homes/{t.listing_reference}">{t.listing_title} · <span class="mono">{t.listing_reference}</span></a>
		</div>
	</div>

	{#each t.viewings as v (v.id)}
		<div class="viewing">
			<div class="row spread">
				<span><span class="label-mono">Viewing</span><br /><b>{dateTime(v.requested_for)}</b></span>
				<span class="pill {TONE[v.status] ?? ''}">{statusLabel(v.status)}</span>
			</div>
			{#if v.note}<p class="small muted" style="margin: 0">“{v.note}”</p>{/if}
			<ViewingActions viewing={v} back="/account/messages/{t.id}" />
		</div>
	{/each}

	<div class="chat" style="margin: 0" aria-live="polite">
		{#each t.messages as m (m.id)}
			<div class="bubble" class:mine={m.mine} class:system={m.system}>
				{m.body}
				{#if m.warning}<span class="warn">{m.warning}</span>{/if}
				<span class="meta">{m.system ? '' : `${m.mine ? 'You' : m.sender} · `}{dateTime(m.created_at)}</span>
			</div>
		{:else}
			<p class="muted small" style="text-align: center">No messages yet.</p>
		{/each}
	</div>

	<form
		class="reply"
		method="post"
		action="?/send"
		use:enhance={() => {
			sending = true;
			return async ({ update, result }) => {
				await update();
				sending = false;
				if (result.type === 'success') draft = '';
			};
		}}
	>
		<FormError message={form?.error} />
		<label for="body" class="sr">Your message</label>
		<textarea id="body" name="body" maxlength="2000" required bind:value={draft} placeholder="Write a message"></textarea>
		<div class="row spread">
			<span class="note">Afe never asks you to pay before a viewing. Keep payments and contact on Afe.</span>
			<button class="btn md" type="submit" disabled={sending || (js.on && !draft.trim())}>{sending ? 'Sending…' : 'Send'}</button>
		</div>
	</form>
</div>

<style>
	.thread {
		padding-top: 12px;
		gap: 18px;
	}
	.who {
		display: flex;
		gap: 14px;
		align-items: center;
	}
	.who h1 {
		margin: 0;
		font-size: 28px;
	}
	.about {
		font-size: 14.5px;
	}
	.viewing {
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: 12px;
		padding: 16px;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.reply {
		position: sticky;
		bottom: 0;
		display: flex;
		flex-direction: column;
		gap: 10px;
		padding: 14px;
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: 12px;
	}
	.reply textarea {
		min-height: 72px;
	}
</style>
