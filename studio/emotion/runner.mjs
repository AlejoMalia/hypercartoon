// Persistent EmotionsHypercartoon bridge: one JSON request per stdin line, one "@@"-prefixed JSON reply per line.
// Engine logs on stdout are ignored by the Python side because only "@@" lines are parsed.
import readline from 'node:readline'
import { pathToFileURL } from 'node:url'

const { EmotionsHypercartoon, Personality } = await import(pathToFileURL(process.env.EMOTIONS_SRC).href)
const agents = new Map()
const out = o => process.stdout.write('@@' + JSON.stringify(o) + '\n')
const num = x => (typeof x === 'number' && Number.isFinite(x) ? x : null)

function agent(id, personality) {
	if (!agents.has(id)) {
		const t = new EmotionsHypercartoon({ personality: new Personality(personality || {}) })
		// scripted turns arrive back-to-back: relax the sensory-overload burst window (same as the upstream demo)
		t.sensoryOverload = new (t.sensoryOverload.constructor)({ burstThreshold: 1e6 })
		agents.set(id, t)
	}
	return agents.get(id)
}

for await (const line of readline.createInterface({ input: process.stdin })) {
	if (!line.trim()) continue
	try {
		const m = JSON.parse(line)
		if (m.op === 'reset') { agents.clear(); out({ ok: true }); continue }
		const a = agent(m.character, m.personality)
		const r = await a.processInput(m.text, { userId: m.speaker || 'other' })
		a.tick?.(m.ticks ?? 1)
		const s = r.emotionalState || {}
		out({
			ok: true, vector: s.vector || null, dominant: s.dominantEmotion ?? null, mood: s.moodLabel ?? null,
			blend: s.blend ?? null, tags: r.styleTags || [], delayMs: num(r.delayMs), cortisol: num(s.cortisol),
			gestalt: r.gestalt ? (r.gestalt.archetype ?? r.gestalt.dominant ?? r.gestalt.name ?? null) : null,
		})
	} catch (e) {
		out({ ok: false, error: String(e && e.message || e) })
	}
}
