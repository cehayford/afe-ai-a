<script lang="ts">
	// Payouts tab from the Landlord canvas: what Afe holds for you, where it will be paid, and each
	// tenant's payment with its state. Changing the account needs an authenticator code.
	import { enhance } from '$app/forms';
	import FormError from '$lib/components/FormError.svelte';
	import { cedis, date, dateTime, ghs } from '$lib/format';

	let { data, form } = $props();
	const payee = $derived(data.payee);
	const waiting = $derived(payee && new Date(payee.usable_from).getTime() > Date.now());
	const CHANNELS: [string, string][] = [
		['momo_mtn', 'MTN Mobile Money'],
		['momo_telecel', 'Telecel Cash'],
		['momo_at', 'AT Money'],
		['bank', 'Bank account']
	];
	const HELD = ['funded', 'disputed', 'release_pending', 'releasing'];
	const held = $derived(data.payouts.filter((t) => HELD.includes(t.status)).reduce((s, t) => s + t.payout_pesewas, 0));
	const stateOf = (s: string): [string, string] =>
		HELD.includes(s) ? (s === 'disputed' ? ['On hold', 'bad'] : ['Held', 'warn']) : s === 'released' ? ['Released', 'ok'] : ['Refunded', 'quiet'];
	let changing = $state(false);
</script>

<svelte:head><title>Payouts · Afe</title></svelte:head>

<h1>Payouts</h1>

<div class="two">
	<div class="held">
		<span class="k">Held for you</span>
		<span class="v">{ghs(held).replace('GH₵', 'GH₵ ')}</span>
		<span class="s">Released when each tenant confirms move-in</span>
	</div>
	<div class="acct">
		<span class="k">Payout account</span>
		{#if payee}
			<span class="v2">{payee.masked}</span>
			<span class="ok-line">✓ {payee.account_name}, name-matched</span>
		{:else}
			<span class="v2">Not added yet</span>
			<span class="s">Add the mobile money or bank account in the name on your Ghana Card.</span>
		{/if}
	</div>
</div>

{#if waiting && payee}
	<p class="flag medium" style="margin: 0">New account: payments go here from {dateTime(payee.usable_from)}. If you didn't make this change, call Afe now.</p>
{/if}
{#if form?.saved}<p class="result">Saved. We've sent you an SMS about the change.</p>{/if}

{#if data.payouts.length}
	<div class="lines">
		{#each data.payouts as t (t.reference)}
			{@const [label, tone] = stateOf(t.status)}
			<a class="line pay" href="/tenancies/{t.reference}">
				<div class="who"><b>{t.tenant_name}</b><span>{t.listing_reference} · {date(t.funded_at ?? t.accepted_at)}</span></div>
				<div class="amt"><span class="num">{cedis(t.payout_display)}</span><span class="pill {tone}">{label}</span></div>
			</a>
		{/each}
	</div>
{/if}

<details class="box" open={!payee || changing || Boolean(form?.error)}>
	<summary>{payee ? 'Change payout account' : 'Add your payout account'}</summary>
	<form class="stack" method="post" use:enhance style="margin-top: 14px; max-width: 520px">
		<FormError message={form?.error} />
		<div class="form-grid">
			<div>
				<label for="channel">Network</label>
				<select id="channel" name="channel" required>
					{#each CHANNELS as [k, label]}<option value={k} selected={(form?.channel ?? payee?.channel) === k}>{label}</option>{/each}
				</select>
			</div>
			<div>
				<label for="account_number">Wallet or account number</label>
				<input id="account_number" name="account_number" inputmode="numeric" autocomplete="off" required value={form?.account_number ?? ''} placeholder="24 555 0142" />
			</div>
		</div>
		<label for="code">Authenticator code</label>
		<input id="code" name="code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" pattern="[0-9]{6}" style="max-width: 200px" />
		<p class="note" style="margin: 0">If you change this account later, payouts pause for 72 hours and we confirm the change with you by phone.</p>
		<div><button class="btn md" type="submit" onclick={() => (changing = true)}>Save payout account</button></div>
	</form>
</details>
<p class="note" style="margin: 0">Verification fees and featured listings you paid are under <a href="/account/payments">Fees paid</a>.</p>

<style>
	.two {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
		gap: 12px;
	}
	.held,
	.acct {
		border-radius: 12px;
		padding: 18px;
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
	.held {
		background: var(--ok-soft);
	}
	.acct {
		background: var(--surface);
		border: 1px solid var(--line);
	}
	.k {
		font-size: 13.5px;
		font-weight: 600;
		color: var(--muted);
	}
	.held .k {
		color: var(--ok);
	}
	.v {
		font: 700 28px var(--font-display);
		color: var(--brand);
		font-variant-numeric: tabular-nums;
	}
	.v2 {
		font-size: 16px;
		font-weight: 600;
	}
	.s {
		font-size: 13px;
	}
	.ok-line {
		font-size: 13px;
		color: var(--ok);
	}
	.pay {
		justify-content: space-between;
		flex-wrap: wrap;
		color: var(--ink);
		padding-block: 14px;
		padding-inline: 18px;
	}
	.pay:hover {
		background: var(--paper);
		color: var(--ink);
	}
	.who {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.who span {
		font-size: 13px;
		color: var(--muted);
	}
	.amt {
		display: flex;
		gap: 12px;
		align-items: center;
		font-weight: 600;
	}
	@media (prefers-color-scheme: dark) {
		.v {
			color: var(--accent);
		}
	}
</style>
