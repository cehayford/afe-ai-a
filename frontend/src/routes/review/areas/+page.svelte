<script lang="ts">
	// Areas as review cases: open or closed, a readiness checklist (the canvas's check rows), the price
	// survey behind a disclosure, and the open/close action. New areas are created beside the list.
	import { enhance } from '$app/forms';
	import FormError from '$lib/components/FormError.svelte';
	import { bedrooms } from '$lib/format';
	import Done from '$lib/components/Done.svelte';

	let { data, form } = $props();
	const checks = (missing: string[]) => [
		['Boundary drawn', !missing.some((m) => m.includes('boundary'))],
		['Price survey for 2+ home sizes', !missing.some((m) => m.includes('survey'))],
		['An active field verifier', !missing.some((m) => m.includes('verifier'))]
	] as [string, boolean][];
	let busy = $state(false);
	const submit = () => {
		busy = true;
		return async ({ update }: { update: () => Promise<void> }) => {
			await update();
			busy = false;
		};
	};
</script>

<svelte:head><title>Areas · Afe review</title></svelte:head>

<div class="page-head">
	<h1>Areas</h1>
	<p>An area opens to listings only when it has a boundary, a price survey for at least 2 home sizes, and an active field verifier (build plan §17).</p>
</div>
<FormError message={form?.error} />
<Done message={form?.done} key={form} />

<div class="detail">
	<div class="case-list">
		{#each data.areas as a (a.id)}
			<div class="case">
				<div class="case-head">
					<span class="t-head"><b class="a-name">{a.name}</b><span class="mono">{a.slug} · {a.city}</span></span>
					<span class="pill {a.is_active ? 'ok' : 'quiet'}">{a.is_active ? 'Open' : 'Closed'}</span>
				</div>
				{#each checks(a.missing) as [label, ok] (label)}
					<div class="c-row"><span class="tick {ok ? '' : 'no'}">{ok ? '✓' : '✕'}</span><span>{label}</span></div>
				{/each}
				<div class="c-row muted small">Surveyed: {a.surveyed_sizes.length ? a.surveyed_sizes.map((b) => bedrooms(b)).join(', ') : 'none yet'}</div>
				<div class="case-foot">
					<details>
						<summary class="btn quiet sm">Load the price survey</summary>
						<form class="survey" method="post" action="?/survey" use:enhance={submit}>
							<input type="hidden" name="id" value={a.id} />
							<div class="s-grid">
								<span></span><span class="label-mono">Low</span><span class="label-mono">Middle</span><span class="label-mono">High</span>
								{#each [0, 1, 2, 3] as b (b)}
									<span class="s-size">{bedrooms(b)}{b === 3 ? '+' : ''}</span>
									<input name="low{b}" type="number" min="1" placeholder="GH₵" aria-label="{bedrooms(b)} low, GH₵ a month" />
									<input name="mid{b}" type="number" min="1" placeholder="GH₵" aria-label="{bedrooms(b)} middle, GH₵ a month" />
									<input name="high{b}" type="number" min="1" placeholder="GH₵" aria-label="{bedrooms(b)} high, GH₵ a month" />
								{/each}
							</div>
							<span class="fine">GH₵ a month. Leave a size blank if it wasn't surveyed.</span>
							<div><button class="btn md" type="submit" disabled={busy}>Save survey</button></div>
						</form>
					</details>
					<form method="post" action="?/open" use:enhance={submit}>
						<input type="hidden" name="id" value={a.id} />
						<input type="hidden" name="open" value={String(!a.is_active)} />
						<button class="btn md {a.is_active ? 'danger-line' : 'go'}" type="submit" disabled={busy || (!a.is_active && a.missing.length > 0)}>
							{a.is_active ? 'Close area' : 'Open area'}
						</button>
					</form>
				</div>
			</div>
		{:else}
			<div class="empty">No areas yet.</div>
		{/each}
	</div>
	<aside>
		<form class="box stack" method="post" action="?/create" use:enhance={submit}>
			<h2 class="bx">New area</h2>
			<div><label for="name">Name</label><input id="name" name="name" required minlength="3" placeholder="Madina" /></div>
			<div><label for="slug">Web name</label><input id="slug" name="slug" required pattern="[a-z0-9-]{'{'}3,60{'}'}" placeholder="madina" /></div>
			<div><label for="city">City</label><input id="city" name="city" value="Accra" /></div>
			<div>
				<label for="boundary">Boundary</label>
				<textarea id="boundary" name="boundary" required placeholder="5.66, -0.18&#10;5.66, -0.15&#10;5.69, -0.15"></textarea>
				<p class="note" style="margin: 6px 0 0">One "latitude, longitude" per line, at least 3.</p>
			</div>
			<button class="btn md block" type="submit" disabled={busy}>Create (closed)</button>
		</form>
	</aside>
</div>

<style>
	.t-head {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.a-name {
		font: 700 18px var(--font-display);
	}
	.c-row {
		display: flex;
		gap: 10px;
		align-items: center;
		padding: 10px 16px;
		border-bottom: 1px solid var(--hair);
		font-size: 14.5px;
	}
	.survey {
		display: flex;
		flex-direction: column;
		gap: 10px;
		margin-top: 12px;
	}
	.s-grid {
		display: grid;
		grid-template-columns: 110px repeat(3, minmax(0, 1fr));
		gap: 6px 8px;
		align-items: center;
	}
	.s-grid input {
		height: 40px;
		min-width: 0;
	}
	.s-size {
		font-size: 14px;
	}
	.fine {
		font-size: 13px;
		color: var(--muted);
	}
	details > summary {
		list-style: none;
		width: fit-content;
	}
	details > summary::-webkit-details-marker {
		display: none;
	}
	details[open] > summary {
		background: var(--tint);
	}
	.bx {
		margin: 0;
		font-size: 20px;
	}
	@media (max-width: 480px) {
		.s-grid {
			grid-template-columns: 76px repeat(3, minmax(0, 1fr));
		}
	}
</style>
