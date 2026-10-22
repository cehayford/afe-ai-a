<script lang="ts">
	import { enhance } from '$app/forms';
	import FormError from '$lib/components/FormError.svelte';
	import { date } from '$lib/format';

	let { data, form } = $props();
	const user = $derived(data.me!.user);

	function deviceName(ua: string): string {
		if (!ua) return 'Unknown device';
		const os = /Android/.test(ua) ? 'Android' : /iPhone|iPad/.test(ua) ? 'iPhone' : /Windows/.test(ua) ? 'Windows' : /Mac/.test(ua) ? 'Mac' : 'Device';
		const browser = /Edg\//.test(ua) ? 'Edge' : /Chrome\//.test(ua) ? 'Chrome' : /Firefox\//.test(ua) ? 'Firefox' : /Safari\//.test(ua) ? 'Safari' : 'browser';
		return `${browser} on ${os}`;
	}
</script>

<svelte:head><title>Your account · Afe</title></svelte:head>

<h2 class="sr">{user.name}</h2>
<p class="lede">{user.role_label}{user.phone ? ` · ${user.phone}` : ''}</p>

<div class="detail">
	<form class="box stack" method="post" action="?/profile" use:enhance>
		<h2>Profile</h2>
		<FormError message={form?.error} />
		{#if form?.saved}<p class="pill ok">Saved</p>{/if}
		<label for="display_name">Name</label>
		<input id="display_name" type="text" name="display_name" value={user.display_name} minlength="2" required />
		<label for="email">Email (optional, for receipts)</label>
		<input id="email" type="email" name="email" value={user.email ?? ''} />
		<label class="check" style="border: 0">
			<input type="checkbox" name="whatsapp_opt_in" checked={user.whatsapp_opt_in} />
			<span>Send my Afe updates on WhatsApp instead of SMS (payment updates come by SMS too)</span>
		</label>
		<button class="btn" type="submit">Save</button>
	</form>

	<aside>
		<div class="box">
			<h2>Security</h2>
			{#if ['landlord', 'agent', 'field_verifier', 'reviewer', 'admin'].includes(user.role)}
				<p>Authenticator app: <span class="pill {user.mfa_enabled ? 'ok' : 'warn'}">{user.mfa_enabled ? 'On' : 'Not set up'}</span></p>
			{/if}
			<h3>Signed in on</h3>
			<ul class="list">
				{#each data.devices as device}<li>{deviceName(device.device)} <span class="muted small">since {date(device.created_at)}</span></li>{/each}
			</ul>
			<!-- Signing out of this device is at the top of the page, beside the greeting (MyAfe). -->
			<form method="post" action="?/everywhere" use:enhance>
				<p><button class="btn secondary" type="submit">Sign out on all devices</button></p>
			</form>
		</div>
		<div class="box">
			<h2>Your data</h2>
			<p class="small">Download everything Afe holds about you, as a file you can keep.</p>
			<p><a class="btn secondary" href="/account/export" download>Download my data</a></p>
			<details open={Boolean(form?.closing)}>
				<summary class="small">Close my account</summary>
				<form class="stack" method="post" action="?/close" use:enhance style="margin-top: 8px">
					<p class="small">
						This removes your profile, phone, email, saved homes and message text, and signs you out everywhere. Some
						records are kept by law: payments, tenancies and verification decisions, with your name replaced by a
						reference. You can't close your account while a tenancy is in progress.
					</p>
					{#if form?.closing}<FormError message={form?.error} />{/if}
					{#if user.mfa_enabled}
						<label for="code">Authenticator code</label>
						<input id="code" name="code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" required />
					{:else if user.has_password}
						<label for="password">Password</label>
						<input id="password" name="password" type="password" autocomplete="current-password" required />
					{/if}
					<label for="confirm">Type DELETE to confirm</label>
					<input id="confirm" name="confirm" autocomplete="off" required pattern="[Dd][Ee][Ll][Ee][Tt][Ee]" />
					<button class="btn danger" type="submit">Close my account</button>
				</form>
			</details>
		</div>
	</aside>
</div>
