import { fail } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import type { CopilotNumbers, Detector, EvaluationSnapshot, ModelVersion } from '$lib/api/types';
import { formError, str } from '$lib/server/guards';

const NAMES = /^(scam_text|scam_text_llm|price|photos|documents|accounts)$/;
const MODES = /^(off|shadow|canary|active)$/;

export const load: PageServerLoad = async ({ locals }) => {
	const [{ data, meta }, history, copilot] = await Promise.all([
		locals.api.withMeta<Detector[]>('/review/detection'),
		// The weekly history and the copilot's numbers are extra: if either fails, the models and their mode controls
		// still load.
		locals.api.get<EvaluationSnapshot[]>('/review/detection/history').catch((): EvaluationSnapshot[] => []),
		locals.api.get<CopilotNumbers>('/review/agents/copilot').catch((): CopilotNumbers | null => null)
	]);
	return { detectors: data, versions: (meta.versions as ModelVersion[]) ?? [], history, copilot };
};

export const actions: Actions = {
	/** Moving a model between modes is a rule change: it needs a second reviewer on the Rules page. */
	mode: async ({ locals, request }) => {
		const form = await request.formData();
		const name = str(form, 'name');
		const mode = str(form, 'mode');
		if (!NAMES.test(name) || !MODES.test(mode)) return fail(400, { error: 'Unknown model or mode.' });
		try {
			await locals.api.post('/review/rules', { key: `model_${name}_mode`, value: mode, source: str(form, 'source') });
			return { done: `Proposed ${mode} for this model. A second reviewer approves it on the Rules page.` };
		} catch (err) {
			return formError(err);
		}
	},
	train: async ({ locals }) => {
		try {
			const v = await locals.api.post<ModelVersion>('/review/detection/scam_text/train');
			return { done: `Trained ${v.version} on ${v.trained_on} examples. It scores in the model's current mode.` };
		} catch (err) {
			return formError(err);
		}
	}
};
