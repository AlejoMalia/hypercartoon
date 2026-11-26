/**
 * completion.ts — what a model needs to finish a story that stops.
 *
 * An analysis that sees the text as a flat sequence can say what happened; it cannot say what is left. The node engine knows, for every character, place and theme,
 * where it was last seen, with whom, in what tone, and whether its trajectory was closed or left in the air. This reads that map at the end of the work:
 *
 *   endsAt       where the text stops (chapter, scene, place, who is on stage, tension)
 *   alive        the nodes that are still on stage in the last stretch, each with place, company and tone
 *   openThreads  what was started and not closed, strongest first, each with the evidence and the pages to read
 *   closedThreads what did close
 *
 * Nothing is invented: every thread is a measurement of the map. Deciding HOW to close it is the model’s work, and it knows which pages to read.
 */
import type { NodesResult } from './engine';

export type ThreadKind = 'vanished character' | 'unresolved bond' | 'building theme' | 'dark arc' | 'tension left high' | 'missing chapter' | 'abandoned place';
export interface Thread {
  kind: ThreadKind; subject: string;
  /** 0–1, how much the work leans on it */
  weight: number;
  evidence: string[];
  /** where it was last seen */
  lastSeen: { page: number; chapter: number } | null;
  /** the pages worth reading to continue it */
  readPages: [number, number][];
}
export interface CompletionBrief {
  endsAt: { page: number; of: number; chapter: number; chapterTitle: string; place: string | null; actors: string[]; tension: number; peak: number; tone: string; scene: string[] };
  alive: { name: string; kind: string; lastPage: number; place: string | null; with: string[]; valence: number; tension: number }[];
  openThreads: Thread[];
  closedThreads: { kind: string; subject: string; evidence: string }[];
  /** does the end return to where the work began? null when it cannot be told */
  returnsToStart: boolean | null;
  summary: { open: number; ends: 'on a peak' | 'resolving' | 'flat'; mostUrgent: string | null };
}

const clamp = (x: number, a = 0, b = 1) => Math.max(a, Math.min(b, x));

