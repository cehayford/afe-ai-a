<script lang="ts">
	// Footer from the Landing Page canvas: night background, mark + "afe", three link columns.
	import Logo from '$lib/components/ui/Logo.svelte';

	let { wide = false }: { wide?: boolean } = $props();
</script>

<footer class="site-foot">
	<div class="in" class:wide>
		<div class="top">
			<div class="brand">
				<Logo mark={32} text={24} theme="dark" />
				<p>Verified rentals in Accra.</p>
			</div>
			<div class="cols">
				<div><span>Renters</span><a href="/homes">Find a home</a><a href="/check">Scam check</a><a href="/" data-section="how">How it works</a><a href="/rent-index">Accra rent index</a></div>
				<div><span>Landlords</span><a href="/signup?role=landlord">List your home</a><a href="/" data-section="landlords">Verification</a></div>
				<div><span>Afe</span><a href="/check" data-section="report">Report a scam</a><a href="/privacy">Privacy</a><a href="/terms">Terms</a></div>
			</div>
		</div>
		<div class="base">© {new Date().getFullYear()} Afe · Accra, Ghana</div>
	</div>
</footer>

<style>
	.site-foot {
		margin-top: auto;
		background: var(--night);
		color: var(--night-ink);
	}
	.in {
		max-width: 1180px;
		margin: 0 auto;
		padding: 48px 24px 32px;
		display: flex;
		flex-direction: column;
		gap: 32px;
	}
	.in.wide {
		max-width: 1240px;
		padding-inline: 20px;
	}
	.top {
		display: flex;
		justify-content: space-between;
		gap: 32px;
		flex-wrap: wrap;
	}
	.brand {
		display: flex;
		flex-direction: column;
		gap: 12px;
		max-width: 320px;
	}
	.brand p {
		margin: 0;
		font-size: 14px;
		color: var(--night-muted);
	}
	.cols {
		display: flex;
		gap: 48px;
		flex-wrap: wrap;
	}
	.cols div {
		display: flex;
		flex-direction: column;
		gap: 8px;
		font-size: 14px;
	}
	.cols span {
		font-family: var(--font-mono);
		font-size: 11px;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--night-muted);
	}
	.cols a {
		color: var(--night-ink);
	}
	.cols a:hover {
		color: var(--night-link);
	}
	.base {
		border-top: 1px solid var(--night-line);
		padding-top: 20px;
		font-size: 13px;
		color: var(--night-muted);
	}
</style>
