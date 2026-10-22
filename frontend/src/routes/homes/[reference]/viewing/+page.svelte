<script lang="ts">
	// "Book a viewing" from the Renter canvas: pick a day, pick a time, confirm. The landlord confirms
	// the request; the address and a reminder follow the day before.
	import { enhance } from '$app/forms';
	import FormError from '$lib/components/FormError.svelte';
	import CheckIcon from '$lib/components/ui/CheckIcon.svelte';
	import { dateTime } from '$lib/format';

	let { data, form } = $props();
	const listing = $derived(data.listing);
	const me = $derived(data.me!);

	// The next five days, from tomorrow, in Ghana time (UTC+0).
	const days = Array.from({ length: 5 }, (_, i) => {
		const d = new Date(Date.now() + (i + 1) * 86_400_000);
		return {
			value: d.toISOString().slice(0, 10),
			label: d.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'Africa/Accra' })
		};
	});
	const times = ['09:00', '11:00', '14:00', '16:00'];
	let day = $state(1);
	let time = $state(1);
	let busy = $state(false);
	const slot = $derived(`${days[day].label}, ${times[time]}`);
	const phone = $derived((me.user.phone ?? '').replace(/^\+233(\d{2})(\d{3})(\d{4})$/, '+233 $1 $2 $3'));
</script>

<svelte:head><title>Book a viewing · {listing.title} · Afe</title></svelte:head>

<div class="page-720 viewing">
	<a class="back" href="/homes/{listing.reference}">← {listing.title}</a>

	{#if form?.booked}
		<div class="done-card">
			<span class="done-mark"><CheckIcon size={22} weight={2.2} /></span>
			<h1>Viewing requested for {dateTime(form.booked.when)}</h1>
			<p>
				{listing.title}, {listing.area}. {listing.lister_name} will confirm the time. We'll send the exact address and a reminder
				{me.user.whatsapp_opt_in ? 'on WhatsApp' : 'by SMS'} the day before. The person who meets you should be the verified {listing.lister_role.toLowerCase()},
				{listing.lister_name}.
			</p>
			<div class="row">
				<a class="btn" href="/account/viewings">My viewings</a>
				<a class="btn quiet" href="/account/messages/{form.booked.thread}">Message {listing.lister_name}</a>
			</div>
		</div>
	{:else}
		<h1>Book a viewing</h1>
		<form
			class="pick"
			method="post"
			use:enhance={() => {
				busy = true;
				return async ({ update }) => {
					await update({ reset: false });
					busy = false;
				};
			}}
		>
			<FormError message={form?.error} />
			<fieldset>
				<legend>Day</legend>
				<div class="chips grid-110">
					{#each days as d, i}
						<label class="chip"><input type="radio" name="day" value={d.value} checked={i === day} onchange={() => (day = i)} />{d.label}</label>
					{/each}
				</div>
			</fieldset>
			<fieldset>
				<legend>Time</legend>
				<div class="chips grid-110">
					{#each times as t, i}
						<label class="chip"><input type="radio" name="time" value={t} checked={i === time} onchange={() => (time = i)} />{t}</label>
					{/each}
				</div>
			</fieldset>
			<div class="who">
				<span>{me.user.name}{phone ? ` · ${phone}` : ''}</span>
				<span class="muted">Reminder {me.user.whatsapp_opt_in ? 'by WhatsApp' : 'by SMS'}</span>
			</div>
			<button class="btn big" type="submit" disabled={busy}>Confirm {slot}</button>
		</form>
	{/if}
</div>

<style>
	.viewing {
		padding-top: 12px;
	}
	.viewing h1 {
		font-size: 34px;
		line-height: 1.1;
	}
	.pick {
		display: flex;
		flex-direction: column;
		gap: 24px;
	}
	fieldset {
		border: 0;
		padding: 0;
		margin: 0;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	legend {
		font-size: 14px;
		font-weight: 600;
		padding: 0;
		margin-bottom: 10px;
	}
	.who {
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: 10px;
		padding: 14px 16px;
		font-size: 14.5px;
		display: flex;
		justify-content: space-between;
		gap: 12px;
		flex-wrap: wrap;
	}
	.done-card {
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: 16px;
		padding: 28px;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}
	.done-card .done-mark {
		width: 48px;
		height: 48px;
	}
	.done-card h1 {
		font-size: 30px;
		line-height: 1.15;
		margin: 0;
	}
	.done-card p {
		margin: 0;
		font-size: 15.5px;
		color: var(--muted);
		line-height: 1.55;
	}
</style>
