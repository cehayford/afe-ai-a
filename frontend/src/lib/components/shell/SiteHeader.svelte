<script lang="ts">
	// Public header (Landing Page, Renter and UI Components canvases): sticky, frosted paper,
	// mark + "afe", pill-hover nav, Sign in + List your home. Under 880px the nav folds into the
	// menu from the "Mobile · menu open" frame.
	import { page } from '$app/state';
	import { afterNavigate } from '$app/navigation';
	import type { Me } from '$lib/api/types';
	import Logo from '$lib/components/ui/Logo.svelte';

	// wide: app pages use the Renter canvas's 1240px frame; the landing page keeps 1180px.
	let { me, wide = false }: { me: Me | null; wide?: boolean } = $props();
	let open = $state(false);
	afterNavigate(() => (open = false));

	const role = $derived(me?.user.role);
	const path = $derived(page.url.pathname);
	const links = $derived.by(() => {
		// [href, label, current page, section of the page to scroll to ($lib/sections)]
		const out: [string, string, boolean, string?][] = [
			['/homes', 'Find a home', path.startsWith('/homes') || path.startsWith('/areas')],
			['/check', 'Scam check', path.startsWith('/check')]
		];
		if (role === 'landlord' || role === 'agent') out.push(['/landlord', 'My homes', path.startsWith('/landlord')]);
		else if (role === 'reviewer' || role === 'admin') out.push(['/review', 'Review desk', false]);
		else if (role === 'field_verifier') out.push(['/field', 'Visits', false]);
		if (me) out.push([role === 'renter' ? '/account/saved' : '/account', 'My Afe', path.startsWith('/account') || path.startsWith('/tenancies')]);
		else out.push(['/', 'How it works', false, 'how'], ['/', 'For landlords', false, 'landlords']);
		return out;
	});
	const initials = $derived(
		(me?.user.name ?? '')
			.split(/\s+/)
			.filter(Boolean)
			.slice(0, 2)
			.map((w) => w[0]?.toUpperCase())
			.join('') || 'A'
	);
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && (open = false)} />

