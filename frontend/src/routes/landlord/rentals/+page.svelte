<script lang="ts">
	// Tenants and rent: the numbers first (as on the Landlord canvas's overview), then one card per
	// tenant with when rent is next due, and beside them the plan and the add-a-tenant form.
	import { enhance } from '$app/forms';
	import FormError from '$lib/components/FormError.svelte';
	import { cedis, date, day, ghs, initials } from '$lib/format';
	import Done from '$lib/components/Done.svelte';

	let { data, form } = $props();
	const today = new Date().toISOString().slice(0, 10);
	const week = new Date(Date.now() + 7 * 86_400_000).toISOString().slice(0, 10);
	const due = (d: string) => (d < today ? 'bad' : d <= week ? 'warn' : 'quiet');
	const active = $derived(data.rentals.filter((r) => r.status === 'active'));
	const late = $derived(active.filter((r) => r.next_due_date < today).length);
	const soon = $derived(active.filter((r) => r.next_due_date >= today && r.next_due_date <= week).length);
	const price = (k: string) => (data.plan.launch_offer ? 'Free' : `${cedis(ghs(data.plan.prices[k]))} / month`);
	let adding = $state(false);
</script>

<svelte:head><title>Tenants · Afe</title></svelte:head>

<a class="back" href="/landlord">← Dashboard</a>
<div class="page-head">
	<h1>Tenants and rent</h1>
	<p>Every tenant's rent in one place, with receipts, reminders, repairs and agreements. Tenants who came through Afe are added when their payment is released.</p>
</div>
<Done message={form?.planActive ? `Plan active. You can add up to ${data.plan.limit} tenants.` : null} key={form} />

<div class="stats-row">
	<div class="stat"><b>{active.length}</b><span>Active tenants</span></div>
	<div class="stat"><b>{soon}</b><span>Rent due this week</span></div>
	<div class="stat"><b style={late ? 'color: var(--crit)' : ''}>{late}</b><span>Rent overdue</span></div>
	<div class="stat"><b>{data.plan.used}/{data.plan.limit}</b><span>{data.plan.label} plan used</span></div>
</div>

