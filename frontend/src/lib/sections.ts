// Links to a part of a page ("How it works", "Report a scam") scroll there without putting "#how" in the address bar.
// They are plain links to the page, marked with the section's id: <a href="/check" data-section="report">. Without
// JavaScript they open the page at the top. The root layout listens for clicks on them (followSectionLink) and drops
// a "#..." that arrives in an old link (showSection, then replaceState).
import { tick } from 'svelte';
import { goto } from '$app/navigation';

/** Scrolls to the element with this id and moves focus there, so the keyboard and screen readers carry on from it. */
export function showSection(id: string): boolean {
	const el = document.getElementById(id);
	if (!el) return false;
	const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
	el.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
	if (!el.hasAttribute('tabindex')) el.setAttribute('tabindex', '-1');
	el.focus({ preventScroll: true });
	return true;
}

/** Click handler (capture phase, before the router sees the click) for links with data-section. */
export async function followSectionLink(event: MouseEvent) {
	// A new tab or window keeps the browser's own behaviour: the page opens at the top.
	if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
	const link = (event.target as Element | null)?.closest<HTMLAnchorElement>('a[data-section]');
	if (!link?.dataset.section) return;
	event.preventDefault();
	const url = new URL(link.href, location.href);
	if (url.pathname !== location.pathname) {
		await goto(url.pathname + url.search);
		await tick();
	}
	showSection(link.dataset.section);
}
