// Persistent bridge to the vendored script-hypercartoon engines (vendor/script-hypercartoon/engines.mjs): deterministic, offline, plain Node.
// One JSON request per stdin line -> one "@@"-prefixed JSON reply. Only the basic screenplay-reading op is exposed: no generic,
// cross-domain node-graph analysis of arbitrary prose, and no passthrough to arbitrary vendored functions.
import readline from 'node:readline'
import { fileURLToPath, pathToFileURL } from 'node:url'
import path from 'node:path'

const here = path.dirname(fileURLToPath(import.meta.url))
const E = await import(pathToFileURL(path.join(here, '..', '..', 'vendor', 'script-hypercartoon', 'engines.mjs')).href)
const out = o => process.stdout.write('@@' + JSON.stringify(o) + '\n')

function slimScreenplay(r) {
	const e = r.engine ?? {}
	return {
		isScreenplay: r.isScreenplay, confidence: r.confidence, stats: r.stats, acts: r.acts,
		scenes: (r.scenes ?? []).map(s => ({ index: s.index, place: s.heading?.place, intExt: s.heading?.intExt, time: s.heading?.timeClass,
			cast: s.cast, dialogueShare: s.dialogueShare, speechWords: s.speechWords, actionWords: s.actionWords, tension: s.tension, pages: s.pages, camera: s.camera })),
		characters: (r.characters ?? []).map(c => ({ name: c.name, share: c.share, cues: c.cues, words: c.words, firstScene: c.firstScene, lastScene: c.lastScene, scenes: c.scenes })),
		places: (r.places ?? []).map(p => ({ place: p.place, scenes: p.scenes })),
		tension: (e.tension?.curve ?? []).map(c => ({ page: c.page, tension: c.tension })),
	}
}
const slimCompletion = b => b && {
	openThreads: (b.openThreads ?? []).map(t => ({ kind: t.kind, subject: t.subject, weight: t.weight, evidence: t.evidence })),
	summary: b.summary, endsAt: b.endsAt && { page: b.endsAt.page, of: b.endsAt.of, tension: b.endsAt.tension, peak: b.endsAt.peak }, returnsToStart: b.returnsToStart,
}

for await (const line of readline.createInterface({ input: process.stdin })) {
	if (!line.trim()) continue
	try {
		const m = JSON.parse(line)
		if (m.op === 'screenplay') {
			const r = E.screenplay.analyzeScreenplay(m.text, { language: m.language ?? 'auto' })
			out({ ok: true, reading: slimScreenplay(r), completion: m.completion ? slimCompletion(E.completion.buildCompletionBrief(r.engine)) : null })
		} else throw new Error('unknown op ' + m.op)
	} catch (e) {
		out({ ok: false, error: String(e?.message ?? e) })
	}
}