<div class="detail">
	<div class="col">
		{#if data.rentals.length}
			<div class="pcard-list">
				{#each data.rentals as r (r.id)}
					<a class="pcard" href="/rentals/{r.id}">
						<span class="avatar">{initials(r.tenant_name)}</span>
						<div class="pcard-body">
							<div class="pcard-who"><b>{r.tenant_name}</b>{#if r.from_afe}<span class="tag soft">via Afe</span>{/if}{#if r.tenant_on_afe}<span>On Afe</span>{/if}</div>
							<div class="pcard-msg">{r.home || 'Home not on Afe'}</div>
							<span class="small muted">{cedis(ghs(r.rent_pesewas))} / month{r.pay_every_months > 1 ? `, paid ${r.pay_every_months} months at a time` : ''} · until {date(r.end_date)}</span>
						</div>
						{#if r.status === 'active'}
							<span class="pill {due(r.next_due_date)}">{r.next_due_date < today ? 'Overdue since' : 'Next due'} {day(r.next_due_date)}</span>
						{:else}
							<span class="pill quiet">Ended</span>
						{/if}
					</a>
				{/each}
			</div>
		{:else}
			<div class="empty">No tenants yet. Add one with the form, or offer a tenancy after a viewing.</div>
		{/if}

		{#if data.groups.length}
			<section class="lines" aria-labelledby="own-h">
				<div class="panel-head"><h2 id="own-h">Homes you manage, by owner</h2></div>
				{#each data.groups as g (g.owner)}
					<div class="line owner-row"><b>{g.owner}</b><span class="mono small muted">{g.homes.map((h) => h.address).join(' · ')}</span></div>
				{/each}
			</section>
		{/if}
	</div>

	<aside class="col">
		<div class="plan">
			<div class="row spread">
				<span class="label-mono">Your plan</span>
				{#if data.plan.launch_offer}<span class="tag soft">Launch offer</span>{/if}
			</div>
			<b class="plan-name">{data.plan.label}</b>
			<div class="meter" aria-hidden="true"><span style="width: {Math.min(100, (data.plan.used / Math.max(1, data.plan.limit)) * 100)}%"></span></div>
			<span class="small muted">{data.plan.used} of {data.plan.limit} tenants{data.plan.period_end ? ` · until ${date(data.plan.period_end)}` : ''}</span>
			<FormError message={form?.form === 'plan' ? form.error : null} />
			<form class="plan-opts" method="post" action="?/plan">
				<button class="plan-opt" class:on={data.plan.plan === 'standard'} type="submit" name="plan" value="standard"><b>Standard</b><span>{price('standard')}</span></button>
				<button class="plan-opt" class:on={data.plan.plan === 'pro'} type="submit" name="plan" value="pro"><b>Pro</b><span>{price('pro')}</span></button>
			</form>
		</div>

		<form
			class="box stack"
			method="post"
			action="?/add"
			use:enhance={() => {
				adding = true;
				return async ({ update }) => {
					await update();
					adding = false;
				};
			}}
		>
			<h2 class="add-h">Add a tenant</h2>
			<FormError message={form?.form === 'plan' ? null : form?.error} />
			<div><label for="tenant_name">Tenant's name</label><input id="tenant_name" name="tenant_name" required minlength="2" /></div>
			<div>
				<label for="tenant_phone">Tenant's phone <span class="muted" style="font-weight: 400">(optional)</span></label>
				<input id="tenant_phone" name="tenant_phone" inputmode="tel" placeholder="024 555 0142" />
				<p class="note" style="margin: 6px 0 0">If they have an Afe account on this number, they see their receipts and can raise repairs.</p>
			</div>
			<div>
				<label for="unit_id">Home</label>
				<select id="unit_id" name="unit_id">
					<option value="">Not on Afe</option>
					{#each data.homes as h (h.unit.id)}<option value={h.unit.id}>{h.unit.digital_address} · {h.unit.unit_label}</option>{/each}
				</select>
			</div>
			<div class="form-grid">
				<div><label for="rent_ghs">Rent a month (GH₵)</label><input id="rent_ghs" name="rent_ghs" type="number" min="1" required /></div>
				<div><label for="pay_every_months">Months per payment</label><input id="pay_every_months" name="pay_every_months" type="number" min="1" max="24" value="1" required /></div>
				<div><label for="start_date">Start</label><input id="start_date" name="start_date" type="date" required /></div>
				<div><label for="end_date">End</label><input id="end_date" name="end_date" type="date" required /></div>
			</div>
			<div><button class="btn md" type="submit" disabled={adding}>Add tenant</button></div>
		</form>
	</aside>
</div>

<style>
	.col {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}
	.owner-row {
		flex-direction: column;
		align-items: flex-start;
		gap: 2px;
	}
	.plan {
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: 12px;
		padding: 18px;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.plan-name {
		font: 700 24px var(--font-display);
		color: var(--brand);
	}
	.meter {
		height: 8px;
		border-radius: 99px;
		background: var(--tint);
		overflow: hidden;
	}
	.meter span {
		display: block;
		height: 100%;
		background: var(--brand);
		border-radius: 99px;
	}
	.plan-opts {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 8px;
		margin-top: 6px;
	}
	.plan-opt {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: 2px;
		padding: 12px 14px;
		border-radius: 8px;
		border: 1px solid var(--line);
		background: var(--surface);
		color: var(--ink);
		font: inherit;
		text-align: left;
		cursor: pointer;
		transition: border-color 0.15s ease, transform 0.16s ease-out;
	}
	.plan-opt:hover {
		border-color: var(--muted);
	}
	.plan-opt:active {
		transform: scale(0.98);
	}
	.plan-opt.on {
		border: 2px solid var(--brand);
		padding: 11px 13px;
		background: var(--tint);
	}
	.plan-opt b {
		font-weight: 600;
		font-size: 15px;
	}
	.plan-opt span {
		font-size: 13px;
		color: var(--muted);
	}
	.plan-opt:focus-visible {
		outline: 2px solid var(--amber);
		outline-offset: 2px;
	}
	.add-h {
		margin: 0;
		font-size: 20px;
	}
	@media (prefers-color-scheme: dark) {
		.plan-name {
			color: var(--accent);
		}
		.meter span {
			background: var(--accent);
		}
	}
</style>
