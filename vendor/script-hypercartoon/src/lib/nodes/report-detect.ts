/**
 * report-detect.ts — how many themes, strengths and weaknesses a work has is decided by the work, never by a template.
 *
 * Every candidate is scored against the others of its own family (z-score); the ones that stand out are kept, however
 * many that is. Everything is read from the chain of words: for each word of the book — the basic ones included — the
 * engine knows how often it occurs, where (page, chapter, slice of the book), what stands right before and after it and
 * its solar system (the words around it between two full stops, the rare ones weighing more). That is what lets a
 * stock phrase, an over-used connective, a flat stretch or a motif that keeps coming back be seen without any list.
 */
import type { NodesResult } from './engine';

export interface WordProof {
  word: string; n: number; pages: number; chapters: number;
  /** its solar system (rare neighbours first) */
  orbit: string[];
  /** the characters and places it keeps company with */
  near: string[];
  /** what most often follows it */
  after: string | null;
}
export interface Finding {
  id:       string;
  family:   string;
  title:    string;
  /** how far it stands from the rest of its family, in standard deviations */
  salience: number;
  evidence: string[];
  /** the word chains the finding rests on */
  words:    WordProof[];
}

const mean = (a: number[]) => a.length ? a.reduce((x, y) => x + y, 0) / a.length : 0;
const sd = (a: number[]) => { const m = mean(a); return Math.sqrt(mean(a.map(x => (x - m) ** 2))) || 1e-9; };
const zs = (a: number[]) => { const m = mean(a), s = sd(a); return a.map(x => (x - m) / s); };

export function proof(r: NodesResult, word: string): WordProof | null {
  const e = r.wordIndex[word.toLowerCase()]; if (!e) return null;
  return { word, n: e.n, pages: e.pages, chapters: e.chapters.filter(c => c > 0).length, orbit: e.orbit.slice(0, 6), near: e.near.slice(0, 4), after: e.after[0]?.[0] ?? null };
}
const proofs = (r: NodesResult, ws: string[]) => ws.map(w => proof(r, w)).filter((p): p is WordProof => !!p);

/** keep the candidates that stand out from their family (z above what a family of that size produces by chance); a family with a single candidate keeps it when it clears `floor` */
function standouts<T>(items: T[], score: (t: T) => number, floor: number, chance = true): { item: T; z: number }[] {
  if (!items.length) return [];
  if (items.length === 1) return score(items[0]) >= floor ? [{ item: items[0], z: score(items[0]) / Math.max(floor, 1e-9) }] : [];
  const sc = items.map(score), z = zs(sc).map(v => Math.min(v, 99));
  const cut = chance ? Math.max(1, Math.sqrt(2 * Math.log(items.length))) : 1;       // the largest z a family of this size throws up by itself: only what rises above it counts
  return items.map((item, i) => ({ item, z: z[i], s: sc[i] })).filter(x => x.z >= cut && x.s >= floor).map(({ item, z }) => ({ item, z }));
}

// ───────────────────────────── THEMES ─────────────────────────────
/** A theme is a tree of elements (motif, concentrated theme, action) carried through the chapters. The weight is how much of the book it covers, how often, and how its words hold together. */
export function detectThemes(r: NodesResult): Finding[] {
  // a word that heads the work’s own parts and chapters is scaffolding, not a theme
  const titleWords = new Set(r.chapters.flatMap(c => c.title.toLowerCase().split(/[^\p{L}]+/u)).filter(Boolean)), scaffold = new Set([...r.structuralWords.map(w => w.toLowerCase()), ...titleWords]);
  const trees = r.themeForest.filter(t => t.mentions >= 3 && !scaffold.has(t.root.toLowerCase()));
  const out: Finding[] = [];
  for (const { item: t, z } of standouts(trees, t => t.share * Math.log(1 + t.mentions) * (1 + 0.15 * t.branches.length), 0, false)) {
    const th = r.morphisms.thematic.find(x => x.root === t.root);
    out.push({
      id: `theme:${t.root}`, family: 'theme', title: t.root, salience: Math.round(z * 100) / 100,
      evidence: [`${t.class}, ${t.flow}, in ${Math.round(t.share * 100)}% of the chapters (${t.mentions} mentions)`, t.branches.length ? `grows: ${t.branches.slice(0, 6).map(b => b.word).join(', ')}` : '', t.peaks.length ? `peaks in chapters ${t.peaks.join(', ')}` : '', th ? `${th.verdict} (${Math.round(th.preservation * 100)}% of its relations survive from the first half to the second)` : ''].filter(Boolean),
      words: proofs(r, [t.root, ...t.branches.slice(0, 5).map(b => b.word)]),
    });
  }
  return out.sort((a, b) => b.salience - a.salience);
}

