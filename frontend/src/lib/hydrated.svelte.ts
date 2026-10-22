/**
 * `hydrated().on` turns true once the page's JavaScript runs. Buttons that wait for input (Reject
 * until a reason is picked, Send until there's text) use it so that, without JavaScript, the
 * server-rendered button is never stuck disabled: the form's own `required` rules and the API's
 * checks take over instead.
 */
export function hydrated() {
	const state = $state({ on: false });
	$effect(() => {
		state.on = true;
	});
	return state;
}
