<script lang="ts">
	// Headers for the working areas. "brand" is the Landlord canvas (Afe green, amber rule,
	// "Landlords" tag, nav on the right, amber avatar). "night" is the Admin Review canvas
	// ("Review desk" tag and who is signed in).
	import Logo from '$lib/components/ui/Logo.svelte';

	let {
		tone,
		tag,
		links,
		who = '',
		initials = '',
		wide = false
	}: {
		tone: 'brand' | 'night';
		tag: string;
		links: { href: string; label: string; on: boolean }[];
		who?: string;
		initials?: string;
		wide?: boolean;
	} = $props();
</script>

<header class="area-head {tone}">
	<div class="bar" class:wide>
		<Logo mark={tone === 'brand' ? 30 : 28} text={tone === 'brand' ? 22 : 20} theme="dark" {tag} href={tone === 'brand' ? '/landlord' : '/review'} />
		<nav aria-label={tag}>
			{#each links as l}<a href={l.href} aria-current={l.on ? 'page' : undefined}>{l.label}</a>{/each}
		</nav>
		{#if who}<span class="who">{who}</span>{/if}
		{#if initials}<a class="avatar-a" href="/account" aria-label="My account">{initials}</a>{/if}
	</div>
</header>

<style>
	.area-head {
		border-bottom: 4px solid var(--amber);
		color: #fff;
	}
	.area-head.brand {
		position: sticky;
		top: 0;
		z-index: 1000;
		background: var(--brand);
	}
	.area-head.night {
		background: var(--night);
		color: var(--night-ink);
	}
	.bar {
		max-width: 1240px;
		margin: 0 auto;
		padding: 12px 20px;
		display: flex;
		align-items: center;
		gap: 20px;
	}
	.bar.wide {
		max-width: none;
	}
	.night .bar {
		gap: 14px;
	}
	nav {
		display: flex;
		gap: 4px;
		flex: 1;
		min-width: 0;
		justify-content: flex-end;
		flex-wrap: wrap;
	}
	.night nav {
		justify-content: flex-start;
		margin-left: 12px;
	}
	nav a {
		white-space: nowrap;
		display: flex;
		align-items: center;
		height: 40px;
		padding: 0 14px;
		border-radius: 6px;
		color: #fff;
		font-size: 15px;
		font-weight: 600;
	}
	.night nav a {
		height: 34px;
		padding: 0 10px;
		font-size: 14px;
		font-weight: 500;
		color: var(--night-ink);
	}
	nav a:hover {
		background: rgba(255, 255, 255, 0.08);
		color: #fff;
	}
	nav a[aria-current='page'] {
		background: rgba(255, 255, 255, 0.14);
		color: #fff;
	}
	.night nav a[aria-current='page'] {
		font-weight: 600;
	}
	.who {
		margin-left: auto;
		font-size: 13.5px;
		color: var(--night-muted);
		white-space: nowrap;
	}
	.avatar-a {
		flex: 0 0 auto;
		width: 40px;
		height: 40px;
		border-radius: 99px;
		background: var(--amber);
		color: var(--on-amber);
		display: flex;
		align-items: center;
		justify-content: center;
		font: 700 15px var(--font-display);
	}
	.avatar-a:hover {
		background: var(--amber-hover);
		color: var(--on-amber);
	}
	@media (max-width: 720px) {
		.bar {
			flex-wrap: wrap;
			gap: 10px 14px;
		}
		nav {
			order: 3;
			flex-basis: 100%;
			justify-content: flex-start;
			margin-left: 0 !important;
			overflow-x: auto;
			flex-wrap: nowrap;
		}
		.who {
			display: none;
		}
		.avatar-a {
			margin-left: auto;
		}
	}
</style>
