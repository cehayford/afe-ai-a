<script lang="ts">
	// Sign in and sign up, from the "Afe Auth" canvas: a green brand panel beside the form. One screen
	// for both: the tabs switch in place (the address follows), the phone number and name carry over.
	// Steps: entry (phone, how to send the code) -> code (six boxes, resend timer) -> done.
	// Landlords and staff also pass an authenticator step, which the backend requires.
	import { onDestroy } from 'svelte';
	import { applyAction, enhance } from '$app/forms';
	import { replaceState } from '$app/navigation';
	import type { SubmitFunction } from '@sveltejs/kit';
	import AfeMark from '$lib/components/ui/AfeMark.svelte';
	import CheckIcon from '$lib/components/ui/CheckIcon.svelte';

	type Result = {
		step?: 'code' | 'mfa' | 'mfa_setup' | 'done';
		error?: string;
		phone?: string;
		channel?: string;
		qr?: string;
		secret?: string;
		role?: string;
		login?: string;
		mode?: string;
	} | null;

	let {
		start,
		next = '',
		initialRole = 'renter',
		password = false,
		freeVerification = false,
		form
	}: {
		start: 'in' | 'up';
		next?: string;
		initialRole?: string;
		password?: boolean;
		freeVerification?: boolean;
		form: Result;
	} = $props();

	// svelte-ignore state_referenced_locally
	let mode = $state<'in' | 'up'>(start);
	// svelte-ignore state_referenced_locally
	let res = $state<Result>(form);
	// svelte-ignore state_referenced_locally
	let role = $state(initialRole === 'agent' ? 'agent' : initialRole === 'landlord' ? 'landlord' : 'renter');
	let name = $state('');
	// svelte-ignore state_referenced_locally
	let phone = $state(localPhone(form?.phone ?? ''));
	// svelte-ignore state_referenced_locally
	let channel = $state<'whatsapp' | 'sms'>(form?.channel === 'sms' ? 'sms' : 'whatsapp');
	let phoneErr = $state(false);
	let code = $state('');
	let busy = $state(false);
	let wait = $state(0);
	let timer: ReturnType<typeof setInterval> | undefined;

	const up = $derived(mode === 'up');
	const step = $derived(res?.step === 'code' || res?.step === 'mfa' || res?.step === 'mfa_setup' || res?.step === 'done' ? res.step : 'entry');
	const digits = $derived(phone.replace(/\D/g, ''));
	const e164 = $derived(`+233${digits.length === 10 && digits.startsWith('0') ? digits.slice(1) : digits}`);
	const pretty = $derived((res?.phone ?? e164).replace(/^\+233/, '').replace(/^(\d{2})(\d{3})(\d{0,4}).*$/, '$1 $2 $3'));
	const landlord = $derived(role === 'landlord' || role === 'agent');
	const action = (name: string) => `${up ? '/signup' : '/signin'}?/${name}`;

	/** "024 412 3456", "+233 24 412 3456" and "24 412 3456" all become "24 412 3456". */
	function localPhone(value: string): string {
		let d = value.replace(/\D/g, '');
		if (d.startsWith('233') && d.length === 12) d = d.slice(3);
		if (d.startsWith('0') && d.length === 10) d = d.slice(1);
		return d.slice(0, 9).replace(/^(\d{2})(\d{3})(\d{0,4}).*$/, '$1 $2 $3').trim();
	}

	function startTimer() {
		clearInterval(timer);
		wait = 30;
		timer = setInterval(() => {
			wait -= 1;
			if (wait <= 0) clearInterval(timer);
		}, 1000);
	}
	onDestroy(() => clearInterval(timer));

	function switchTo(m: 'in' | 'up') {
		if (m === mode) return;
		mode = m;
		phoneErr = false;
		res = null;
		replaceState(m === 'up' ? '/signup' : '/signin', {});
	}

	// Every form answers in place: the step comes from the action's result.
	const submit =
		(opts: { check?: 'phone' | 'code'; onCode?: boolean } = {}): SubmitFunction =>
		({ cancel }) => {
			if (opts.check === 'phone' && !(digits.length === 9 || (digits.length === 10 && digits.startsWith('0')))) {
				phoneErr = true;
				cancel();
				return;
			}
			if (opts.check === 'code' && code.length !== 6) {
				res = { ...res, error: 'Enter all 6 digits of the code.' };
				cancel();
				return;
			}
			busy = true;
			return async ({ result }) => {
				busy = false;
				if (result.type === 'success') {
					res = (result.data ?? null) as Result;
					if (res?.step === 'code' && opts.onCode) {
						code = '';
						startTimer();
					}
				} else if (result.type === 'failure') {
					// A failure only adds its message: the step (and any authenticator QR code) stays.
					res = { ...res, error: (result.data as Result)?.error ?? 'Something went wrong. Try again.' };
				} else {
					await applyAction(result);
				}
			};
		};

	const kyc = [
		['1', 'Ghana Card and live selfie', '3 min'],
		['2', 'Ownership papers or letter of authority', '5 min'],
		['3', 'Book a visit from an Afe verifier', '1 min']
	];
	const home = $derived(
		res?.role === 'landlord' || res?.role === 'agent'
			? ['/landlord', 'Go to your dashboard']
			: res?.role === 'reviewer' || res?.role === 'admin'
				? ['/review', 'Open the review desk']
				: res?.role === 'field_verifier'
					? ['/field', "Today's visits"]
					: ['/homes', 'Find a home']
	);