export function buildCompletionBrief(r: NodesResult): CompletionBrief {
  // the end of the STORY: the notes, index and acknowledgments after the last chapter are not where it stops
  const L = Math.max(1, r.structure.body ? Math.min(r.layers, r.structure.body[1]) : r.layers), tail = Math.max(1, Math.round(L * 0.1)), endFrom = L - tail + 1;
  const lastCh = r.chapters[r.chapters.length - 1];
  const curve = r.tension.curve, endT = curve.filter(c => c.page >= endFrom).map(c => c.tension), allT = curve.map(c => c.tension);
  const endTension = endT.length ? Math.round(endT.reduce((a, b) => a + b, 0) / endT.length) : 0, peak = allT.length ? Math.max(...allT) : 0;
  const lastScene = lastCh?.events[lastCh.events.length - 1];
  const chOfPage = (pg: number) => { let c = 1; for (const ch of r.chapters) if (pg >= ch.pages[0]) c = ch.index; return c; };
  const readAround = (pg: number): [number, number] => [Math.max(1, pg - 1), Math.min(L, pg + 1)];

  // who is still on stage in the last stretch
  const lastLayers = r.map4d.layers.filter(l => l.page >= endFrom);
  const stage = new Map<string, { n: number; last: number; place: string | null; with: Map<string, number>; v: number; t: number }>();
  for (const l of lastLayers) for (const n of l.nodes) { const c = stage.get(n.name) ?? stage.set(n.name, { n: 0, last: 0, place: null, with: new Map(), v: 0, t: 0 }).get(n.name)!; c.n += n.n; c.last = Math.max(c.last, l.page); c.place = n.place ?? c.place; for (const w of n.with) c.with.set(w, (c.with.get(w) ?? 0) + 1); c.v += n.tone.valence * n.n; c.t += n.tone.tension * n.n; }
  const alive = [...stage].sort((a, b) => b[1].n - a[1].n).slice(0, 12).map(([name, c]) => ({ name, kind: r.nodes.find(x => x.name === name)?.kind ?? 'character', lastPage: c.last, place: c.place, with: [...c.with].sort((a, b) => b[1] - a[1]).slice(0, 3).map(x => x[0]), valence: Math.round(c.v / c.n), tension: Math.round(c.t / c.n) }));

  const open: Thread[] = [], closed: CompletionBrief['closedThreads'] = [];
  const maxMentions = Math.max(1, ...r.dossiers.map(d => d.presence.mentions));

  // 1. characters that carried the work and are no longer there
  for (const d of r.dossiers) {
    if (d.kind !== 'character' || d.presence.mentions < 8) continue;
    const gone = d.presence.last < L * 0.85, weight = clamp(0.55 * (d.presence.mentions / maxMentions) ** 0.5 + 0.45 * d.presence.share);
    if (gone) open.push({ kind: 'vanished character', subject: d.name, weight: Math.round(weight * 100) / 100, evidence: [`${d.presence.mentions} mentions over ${d.presence.chapters.length} chapters, last seen on page ${d.presence.last} of ${L}`, d.lastSeen.line ? `last line: «${d.lastSeen.line.slice(0, 110)}»` : '', d.tone ? `its tone at the end of its line: ${d.tone.trend}` : ''].filter(Boolean), lastSeen: { page: d.presence.last, chapter: d.lastSeen.chapter }, readPages: [readAround(d.presence.last), ...(d.introduced.page ? [[d.introduced.page, d.introduced.page] as [number, number]] : [])] });
    else if (d.presence.first > L * 0.1 || d.presence.mentions >= 20) closed.push({ kind: 'character present to the end', subject: d.name, evidence: `last seen on page ${d.presence.last} of ${L}` });
  }
  // 2. bonds that were still tightening when the stretch they share ends
  for (const p of r.tension.pairs) {
    if (p.sentences < 5) continue;
    const endsLate = p.pages[1] >= L * 0.6, tense = p.bond === 'hostile' || p.bond === 'strained';
    if (tense && p.trend === 'escalates' && endsLate) open.push({ kind: 'unresolved bond', subject: `${p.a} + ${p.b}`, weight: Math.round(clamp(p.tension / 100 * 0.6 + Math.min(0.4, Math.log10(p.sentences) * 0.25)) * 100) / 100, evidence: [`${p.bond}, tension ${p.tension} and rising over ${p.sentences} sentences (pages ${p.pages[0]}–${p.pages[1]})`, p.peak ? `peak of the bond on page ${p.peak}` : ''].filter(Boolean), lastSeen: { page: p.pages[1], chapter: chOfPage(p.pages[1]) }, readPages: [...(p.peak ? [readAround(p.peak)] : []), readAround(p.pages[1])] });
    else if (p.trend === 'eases' && p.sentences >= 8) closed.push({ kind: 'bond that eased', subject: `${p.a} + ${p.b}`, evidence: `tension falls over pages ${p.pages[0]}–${p.pages[1]}` });
  }
  // 3. themes that were still building at the end
  for (const t of r.themeForest) if (t.flow === 'builds' && t.mentions >= 6) open.push({ kind: 'building theme', subject: t.root, weight: Math.round(clamp(t.share * 0.7) * 100) / 100, evidence: [`a ${t.class} that grows through the work (${t.mentions} mentions, ${Math.round(t.share * 100)}% of the chapters) and has not peaked`, t.branches.length ? `grows: ${t.branches.slice(0, 4).map(b => b.word).join(', ')}` : ''].filter(Boolean), lastSeen: t.chapters.length ? { page: r.chapters[t.chapters[t.chapters.length - 1] - 1]?.pages[1] ?? L, chapter: t.chapters[t.chapters.length - 1] } : null, readPages: t.chapters.slice(-2).map(c => r.chapters[c - 1]?.pages).filter((x): x is [number, number] => !!x) });
  // 4. arcs that ended dark or half-done for the characters that carry the work
  for (const a of r.arcs) { const d = r.dossiers.find(x => x.name === a.node); if (!d || d.kind !== 'character' || d.rank !== 'primary' || a.confidence < 0.5) continue;
    if (a.verdict !== 'identity' && a.direction === 'falls') open.push({ kind: 'dark arc', subject: a.node, weight: Math.round(clamp(0.5 + (1 - a.identity) * 0.4) * 100) / 100, evidence: [`its surroundings change (${a.verdict}) and the charge falls from ${a.chargeEarly} to ${a.chargeLate}`, `lost ${a.lost.slice(0, 3).join(', ') || '—'} · gained ${a.gained.slice(0, 3).join(', ') || '—'}`], lastSeen: { page: d.presence.last, chapter: d.lastSeen.chapter }, readPages: [readAround(d.presence.last), ...(d.climax ? [d.climax.pages] : [])] });
    else if (a.verdict === 'identity') closed.push({ kind: 'character unchanged', subject: a.node, evidence: 'its surroundings at the end are those of the beginning' }); }
  // 5. the text stops while the tension is still near its peak
  const endsHigh = peak > 0 && endTension >= peak * 0.7;
  if (endsHigh) open.push({ kind: 'tension left high', subject: `pages ${endFrom}–${L}`, weight: Math.round(clamp(endTension / 100) * 100) / 100, evidence: [`tension at the end ${endTension} against a peak of ${peak}`, ...(r.tension.peaks.length ? [`peaks of the work: pages ${r.tension.peaks.join(', ')}`] : [])], lastSeen: { page: L, chapter: lastCh?.index ?? 1 }, readPages: [[endFrom, L], ...(r.tension.peaks.length ? [readAround(r.tension.peaks[r.tension.peaks.length - 1])] : [])] });
  // 6. chapters the rhythm of the work says are missing
  for (const c of r.chapters.filter(c => c.inferred)) open.push({ kind: 'missing chapter', subject: `chapter ${c.index}`, weight: 0.5, evidence: [`no heading was found; recovered from the spacing (${c.inferredBy ?? 'rhythm'})`], lastSeen: { page: c.pages[0], chapter: c.index }, readPages: [c.pages] });
  // 7. places the story left and never came back to
  for (const pc of r.placeCasts) { if (pc.mentions < 6 || pc.pages[1] >= L * 0.8) continue; const d = r.dossiers.find(x => x.name === pc.place); open.push({ kind: 'abandoned place', subject: pc.place, weight: Math.round(clamp(Math.log10(pc.mentions + 1) / 2) * 60) / 100, evidence: [`${pc.mentions} mentions, last on page ${pc.pages[1]} of ${L}`, pc.cast.length ? `who weighed there: ${pc.cast.slice(0, 3).map(c => c.name).join(', ')}` : ''].filter(Boolean), lastSeen: { page: pc.pages[1], chapter: chOfPage(pc.pages[1]) }, readPages: [readAround(pc.pages[1]), ...(d?.climax ? [d.climax.pages] : [])] }); }

  // a family with many candidates keeps only those that stand out from the others of its kind
  const kept: Thread[] = [];
  for (const kind of [...new Set(open.map(t => t.kind))]) { const fam = open.filter(t => t.kind === kind).sort((a, b) => b.weight - a.weight); if (fam.length <= 3) { kept.push(...fam); continue; } const mu = fam.reduce((a, t) => a + t.weight, 0) / fam.length, sd = Math.sqrt(fam.reduce((a, t) => a + (t.weight - mu) ** 2, 0) / fam.length); kept.push(...fam.filter((t, i) => i < 3 || t.weight >= mu + 0.5 * sd)); }
  open.length = 0; open.push(...kept);
  open.sort((a, b) => b.weight - a.weight);
  const returns = r.worldIdentity ? r.worldIdentity.circularity.verdict === 'circular' : null;
  const lastPlace = lastScene?.place ?? alive.find(a => a.place)?.place ?? null;
  return {
    endsAt: { page: L, of: L, chapter: lastCh?.index ?? 0, chapterTitle: lastCh?.title ?? '', place: lastPlace, actors: lastScene?.actors ?? alive.slice(0, 4).map(a => a.name), tension: endTension, peak, tone: lastCh?.tone.label ?? 'neutral', scene: lastScene?.words.slice(0, 8) ?? [] },
    alive, openThreads: open, closedThreads: closed.slice(0, 20), returnsToStart: returns,
    summary: { open: open.length, ends: endsHigh ? 'on a peak' : endTension >= peak * 0.4 ? 'resolving' : 'flat', mostUrgent: open[0] ? `${open[0].kind}: ${open[0].subject}` : null },
  };
}
