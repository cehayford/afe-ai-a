<script lang="ts">
	// Landlord dashboard frame from the Landlord canvas: side tabs beside the content (they wrap into
	// a row on phones). "Get verified" is a page of its own, as in the design.
	import { page } from '$app/state';

	let { children } = $props();
	const path = $derived(page.url.pathname);
	const tabs = $derived([
		['/landlord', 'Overview', path === '/landlord' || path.startsWith('/landlord/homes')],
		['/landlord/listings', 'Listings', path.startsWith('/landlord/listings')],
		['/landlord/enquiries', 'Enquiries', path.startsWith('/landlord/enquiries') || path.startsWith('/landlord/offer')],
		['/landlord/payouts', 'Payouts', path.startsWith('/landlord/payouts')],
		['/landlord/rentals', 'Tenants', path.startsWith('/landlord/rentals')]
	] as [string, string, boolean][]);
</script>

{#if path.startsWith('/landlord/verify')}
	{@render children()}
{:else}
	<div class="ll-dash">
		<nav class="side" aria-label="Dashboard">
			{#each tabs as [href, label, on]}<a {href} aria-current={on ? 'page' : undefined}>{label}</a>{/each}
		</nav>
		<div class="ll-main">{@render children()}</div>
	</div>
{/if}

<style>
	.ll-dash {
		display: flex;
		flex-wrap: wrap;
		gap: 24px;
		align-items: flex-start;
	}
	.side {
		flex: 1 1 200px;
		display: flex;
		flex-wrap: wrap;
		gap: 4px;
		align-content: flex-start;
	}
	.side a {
		white-space: nowrap;
		flex: 1 1 160px;
		height: 44px;
		display: flex;
		align-items: center;
		padding: 0 14px;
		border-radius: 8px;
		color: var(--ink);
		font-size: 15px;
		font-weight: 600;
	}
	.side a:hover {
		background: var(--tint);
		color: var(--ink);
	}
	.side a[aria-current='page'] {
		background: var(--tint);
		color: var(--brand);
	}
	.ll-main {
		flex: 999 1 600px;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 20px;
	}
	.ll-main :global(> h1) {
		margin: 0;
		font-size: 30px;
	}
	@media (max-width: 640px) {
		.side {
			flex-wrap: nowrap;
			overflow-x: auto;
			flex-basis: 100%;
		}
		.side a {
			flex: 0 0 auto;
		}
	}
	@media (prefers-color-scheme: dark) {
		.side a[aria-current='page'] {
			color: var(--accent);
		}
	}
</style>
