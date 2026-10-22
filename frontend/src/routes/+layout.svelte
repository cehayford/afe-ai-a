<script lang="ts">
	import '@fontsource-variable/bricolage-grotesque/opsz.css';
	import '@fontsource/ibm-plex-sans/400.css';
	import '@fontsource/ibm-plex-sans/500.css';
	import '@fontsource/ibm-plex-sans/600.css';
	import '@fontsource/ibm-plex-mono/400.css';
	import '@fontsource/ibm-plex-mono/500.css';
	import '../app.css';
	import { page } from '$app/state';
	import { afterNavigate, onNavigate, replaceState } from '$app/navigation';
	import SiteHeader from '$lib/components/shell/SiteHeader.svelte';
	import SiteFooter from '$lib/components/shell/SiteFooter.svelte';
	import AreaHeader from '$lib/components/shell/AreaHeader.svelte';
	import { announcer } from '$lib/announce.svelte';
	import { followSectionLink, showSection } from '$lib/sections';

	let { data, children } = $props();

	const me = $derived(data.me);
	const role = $derived(me?.user.role);
	const path = $derived(page.url.pathname);
	// Each working area has its own frame, as in the design: the sign-in pages are a full-screen
	// split, the field app is a phone-width column, landlords and reviewers get their own headers.
	const area = $derived(
		path.startsWith('/signin') || path.startsWith('/signup')
			? 'auth'
			: path.startsWith('/field')
				? 'field'
				: ['/landlord', '/rentals', '/account', '/tenancies'].some((p) => path.startsWith(p)) && (role === 'landlord' || role === 'agent')
					? 'landlord'
					: path.startsWith('/review')
						? 'review'
						: 'public'
	);
	const fullBleed = $derived(page.route.id === '/');
	const initials = $derived(
		(me?.user.name ?? '')
			.split(/\s+/)
			.filter(Boolean)
			.slice(0, 2)
			.map((w) => w[0]?.toUpperCase())
			.join('')
	);
	const on = (href: string, exact = false) => (exact ? path === href : path === href || path.startsWith(href + '/'));
	const landlordLinks = $derived([
		{ href: '/landlord/verify', label: 'Verification', on: on('/landlord/verify') },
		{ href: '/landlord', label: 'Dashboard', on: path.startsWith('/landlord') && !on('/landlord/verify') }
	]);
	const reviewLinks = $derived([
		{ href: '/review', label: 'Queue', on: path === '/review' || on('/review/homes') || on('/review/people') },
		{ href: '/review/money', label: 'Money', on: on('/review/money') },
		{ href: '/review/reports', label: 'Reports', on: on('/review/reports') },
		{ href: '/review/appeals', label: 'Appeals', on: on('/review/appeals') },
		{ href: '/review/detection', label: 'Models', on: on('/review/detection') || on('/review/label-checks') || on('/review/insights') },
		{ href: '/review/rules', label: 'Rules', on: on('/review/rules') },
		{ href: '/review/verifiers', label: 'Verifiers', on: on('/review/verifiers') || on('/review/visit-plan') || on('/review/workload') },
		...(role === 'admin'
			? [
					{ href: '/review/staff', label: 'Staff', on: on('/review/staff') },
					{ href: '/review/areas', label: 'Areas', on: on('/review/areas') }
				]
			: [])
	]);

	// An old link with "#how" still lands on its section; then the "#how" is dropped from the address ($lib/sections).
	// Run after the router has finished: replaceState can't run while the first page is still being set up.
	function dropHash() {
		const { pathname, search, hash } = location;
		if (hash && showSection(decodeURIComponent(hash.slice(1)))) replaceState(pathname + search, page.state);
	}
	afterNavigate(({ to }) => {
		if (to?.url.hash) setTimeout(dropHash);
	});

	// Searching from the landing page: the search form carries over to the results (View Transitions
	// API). Only this navigation: page changes elsewhere stay instant, because people make them often.
	onNavigate((navigation) => {
		if (navigation.from?.route.id !== '/' || navigation.to?.route.id !== '/homes') return;
		if (!document.startViewTransition || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
		return new Promise((resolve) => {
			document.startViewTransition(async () => {
				resolve();
				await navigation.complete;
			});
		});
	});
</script>

{#snippet privacy()}
	{#if me && !me.user.privacy_current}
		<form class="notice row spread" method="post" action="/account?/privacy">
			<span>Please read Afe's <a href="/privacy">privacy notice</a> and <a href="/terms">terms</a>. They explain how we use your data.</span>
			<button class="btn small" type="submit">I accept</button>
		</form>
	{/if}
{/snippet}

<!-- A "#how" typed on the page that's already open isn't a navigation: hashchange catches it. -->
<svelte:window onclickcapture={followSectionLink} onhashchange={() => setTimeout(dropHash)} />

<!-- "#main" is for browsers without JavaScript; with it, the skip link moves focus without changing the address. -->
<a class="skip" href="#main" data-section="main">Skip to content</a>

{#if area === 'auth' || area === 'field'}
	{@render children()}
{:else}
	<div class="app">
		{#if area === 'landlord'}
			<AreaHeader tone="brand" tag="Landlords" links={landlordLinks} {initials} />
		{:else if area === 'review'}
			<AreaHeader tone="night" tag="Review desk" links={reviewLinks} wide who={me ? `Signed in as ${me.user.name} · ${me.user.role_label.toLowerCase()}` : ''} />
		{:else}
			<SiteHeader {me} wide={!fullBleed} />
		{/if}

		{#if fullBleed}
			<main id="main" tabindex="-1" class="bleed">
				{#if me && !me.user.privacy_current}<div class="wrap" style="padding-top: 16px">{@render privacy()}</div>{/if}
				{@render children()}
			</main>
		{:else}
			<main id="main" tabindex="-1" class="wrap" class:area-wide={area === 'landlord'} class:desk={area === 'review'} class:flush={page.route.id === '/review'}>
				{@render privacy()}
				{@render children()}
			</main>
		{/if}

		{#if area === 'public'}<SiteFooter wide={!fullBleed} />{/if}
	</div>
{/if}

<!-- Messages that appear after an action are read from here ($lib/announce.svelte.ts). -->
<div class="sr announcer" role="status" aria-live="polite" aria-atomic="true">{announcer.text}</div>

<style>
	/* Pinned to the top: left where it falls, after the page, it would add a pixel of scrolling to every page. */
	.announcer {
		top: 0;
		left: 0;
	}
	.app {
		min-height: 100vh;
		display: flex;
		flex-direction: column;
	}
	main {
		flex: 1;
		width: 100%;
	}
	main.bleed {
		padding: 0;
	}
	main.wrap {
		max-width: 1240px;
		padding: 20px 20px 88px;
	}
	main.area-wide {
		padding-top: 24px;
	}
	main.desk {
		max-width: 1440px;
		padding-inline: 24px;
		padding-top: 24px;
	}
	main.desk.flush {
		max-width: none;
		padding: 0;
	}
</style>