// ───────────────────────────── STRENGTHS ─────────────────────────────
export function detectStrengths(r: NodesResult): Finding[] {
  const out: Finding[] = [];

  // 1. characters that really transform (arc far from the identity map, read on enough mentions)
  for (const { item: a, z } of standouts(r.arcs.filter(a => a.confidence >= 0.5), a => (1 - a.identity) * a.confidence, 0.2)) {
    out.push({ id: `arc:${a.node}`, family: 'transformation', title: `The arc of ${a.node}`, salience: z,
      evidence: [`${a.verdict}: ${Math.round((1 - a.identity) * 100)}% of its circle changes (${a.basis}); charge ${a.chargeEarly} → ${a.chargeLate} (${a.direction})`, `kept ${a.kept.slice(0, 4).join(', ') || '—'} · lost ${a.lost.slice(0, 4).join(', ') || '—'} · gained ${a.gained.slice(0, 4).join(', ') || '—'}`],
      words: proofs(r, [a.node, ...a.gained.slice(0, 3), ...a.lost.slice(0, 3)]) });
  }
  // 2. structural echoes: chapters that repeat a skeleton with another cast
  for (const { item: p, z } of standouts(r.morphisms.parallels, p => p.similarity * (1 - p.castOverlap * 0.5), 0.5)) {
    out.push({ id: `echo:${p.a.chapter}-${p.b.chapter}`, family: 'structure', title: `${p.kind === 'echo' ? 'Echo' : 'Hidden parallel'}: chapters ${p.a.chapter} and ${p.b.chapter}`, salience: z,
      evidence: [`same skeleton of relations (${Math.round(p.similarity * 100)}%) with ${Math.round((1 - p.castOverlap) * 100)}% of the cast different`, `map: ${p.mapping.slice(0, 5).map(([x, y]) => `${x}↦${y}`).join(', ')}`], words: [] });
  }
  // 3. rhythm: chapters whose charge swings against their neighbours (a book that breathes)
  { const ar = r.chapters.map(c => c.tone.arousal); if (ar.length >= 4) {
      const swing = ar.map((v, i) => i ? Math.abs(v - ar[i - 1]) : 0); const hi = standouts(r.chapters.map((c, i) => ({ c, s: swing[i] })).filter(x => x.s > 0), x => x.s, 0);
      if (hi.length >= 1 && sd(ar) > 4) out.push({ id: 'rhythm', family: 'rhythm', title: 'Rhythm of intensity between chapters', salience: Math.max(...hi.map(h => h.z)),
        evidence: [`arousal moves between ${Math.min(...ar)} and ${Math.max(...ar)} with the sharpest turns into chapters ${hi.slice(0, 4).map(h => h.item.c.index).join(', ')}`], words: [] }); } }
  // 4. a world that returns (or deliberately does not)
  if (r.worldIdentity && r.worldIdentity.circularity.verdict === 'circular' && r.worldIdentity.invariant.length >= 3) out.push({ id: 'world-return', family: 'world', title: 'A world that comes back to where it began',
      salience: 1 + r.worldIdentity.circularity.similarity,
      evidence: [`end against beginning: ${Math.round(r.worldIdentity.circularity.similarity * 100)}% alike${r.worldIdentity.circularity.samePlace ? ', in the same place' : ''}`, `unchanged: ${r.worldIdentity.invariant.slice(0, 6).map(w => w.word).join(', ')}`, `changed most: ${r.worldIdentity.drift.slice(0, 5).map(w => w.word).join(', ')}`],
      words: proofs(r, r.worldIdentity.invariant.slice(0, 5).map(w => w.word)) });
  // 5. places with a world of their own (their own words, their own people)
  for (const { item: pc, z } of standouts(r.placeCasts.filter(p => p.cast.length >= 2), p => p.cast.length * Math.log(1 + p.mentions) * (1 + p.meetings.length), 0)) {
    out.push({ id: `place:${pc.place}`, family: 'place', title: `${pc.place} as a place with life`, salience: z,
      evidence: [`${pc.cast.length} people live or pass through it (natives: ${pc.cast.filter(c => c.role === 'native').map(c => c.name).join(', ') || '—'}); ${pc.meetings.length} meetings`], words: proofs(r, [pc.place]) });
  }
  // 6. distinct voices: characters whose dialogue share differs clearly from the rest
  { const ch = r.dossiers.filter(d => d.kind === 'character' && d.presence.mentions >= 15);
    for (const { item: d, z } of standouts(ch, d => Math.abs(d.voice.dialogue - mean(ch.map(x => x.voice.dialogue))), 0.15)) out.push({ id: `voice:${d.name}`, family: 'voice', title: `A distinct voice: ${d.name}`, salience: z,
      evidence: [`${Math.round(d.voice.dialogue * 100)}% dialogue against ${Math.round(mean(ch.map(x => x.voice.dialogue)) * 100)}% for the cast`, `distinctive words: ${d.traits.elements.slice(0, 5).join(', ')}`], words: proofs(r, d.traits.elements.slice(0, 4)) }); }
  return dedupe(out).sort((a, b) => b.salience - a.salience);
}