</script>

<div class="auth">
	<aside class="brand-panel" data-screen-label="Auth brand panel">
		<a class="brand-logo" href="/" aria-label="Afe home"><AfeMark size={36} theme="dark" /><span>afe</span></a>
		<div class="brand-copy">
			<h1>Every landlord checked. Every home visited.</h1>
			<p>Sign in with your phone number. We never ask for a password, and we'll never ask you to send money outside Afe.</p>
		</div>
		<div class="brand-foot">Verified rentals in Accra</div>
	</aside>

	<main id="main" tabindex="-1" class="form-side">
		<div class="col">
			{#if step === 'entry' && password}
				<div class="head">
					<h2>Staff sign-in</h2>
					<p>For Afe staff with a username and password.</p>
				</div>
				<form class="fields" method="post" action="/signin?/password" use:enhance={submit()}>
					{#if res?.error}<div class="err" role="alert">{res.error}</div>{/if}
					<input type="hidden" name="next" value={next} />
					<label class="fld"><span>Username or phone number</span><input type="text" name="login" autocomplete="username" value={res?.login ?? ''} required /></label>
					<label class="fld"><span>Password</span><input type="password" name="password" autocomplete="current-password" required /></label>
					<button class="btn big" type="submit" disabled={busy}>Sign in</button>
					<a class="quiet-link" href="/signin">Sign in with a phone code instead</a>
				</form>
			{:else if step === 'entry'}
				<div class="seg" role="group" aria-label="Sign in or create an account">
					<button type="button" aria-pressed={!up} onclick={() => switchTo('in')}>Sign in</button>
					<button type="button" aria-pressed={up} onclick={() => switchTo('up')}>Create account</button>
				</div>
				<div class="head">
					<h2>{up ? 'Create your account' : 'Welcome back'}</h2>
					<p>{up ? 'It takes a minute. No password needed.' : "We'll send a one-time code to your phone."}</p>
				</div>
				<form class="fields" method="post" action={action('sendCode')} use:enhance={submit({ check: 'phone', onCode: true })} novalidate>
					<input type="hidden" name="next" value={next} />
					<input type="hidden" name="channel" value={channel} />
					{#if up}
						<input type="hidden" name="role" value={role} />
						<input type="hidden" name="accept" value="yes" />
						<div class="fld">
							<span id="iam">I am</span>
							<div class="roles" role="radiogroup" aria-labelledby="iam">
								<button type="button" role="radio" aria-checked={role === 'renter'} class="opt" class:on={role === 'renter'} onclick={() => (role = 'renter')}>
									<b>Looking for a home</b><small>Renter</small>
								</button>
								<button type="button" role="radio" aria-checked={landlord} class="opt" class:on={landlord} onclick={() => (role = role === 'agent' ? 'agent' : 'landlord')}>
									<b>Renting out a home</b><small>Landlord or agent</small>
								</button>
							</div>
							{#if landlord}
								<div class="chips fill owner" role="radiogroup" aria-label="Whose home is it?">
									<button type="button" role="radio" aria-checked={role === 'landlord'} class="chip" class:on={role === 'landlord'} onclick={() => (role = 'landlord')}>I own it</button>
									<button type="button" role="radio" aria-checked={role === 'agent'} class="chip" class:on={role === 'agent'} onclick={() => (role = 'agent')}>I'm the owner's agent</button>
								</div>
							{/if}
						</div>
						<label class="fld">
							<span>Full name</span><small>As it appears on your Ghana Card</small>
							<input type="text" name="display_name" bind:value={name} placeholder="Ama Mensah" autocomplete="name" required minlength="2" />
						</label>
					{/if}
					<label class="fld">
						<span>Phone number</span>
						<div class="phone" class:bad={phoneErr}>
							<span>+233</span>
							<input
								type="tel"
								name="phone"
								inputmode="tel"
								autocomplete="tel-national"
								placeholder="24 123 4567"
								value={phone}
								oninput={(e) => {
									phone = e.currentTarget.value.replace(/[^\d ]/g, '').slice(0, 13);
									phoneErr = false;
								}}
								aria-invalid={phoneErr}
								aria-describedby={phoneErr ? 'phone-err' : undefined}
							/>
						</div>
					</label>
					<div class="fld">
						<span id="via">Send my code by</span>
						<div class="chips fill" role="radiogroup" aria-labelledby="via">
							<button type="button" role="radio" aria-checked={channel === 'whatsapp'} class="chip" class:on={channel === 'whatsapp'} onclick={() => (channel = 'whatsapp')}>WhatsApp</button>
							<button type="button" role="radio" aria-checked={channel === 'sms'} class="chip" class:on={channel === 'sms'} onclick={() => (channel = 'sms')}>SMS</button>
						</div>
					</div>
					{#if phoneErr}<div class="err" id="phone-err" role="alert">Enter a 9-digit Ghana number, without the leading 0.</div>{/if}
					{#if res?.error}<div class="err" role="alert">{res.error}</div>{/if}
					<button class="btn big" type="submit" disabled={busy}>{busy ? 'Sending…' : 'Send code'}</button>
					{#if up}
						<p class="fine">By creating an account you agree to the <a href="/terms" target="_blank">Terms</a> and <a href="/privacy" target="_blank">Privacy notice</a>.</p>
					{:else}
						<p class="fine">Afe staff? <a href="/signin?mode=password">Sign in with a password</a></p>
					{/if}
				</form>
			{:else if step === 'code'}
				<button type="button" class="back" onclick={() => (res = null)}>← Change number</button>
				<div class="head">
					<h2>Enter your code</h2>
					<p>We sent a 6-digit code by {res?.channel === 'sms' ? 'SMS' : 'WhatsApp'} to +233 {pretty}.</p>
				</div>
				<form class="fields" method="post" action={action(up ? 'verify' : 'verifyCode')} use:enhance={submit({ check: 'code' })}>
					<input type="hidden" name="phone" value={res?.phone ?? e164} />
					<input type="hidden" name="next" value={next} />
					{#if up}
						<input type="hidden" name="display_name" value={name} />
						<input type="hidden" name="role" value={role} />
						<input type="hidden" name="accept" value="yes" />
					{/if}
					<label class="boxes-wrap">
						<span class="sr">6-digit code</span>
						<div class="boxes" aria-hidden="true">
							{#each Array(6) as _, i}
								<div class="box6" class:cur={i === code.length} class:bad={!!res?.error && i !== code.length}>{code[i] ?? ''}</div>
							{/each}
						</div>
						<!-- svelte-ignore a11y_autofocus -->
						<input
							class="code-in"
							name="code"
							value={code}
							oninput={(e) => {
								code = e.currentTarget.value.replace(/\D/g, '').slice(0, 6);
								e.currentTarget.value = code;
								if (res?.error) res = { ...res, error: undefined };
							}}
							inputmode="numeric"
							autocomplete="one-time-code"
							maxlength="6"
							autofocus
						/>
					</label>
					{#if res?.error}<div class="err" role="alert">{res.error}</div>{/if}
					<button class="btn big" type="submit" disabled={busy}>{busy ? 'Checking…' : 'Verify and continue'}</button>
				</form>
				<form class="resend" method="post" action={action('sendCode')} use:enhance={submit({ onCode: true })}>
					<input type="hidden" name="phone" value={res?.phone ?? e164} />
					<input type="hidden" name="channel" value={res?.channel ?? channel} />
					<input type="hidden" name="next" value={next} />
					{#if up}
						<input type="hidden" name="display_name" value={name} />
						<input type="hidden" name="role" value={role} />
						<input type="hidden" name="accept" value="yes" />
					{/if}
					<span>Didn't get it?</span>
					<button type="submit" class="linkbtn" disabled={wait > 0 || busy}>{wait > 0 ? `Resend in ${wait}s` : 'Resend code'}</button>
				</form>
				<div class="private"><b>Keep it private.</b><span>Afe staff will never ask you for this code.</span></div>
			{:else if step === 'mfa' || step === 'mfa_setup'}
				<div class="head">
					<h2>{step === 'mfa_setup' ? 'Protect your account' : 'Enter your authenticator code'}</h2>
					<p>
						{step === 'mfa_setup'
							? "Landlords, agents and Afe staff also use an authenticator app, so a stolen text message can't open the account. Install Google Authenticator or Microsoft Authenticator, then scan this code."
							: 'Open your authenticator app and type the 6-digit code for Afe.'}
					</p>
				</div>
				<form class="fields" method="post" action={action('mfa')} use:enhance={submit()}>
					{#if step === 'mfa_setup' && res?.qr}
						<img class="qr" src={res.qr} alt="QR code to add Afe to your authenticator app" width="200" height="200" />
						<p class="fine">Can't scan? Enter this key in the app: <code class="secret">{res.secret}</code></p>
					{/if}
					<input type="hidden" name="next" value={next} />
					<label class="fld"><span>6-digit code</span><input type="text" name="code" inputmode="numeric" autocomplete="one-time-code" maxlength="7" required /></label>
					{#if res?.error}<div class="err" role="alert">{res.error}</div>{/if}
					<button class="btn big" type="submit" disabled={busy}>{step === 'mfa_setup' ? 'Finish setup' : 'Sign in'}</button>
				</form>
			{:else}
				{@const isLandlord = res?.role === 'landlord' || res?.role === 'agent'}
				<div class="done-ring"><CheckIcon size={26} weight={1.8} /></div>
				<div class="head">
					<h2>{isLandlord && up ? 'Account created. Next, get verified.' : up ? "You're in." : 'Signed in'}</h2>
					<p>
						{#if isLandlord && up}
							Before your first listing goes live, we check who you are and that the home is yours.{freeVerification ? ' Verification is free during the launch offer.' : ''}
						{:else if res?.role === 'renter' || !res?.role}
							Browse verified homes and save the ones you want to view.
						{:else}
							You're signed in to Afe.
						{/if}
					</p>
				</div>
				{#if isLandlord && up}
					<ol class="kyc">
						{#each kyc as [n, t, time]}<li><span class="n">{n}</span><span class="t">{t}</span><span class="time">{time}</span></li>{/each}
					</ol>
					<a class="btn big" href="/landlord/verify">Start verification</a>
				{:else}
					<a class="btn big" href={home[0]}>{home[1]}</a>
				{/if}
			{/if}
		</div>
	</main>
</div>

<style>
	.auth {
		min-height: 100vh;
		display: grid;
		grid-template-columns: 1fr;
	}
	/* Side by side, the brand panel stays put while the form scrolls. Stacked on a phone, it scrolls away above
	   the form, so it never covers it. */
	@media (min-width: 860px) {
		.auth {
			grid-template-columns: 1fr 1fr;
		}
		.brand-panel {
			position: sticky;
			top: 0;
			align-self: start;
			height: 100vh;
			height: 100dvh;
			overflow-y: auto;
		}
	}
	.brand-panel {
		background: var(--brand);
		color: #fff;
		padding: 40px;
		display: flex;
		flex-direction: column;
		justify-content: space-between;
		gap: 40px;
		border-right: 5px solid var(--amber);
	}
	.brand-logo {
		display: flex;
		align-items: center;
		gap: 10px;
		color: #fff;
		width: fit-content;
	}
	.brand-logo:hover {
		color: #fff;
	}
	.brand-logo span {
		font: 700 26px var(--font-display);
		letter-spacing: -0.02em;
	}
	.brand-copy {
		display: flex;
		flex-direction: column;
		gap: 16px;
		max-width: 30em;
	}
	.brand-copy h1 {
		margin: 0;
		font-size: clamp(32px, 4vw, 44px);
		line-height: 1.08;
		letter-spacing: -0.02em;
	}
	.brand-copy p {
		margin: 0;
		font-size: 16.5px;
		line-height: 1.55;
		color: var(--brand-ink-soft);
	}
	.brand-foot {
		font: 12px var(--font-mono);
		color: var(--brand-ink-soft);
	}
	.form-side {
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 40px 24px;
	}
	.col {
		width: 100%;
		max-width: 420px;
		display: flex;
		flex-direction: column;
		gap: 28px;
	}
	.head {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	.head h2 {
		margin: 0;
		font-size: 30px;
		line-height: 1.15;
	}
	.head p {
		margin: 0;
		font-size: 15px;
		color: var(--muted);
		line-height: 1.55;
	}
	.fields {
		display: flex;
		flex-direction: column;
		gap: 18px;
	}
	.fld {
		display: flex;
		flex-direction: column;
		gap: 6px;
		margin: 0;
	}
	.fld > span,
	.fld > #iam,
	.fld > #via {
		font-size: 14px;
		font-weight: 600;
	}
	.fld > small {
		font-size: 13px;
		font-weight: 400;
		color: var(--muted);
		margin-top: -4px;
	}
	.roles {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 8px;
	}
	.opt {
		text-align: left;
		padding: 12px 14px;
		display: flex;
		flex-direction: column;
		gap: 2px;
		border-radius: 8px;
		border: 1px solid var(--line);
		background: var(--surface);
		color: var(--ink);
		font-family: var(--font-sans);
		cursor: pointer;
		margin: 1px;
	}
	.opt.on {
		border: 2px solid var(--brand);
		background: var(--tint);
		margin: 0;
	}
	.opt b {
		font-weight: 600;
		font-size: 15px;
	}
	.opt small {
		font-size: 13px;
		color: var(--muted);
	}
	.owner {
		margin-top: 2px;
	}
	.owner .chip {
		height: 40px;
		font-size: 14px;
	}
	.phone.bad {
		border: 2px solid var(--crit);
	}
	.chips.fill .chip {
		flex: 1;
	}
	.err {
		font-size: 14px;
		color: var(--crit);
		background: var(--crit-soft);
		border-radius: 8px;
		padding: 10px 12px;
	}
	.fine {
		margin: 0;
		font-size: 13px;
		line-height: 1.5;
		color: var(--muted);
	}
	.quiet-link {
		font-size: 14px;
		font-weight: 600;
	}
	.boxes-wrap {
		position: relative;
		display: block;
		cursor: text;
		margin: 0;
	}
	.boxes {
		display: grid;
		grid-template-columns: repeat(6, 1fr);
		gap: 8px;
	}
	.box6 {
		height: 56px;
		border-radius: 8px;
		border: 1px solid var(--line);
		background: var(--surface);
		display: flex;
		align-items: center;
		justify-content: center;
		font: 500 24px var(--font-mono);
	}
	.box6.cur {
		border: 2px solid var(--brand);
	}
	.box6.bad {
		border-color: var(--crit);
	}
	.boxes-wrap:has(.code-in:focus-visible) .box6.cur {
		outline: 2px solid var(--amber);
		outline-offset: 1px;
	}
	.code-in {
		position: absolute;
		inset: 0;
		opacity: 0;
		width: 100%;
		height: 100%;
		font-size: 16px;
		border: 0;
	}
	.resend {
		display: flex;
		justify-content: space-between;
		font-size: 14px;
		color: var(--muted);
	}
	.resend .linkbtn {
		font-size: 14px;
		font-family: var(--font-sans);
	}
	.resend .linkbtn:disabled {
		color: var(--muted);
		font-weight: 500;
	}
	.private {
		display: flex;
		gap: 10px;
		background: var(--warn-soft);
		border-radius: 8px;
		padding: 12px 14px;
		font-size: 13.5px;
		line-height: 1.5;
	}
	.private b {
		font-weight: 600;
		flex: 0 0 auto;
	}
	.done-ring {
		width: 56px;
		height: 56px;
		border-radius: 99px;
		background: var(--ok-soft);
		color: var(--ok);
		display: flex;
		align-items: center;
		justify-content: center;
	}
	.kyc {
		list-style: none;
		margin: 0;
		padding: 0;
		border: 1px solid var(--line);
		border-radius: 10px;
		background: var(--surface);
	}
	.kyc li {
		display: flex;
		gap: 12px;
		align-items: center;
		padding: 14px 16px;
		border-bottom: 1px solid var(--line);
	}
	.kyc li:last-child {
		border-bottom: 0;
	}
	.kyc .n {
		font: 12px var(--font-mono);
		color: var(--warn);
		width: 20px;
	}
	.kyc .t {
		flex: 1;
		font-size: 15px;
	}
	.kyc .time {
		font: 11px var(--font-mono);
		color: var(--muted);
	}
	@media (max-width: 860px) {
		.auth {
			grid-template-rows: auto 1fr;
		}
		.form-side {
			align-items: flex-start;
			padding-top: 32px;
		}
		.brand-panel {
			border-right: 0;
			border-bottom: 5px solid var(--amber);
			padding: 24px;
			gap: 24px;
		}
		.brand-copy p,
		.brand-foot {
			display: none;
		}
		.brand-copy h1 {
			font-size: 28px;
		}
	}
</style>
