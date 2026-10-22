<script lang="ts">
	// Staff as a table (the canvas's table style): who, role (a select whose Save wakes up only when
	// the role changes), phone, authenticator, and on/off. The add form sits beside it.
	import { enhance } from '$app/forms';
	import FormError from '$lib/components/FormError.svelte';
	import { date, initials } from '$lib/format';
	import { hydrated } from '$lib/hydrated.svelte';
	import Done from '$lib/components/Done.svelte';

	const js = hydrated();

	let { data, form } = $props();
	const ROLES: [string, string][] = [
		['field_verifier', 'Field verifier'],
		['reviewer', 'Reviewer'],
		['admin', 'Admin']
	];
	let picked = $state<Record<number, string>>({});
	let busy = $state(false);
	const submit = () => {
		busy = true;
		return async ({ update }: { update: () => Promise<void> }) => {
			await update();
			busy = false;
			picked = {};
		};
	};
</script>

<svelte:head><title>Staff · Afe review</title></svelte:head>

<div class="page-head">
	<h1>Staff</h1>
	<p>New staff sign in with a code sent to their phone, then set up an authenticator app. Turning an account off signs it out everywhere at once.</p>
</div>
<FormError message={form?.error} />
<Done message={form?.done} key={form} />

<div class="detail">
	<div class="scroll">
		<table class="q wide-t">
			<thead><tr><th>Name</th><th>Role</th><th>Authenticator</th><th>Since</th><th><span class="sr">On or off</span></th></tr></thead>
			<tbody>
				{#each data.staff as person (person.id)}
					<tr class:off={!person.is_active}>
						<td>
							<span class="who"><span class="avatar sm-av">{initials(person.name)}</span><span><b>{person.name}</b><br /><span class="mono">{person.phone ?? '—'}</span></span></span>
						</td>
						<td>
							<form class="role" method="post" action="?/role" use:enhance={submit}>
								<input type="hidden" name="id" value={person.id} />
								<select name="role" aria-label="Role for {person.name}" value={person.role} onchange={(e) => (picked[person.id] = e.currentTarget.value)}>
									{#each ROLES as [value, label] (value)}<option {value}>{label}</option>{/each}
								</select>
								{#if !js.on || (picked[person.id] && picked[person.id] !== person.role)}
									<button class="btn sm" type="submit" disabled={busy}>Save</button>
								{/if}
							</form>
						</td>
						<td><span class="pill {person.mfa_enabled ? 'ok' : 'warn'}">{person.mfa_enabled ? 'On' : 'Not yet'}</span></td>
						<td class="nowrap">{date(person.created_at)}</td>
						<td class="act">
							<form method="post" action="?/active" use:enhance={submit}>
								<input type="hidden" name="id" value={person.id} />
								<input type="hidden" name="active" value={String(!person.is_active)} />
								<button class="btn sm {person.is_active ? 'danger-line' : 'secondary'}" type="submit" disabled={busy}>{person.is_active ? 'Turn off' : 'Turn on'}</button>
							</form>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>

	<aside>
		<form class="box stack" method="post" action="?/add" use:enhance={submit}>
			<h2 class="bx">Add someone</h2>
			<div><label for="name">Full name</label><input id="name" name="name" required minlength="3" value={form?.name ?? ''} /></div>
			<div><label for="phone">Phone</label><input id="phone" name="phone" inputmode="tel" required placeholder="024 412 3456" value={form?.phone ?? ''} /></div>
			<div>
				<label for="role">Role</label>
				<select id="role" name="role" value={form?.role ?? 'field_verifier'}>
					{#each ROLES as [value, label] (value)}<option {value}>{label}</option>{/each}
				</select>
			</div>
			<button class="btn md block" type="submit" disabled={busy}>Add and send sign-in SMS</button>
		</form>
	</aside>
</div>

<style>
	.wide-t {
		min-width: 620px;
	}
	.who {
		display: flex;
		gap: 10px;
		align-items: center;
	}
	.sm-av {
		width: 32px;
		height: 32px;
		font-size: 12.5px;
	}
	.role {
		display: flex;
		gap: 6px;
		align-items: center;
	}
	.role select {
		height: 36px;
		font-size: 14px;
		min-width: 140px;
	}
	.off td {
		opacity: 0.6;
	}
	.nowrap {
		white-space: nowrap;
	}
	.act {
		text-align: right;
	}
	.bx {
		margin: 0;
		font-size: 20px;
	}
</style>
