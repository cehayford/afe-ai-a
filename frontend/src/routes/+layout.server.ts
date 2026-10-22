import type { LayoutServerLoad } from './$types';
import { langFrom } from '$lib/i18n';

export const load: LayoutServerLoad = async ({ locals, cookies }) => ({
	me: locals.me,
	lang: langFrom(cookies.get('afe_lang'))
});
