// One polite live region for the whole site, in the root layout. A status region added to the page together with its
// message is often read by no screen reader at all, so messages that appear after an action (a decision saved, a
// photo uploaded) go through this one instead.
export const announcer = $state({ text: '' });

let timer: ReturnType<typeof setTimeout> | undefined;

export function announce(text: string) {
	// Emptied first, so the same message twice in a row is read twice.
	announcer.text = '';
	clearTimeout(timer);
	timer = setTimeout(() => (announcer.text = text), 100);
}
