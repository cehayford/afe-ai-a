<script lang="ts">
	// Landlord overview from the Landlord canvas: a greeting, four numbers, upcoming viewings, then the
	// homes being verified or listed.
	import { bedrooms, date, dateTime, ghs, statusLabel } from '$lib/format';

	let { data } = $props();
	const me = $derived(data.me!);
	const v = $derived(me.verification);
	const hour = Number(new Date().toLocaleString('en-GB', { hour: 'numeric', hour12: false, timeZone: 'Africa/Accra' }));
	const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';
	const first = $derived(me.user.name.split(/\s+/)[0]);

	const stageText: Record<string, [string, string]> = {
		documents: ['Upload documents', 'warn'],
		fee: ['Pay the verification fee', 'warn'],
		visit: ['Awaiting visit', 'warn'],
		review: ['Afe is reviewing', ''],
		verified: ['Verified', 'ok'],
		rejected: ['Not verified', 'bad']
	};
</script>

<svelte:head><title>Dashboard · Afe</title></svelte:head>

<h1>{greeting}, {first}</h1>

{#if data.pricing.launch_offer}
	<div class="notice" style="margin: 0"><span class="tag amber">Launch offer</span><span>Verification, protected payments and featured listings are free until {date(data.pricing.free_until)}.</span></div>
{/if}
{#if !v?.verified}
	<div class="notice" style="margin: 0">
		{#if v?.identity_check === 'passed'}
			<strong>Your Ghana Card check passed.</strong><span>Afe is reviewing it. You can add homes in the meantime.</span>
		{:else if v?.latest_decision === 'rejected'}
			<strong>Afe could not verify your identity.</strong><a href="/landlord/verify">Check your Ghana Card details again</a>
		{:else}
			<strong>First, get verified.</strong><span>Renters only see homes from verified landlords and agents.</span><a href="/landlord/verify">Start verification</a>
		{/if}
	</div>
{/if}

<div class="stats-row">
	<div class="stat"><b>{data.stats.live}</b><span>Live listings</span></div>
	<div class="stat"><b>{data.stats.enquiries}</b><span>Enquiries this week</span></div>
	<div class="stat"><b>{data.stats.booked}</b><span>Viewings booked</span></div>
	<div class="stat"><b>{ghs(data.stats.held).replace('GH₵', 'GH₵ ')}</b><span>Held for you</span></div>
</div>

<section class="lines" aria-labelledby="up-h">
	<div class="panel-head"><h2 id="up-h" class="up-title">Upcoming viewings</h2>{#if data.toAnswer.length}<a class="pill warn" href="/landlord/enquiries">{data.toAnswer.length} to answer</a>{/if}</div>
	{#each data.upcoming.slice(0, 6) as w (w.id)}
		<a class="line vrow" href="/account/messages/{w.thread_id}">
			<span><b>{dateTime(w.requested_for)}</b> · {w.other_name}{w.status === 'requested' ? ' (waiting for you)' : ''}</span>
			<span class="muted">{w.listing_reference} · {w.listing_title}</span>
		</a>
	{:else}
		<div class="line muted">No viewings booked yet.</div>
	{/each}
</section>

<div class="row spread">
	<h2 class="sect">Homes ({data.homes.length})</h2>
	<a class="btn md" href="/landlord/homes/new">Add a home</a>
</div>
{#if data.homes.length}
	<div class="homes">
		{#each data.homes as home (home.unit.id)}
			{@const [label, tone] = stageText[home.stage]}
			<a class="home" href="/landlord/homes/{home.unit.id}">
				<div class="row spread">
					<b>{home.unit.digital_address} · {home.unit.unit_label}</b>
					<span class="pill {tone}">{label}</span>
				</div>
				<span class="muted small">{home.unit.area.name} · {bedrooms(home.unit.bedrooms)} · {home.unit.property_type_label}{home.visit_scheduled_for ? ` · visit on ${date(home.visit_scheduled_for)}` : ''}</span>
				{#each home.listings as listing}
					<span class="small"><span class="mono">{listing.reference}</span> {listing.title} · {statusLabel(listing.status)}</span>
				{/each}
			</a>
		{/each}
	</div>
{:else}
	<p class="empty">No homes yet. Add your first home to start verification.</p>
{/if}

<style>
	.vrow {
		justify-content: space-between;
		flex-wrap: wrap;
		font-size: 14.5px;
		color: var(--ink);
	}
	.vrow:hover {
		background: var(--paper);
		color: var(--ink);
	}
	.up-title {
		font-size: 18px;
	}
	.sect {
		margin: 8px 0 0;
		font-size: 22px;
	}
	.homes {
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.home {
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: 12px;
		padding: 16px;
		display: flex;
		flex-direction: column;
		gap: 6px;
		color: var(--ink);
	}
	.home:hover {
		border-color: var(--brand);
		color: var(--ink);
	}
	.home .mono {
		font-size: 12px;
		color: var(--muted);
	}
</style>