// ───────────────────────────── WEAKNESSES ─────────────────────────────
export function detectWeaknesses(r: NodesResult): Finding[] {
  const out: Finding[] = [];
  const wi = r.wordIndex;
  const nameWord = new Set<string>(); for (const n of r.nodes) for (const w of n.name.toLowerCase().split(/\s+/)) nameWord.add(w);       // a name repeated is not a tic

  // 1. stock phrases: a content word almost always followed by the same content word (read from the chain of every word)
  { const cands = Object.entries(wi).filter(([w, e]) => e.n >= 20 && w.length >= 3 && !e.function && !nameWord.has(w) && e.after[0] && e.after[0][1] / e.n >= 0.3 && e.after[0][0].length >= 3 && !nameWord.has(e.after[0][0]) && wi[e.after[0][0]] && !wi[e.after[0][0]].function);
    for (const { item: [w, e], z } of standouts(cands, ([, e]) => (e.after[0][1] / e.n) * Math.log(e.n), 0)) out.push({ id: `tic:${w}`, family: 'repetition', title: `Stock phrase: «${w} ${e.after[0][0]}»`, salience: z,
      evidence: [`${Math.round(e.after[0][1] / e.n * 100)}% of the ${e.n} times «${w}» appears it is followed by «${e.after[0][0]}»`], words: proofs(r, [w, e.after[0][0]]) }); }

  // 3. flat stretches: chapters whose charge barely moves from the rest
  { const ch = r.chapters.filter(c => !c.inferred && c.words > 200);
    if (ch.length >= 5) for (const { item: c, z } of standouts(ch, c => -(c.tone.arousal - mean(ch.map(x => x.tone.arousal))), 5)) out.push({ id: `flat:${c.index}`, family: 'pace', title: `A flat stretch: chapter ${c.index} «${c.title}»`, salience: z,
      evidence: [`arousal ${c.tone.arousal} against ${Math.round(mean(ch.map(x => x.tone.arousal)))} for the book`, `${c.events.length} scenes, carried by ${c.nodes.slice(0, 3).join(', ') || 'no named node'}`], words: proofs(r, c.signature.slice(0, 3)) }); }

  // 4. chapters the rhythm says are missing, or that had to be inferred
  { const inf = r.chapters.filter(c => c.inferred); if (inf.length) out.push({ id: 'gaps', family: 'structure', title: 'Chapters the book\'s own rhythm says are missing or unmarked', salience: 1 + inf.length / r.chapters.length * 4,
      evidence: [`chapters ${inf.map(c => c.index).join(', ')} had no heading and were recovered from the spacing (${inf.map(c => c.inferredBy).join(', ')})`], words: [] }); }

  // 5. protagonists who vanish: a long silence in the chain of a primary character
  for (const d of r.dossiers.filter(d => d.kind === 'character' && d.rank === 'primary')) {
    const den = d.presence.density; if (den.length < 8) continue;
    let run = 0, best = 0, at = 0; den.forEach((v, i) => { run = v === 0 ? run + 1 : 0; if (run > best) { best = run; at = i - run + 1; } });
    if (best / den.length >= 0.2 && at > 0 && at + best < den.length) out.push({ id: `absent:${d.name}`, family: 'presence', title: `${d.name} disappears for a fifth of the book`, salience: 1 + best / den.length * 5,
      evidence: [`no mention in ${best} of ${den.length} slices (from slice ${at + 1}), though it appears before and after`], words: proofs(r, [d.name]) });
  }
  // 7. names that could be two people or one (the identity stage kept them apart or refused to merge)
  for (const k of r.injectivity.keptApart.slice(0, 3)) out.push({ id: `confusable:${k.a ?? ''}${k.b ?? ''}`, family: 'identity', title: `Two characters who live in the same surroundings: ${k.a} and ${k.b}`, salience: 1 + k.similarity,
    evidence: [`their surroundings are ${Math.round(k.similarity * 100)}% alike (${k.sharedPages} shared pages) though they are different people: easy to blur`], words: proofs(r, [k.a, k.b].filter(Boolean) as string[]) });
  // 8. dialogue deserts: chapters with no speech in a book that speaks
  { const mixes = r.chapters.map(c => c.mix.dialogue); if (mean(mixes) > 0.1) { const dry = r.chapters.filter(c => c.mix.dialogue < 0.02 && c.words > 300); if (dry.length && dry.length < r.chapters.length) out.push({ id: 'dry', family: 'voice', title: 'Chapters without a single line of speech', salience: 1 + dry.length / r.chapters.length * 3,
      evidence: [`chapters ${dry.map(c => c.index).join(', ')} against ${Math.round(mean(mixes) * 100)}% dialogue for the book`], words: [] }); } }
  return dedupe(out).sort((a, b) => b.salience - a.salience);
}

function dedupe(f: Finding[]): Finding[] { const seen = new Set<string>(); return f.filter(x => (seen.has(x.id) ? false : (seen.add(x.id), true))); }
