<script lang="ts">
	import type { PersonGraph } from '$lib/api/types';

	let { graph }: { graph: PersonGraph } = $props();
	const SIZE = 320;
	const KIND: Record<string, string> = {
		ghana_card: 'Ghana Card',
		payout_account: 'payout account',
		photo: 'photo',
		phone_in_message: 'phone in a message',
		device: 'device'
	};
	// The person in the middle, everyone linked to them on a circle around.
	const pos = $derived.by(() => {
		const others = graph.nodes.filter((n) => !n.focus);
		const map = new Map<number, [number, number]>();
		const focus = graph.nodes.find((n) => n.focus);
		if (focus) map.set(focus.id, [SIZE / 2, SIZE / 2]);
		others.forEach((n, i) => {
			const a = (2 * Math.PI * i) / Math.max(others.length, 1) - Math.PI / 2;
			map.set(n.id, [SIZE / 2 + 120 * Math.cos(a), SIZE / 2 + 120 * Math.sin(a)]);
		});
		return map;
	});
	const tone = (n: PersonGraph['nodes'][number]) => (n.fraud ? 'var(--crit)' : n.flags ? 'var(--amber)' : 'var(--accent)');
</script>

<section class="case" aria-label="Account graph">
	<div class="case-head"><b>Account graph</b></div>
	<div class="case-body">
	{#if graph.nodes.length > 1}
		<svg viewBox="0 0 {SIZE} {SIZE}" role="img" aria-label="Accounts linked to this person" style="max-width: 100%; height: auto">
			{#each graph.edges as e}
				{@const a = pos.get(e.a)}
				{@const b = pos.get(e.b)}
				{#if a && b}<line x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke="var(--line)" stroke-width="2"><title>{KIND[e.kind] ?? e.kind}: {e.evidence}</title></line>{/if}
			{/each}
			{#each graph.nodes as n (n.id)}
				{@const p = pos.get(n.id)}
				{#if p}
					<a href="/review/people/{n.id}">
						<circle cx={p[0]} cy={p[1]} r={n.focus ? 14 : 10} fill={tone(n)} opacity={n.active ? 1 : 0.4}><title>{n.name} · {n.role}{n.fraud ? ' · found fraudulent' : ''}{n.flags ? ` · ${n.flags} flags` : ''}</title></circle>
						<text x={p[0]} y={p[1] + 26} text-anchor="middle" font-size="11" fill="var(--ink)">{n.name}</text>
					</a>
				{/if}
			{/each}
		</svg>
		<p class="small muted">Red: found fraudulent. Amber: has flags. Faded: account closed or off. Hover a line to see what's shared.</p>
	{:else}
		<p class="small muted">No links to other accounts.</p>
	{/if}
	</div>
</section>