<header class="site-head">
	<div class="bar" class:wide>
		<Logo mark={wide ? 30 : 32} text={wide ? 22 : 24} />
		<nav class="links" aria-label="Main">
			{#each links as [href, label, on, section]}<a {href} data-section={section} aria-current={on ? 'page' : undefined}>{label}</a>{/each}
		</nav>
		<div class="acts">
			{#if me}
				<a class="me" href="/account" aria-label="My Afe, {me.user.name}{me.unread_notifications ? `, ${me.unread_notifications} unread alerts` : ''}"
					>{initials}{#if me.unread_notifications}<span class="dot">{me.unread_notifications}</span>{/if}</a
				>
			{:else}
				<a class="signin" href="/signin">Sign in</a>
				<a class="list" href="/signup?role=landlord">List your home</a>
			{/if}
		</div>
		<button class="burger" type="button" aria-label={open ? 'Close menu' : 'Menu'} aria-expanded={open} aria-controls="site-menu" onclick={() => (open = !open)}>
			<span></span><span></span><span></span>
		</button>
	</div>
	<!-- Always in the page, hidden while closed, so the button's aria-controls points at something. -->
	<div class="menu" id="site-menu" hidden={!open}>
		{#each links as [href, label, on, section]}<a {href} data-section={section} aria-current={on ? 'page' : undefined} onclick={() => (open = false)}>{label}</a>{/each}
		{#if me}
			<a href="/account/notifications">Alerts{#if me.unread_notifications} ({me.unread_notifications}){/if}</a>
		{:else}
			<div class="pair"><a class="out" href="/signin">Sign in</a><a class="in" href="/signup?role=landlord">List home</a></div>
		{/if}
	</div>
</header>

<style>
	.site-head {
		position: sticky;
		top: 0;
		z-index: 1000;
		background: var(--head-bg);
		backdrop-filter: blur(8px);
		-webkit-backdrop-filter: blur(8px);
		border-bottom: 1px solid var(--line);
		color: var(--ink);
	}
	.bar {
		max-width: 1180px;
		margin: 0 auto;
		padding: 14px 24px;
		display: flex;
		align-items: center;
		gap: 32px;
	}
	.bar.wide {
		max-width: 1240px;
		padding: 12px 20px;
		gap: 24px;
	}
	.links {
		display: flex;
		gap: 4px;
		flex: 1;
		min-width: 0;
		flex-wrap: wrap;
		height: 40px;
		overflow: hidden;
	}
	.links a {
		white-space: nowrap;
		flex: 0 0 auto;
		padding: 8px 12px;
		border-radius: 6px;
		font-size: 15px;
		font-weight: 500;
		color: var(--ink);
	}
	.links a:hover {
		background: var(--tint);
	}
	.links a[aria-current='page'] {
		background: var(--tint);
		color: var(--brand);
		font-weight: 600;
	}
	.acts {
		display: flex;
		gap: 8px;
		align-items: center;
	}
	.signin,
	.list {
		white-space: nowrap;
		flex: 0 0 auto;
		height: 44px;
		display: flex;
		align-items: center;
		font-size: 15px;
		font-weight: 600;
		border-radius: 8px;
	}
	.signin {
		padding: 0 16px;
		color: var(--ink);
	}
	.signin:hover {
		background: var(--tint);
		color: var(--ink);
	}
	.list {
		padding: 0 18px;
		color: var(--on-primary);
		background: var(--primary);
	}
	.list:hover {
		background: var(--primary-hover);
		color: var(--on-primary);
	}
	.me {
		position: relative;
		flex: 0 0 auto;
		width: 40px;
		height: 40px;
		border-radius: 99px;
		background: var(--primary);
		color: var(--on-primary);
		display: flex;
		align-items: center;
		justify-content: center;
		font: 700 15px var(--font-display);
	}
	.me:hover {
		color: var(--on-primary);
		background: var(--primary-hover);
	}
	.dot {
		position: absolute;
		top: -4px;
		right: -6px;
		min-width: 18px;
		height: 18px;
		padding: 0 5px;
		border-radius: 99px;
		background: var(--amber);
		color: var(--on-amber);
		font: 700 11px/18px var(--font-sans);
		text-align: center;
	}
	.burger {
		display: none;
		width: 44px;
		height: 44px;
		margin-left: auto;
		border: 0;
		border-radius: 8px;
		background: transparent;
		flex-direction: column;
		gap: 5px;
		align-items: center;
		justify-content: center;
		cursor: pointer;
	}
	.burger:hover {
		background: var(--tint);
	}
	.burger span {
		width: 20px;
		height: 2px;
		background: var(--ink);
		border-radius: 2px;
		transition: transform 180ms var(--ease-out-fluid), opacity 120ms;
	}
	.burger[aria-expanded='true'] span:nth-child(1) {
		transform: translateY(7px) rotate(45deg);
	}
	.burger[aria-expanded='true'] span:nth-child(2) {
		opacity: 0;
	}
	.burger[aria-expanded='true'] span:nth-child(3) {
		transform: translateY(-7px) rotate(-45deg);
	}
	.menu {
		display: none;
		padding: 8px;
		flex-direction: column;
		border-top: 1px solid var(--line);
		animation: menu-in 180ms var(--ease-out-fluid);
	}
	.menu a {
		height: 48px;
		padding: 0 12px;
		display: flex;
		align-items: center;
		border-radius: 8px;
		font-size: 16px;
		color: var(--ink);
	}
	.menu a[aria-current='page'] {
		font-weight: 600;
		color: var(--brand);
		background: var(--tint);
	}
	.pair {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 8px;
		padding: 8px 4px 4px;
	}
	.pair a {
		justify-content: center;
		font-weight: 600;
		padding: 0;
	}
	.pair .out {
		border: 1px solid var(--brand);
		color: var(--brand);
	}
	.pair .in {
		background: var(--primary);
		color: var(--on-primary);
	}
	@keyframes menu-in {
		from {
			opacity: 0;
			transform: translateY(-6px);
		}
	}
	@media (max-width: 880px) {
		.bar {
			padding: 10px 16px;
			gap: 12px;
		}
		.links,
		.signin,
		.list {
			display: none;
		}
		.acts {
			margin-left: auto;
		}
		.burger {
			display: flex;
			margin-left: 0;
		}
		.menu {
			display: flex;
		}
		.menu[hidden] {
			display: none;
		}
	}
	@media (prefers-color-scheme: dark) {
		.links a[aria-current='page'],
		.menu a[aria-current='page'] {
			color: var(--accent);
		}
		.pair .out {
			border-color: var(--accent);
			color: var(--accent);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.menu {
			animation: none;
		}
		.burger span {
			transition: none;
		}
	}
</style>
