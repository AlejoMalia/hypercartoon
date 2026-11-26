/**
 * restructure.ts — where a block would work better.
 *
 * The engine knows the tension of every chapter and who appears in it. A chapter that sits where the story is still warming up but carries the tension of a climax,
 * or a flat stretch right before the end, can be read as a misplaced block. This does not rewrite anything: it proposes MOVES of whole chapters, ranked by how much closer
 * they bring the tension curve to the shape of a story that rises, breathes and peaks near the end, and it only proposes the moves that keep the story possible:
 *
 *   · a character is still introduced in the same chapter it was (nobody appears before being introduced);
 *   · dated entries, numbered chapters and the parts of a book keep their order (a diary does not run backwards).
 *
 * The weights decide: a move is worth what it gains, and the proposal says which pages to read on both sides of the new place.
 */
import type { NodesResult } from './engine';

export interface MoveProposal {
  chapter: number; title: string;
  from: number; to: number;
  /** the chapter that will stand right before it, null when it opens the book */
  after: number | null; afterTitle: string | null;
  /** percentage by which the distance to the target curve (and the break in continuity) falls */
  gain: number;
  tension: number;
  reason: string[];
  /** the measurements behind `reason`, so a report in any language can say it in its own words */
  facts: { tension: number; fromTarget: number; toTarget: number; follows: number[]; flatBefore: number[] | null; introduces: string[] };
  /** what the move keeps intact */
  keeps: string[];
  readPages: [number, number][];
}
export interface Restructure {
  /** tension of every chapter in the order of the work, and in the order the proposals would leave */
  before: { tension: number[]; fit: number };
  after:  { tension: number[]; fit: number; order: number[] };
  /** the curve of a story that rises, breathes and peaks near the end (0–100) */
  target: number[];
  proposals: MoveProposal[];
  /** chapters that cannot move, and why */
  pinned: { chapter: number; why: string }[];
}

/** A story that rises with waves, peaks around 85% and resolves. */
export const targetAt = (p: number) => p <= 0.85 ? 22 + 78 * Math.pow(p / 0.85, 1.35) : 100 - 62 * Math.pow((p - 0.85) / 0.15, 1.1);
export const isPartTitle = (t: string) => PART.test(t);
const PART = /^\s*(primer[ao]?|segund[ao]?|tercer[ao]?|cuart[ao]?|quint[ao]?|sext[ao]?|first|second|third|fourth|fifth|sixth|part|parte|libro|book|acto|act)\b.*\b(parte|part)\b|^\s*(part|parte|libro|book|acto|act)\b/i;
const DATED = /\b(d[ií]a|day)\s+\d+|\b\d{1,2}\s+de\s+\p{L}+|\b(chapter|cap[ií]tulo)\s+\d+|^\s*\d+[.)]?\s/iu;

export function proposeRestructure(r: NodesResult, maxProposals = 6): Restructure {
  const n = r.chapters.length;
  const t = r.chapters.map(c => c.tension);
  const target = Array.from({ length: n }, (_, i) => Math.round(targetAt(n > 1 ? i / (n - 1) : 0)));
  // what is measured: distance to the curve outside a tolerance band (a chapter a little off its ideal is not a fault) + the continuity of cast between neighbours (a block should
  // not land between chapters that share nothing with it)
  const BAND = 12, CONT = 150, MAXMOVE = Math.max(3, Math.min(6, Math.round(n * 0.15)));
  const cast = r.chapters.map(c => new Set(c.nodes));
  const jac = (a: number, b: number) => { const A = cast[a], B = cast[b]; if (!A.size || !B.size) return 0.5; let i = 0; for (const x of A) if (B.has(x)) i++; return i / (A.size + B.size - i); };
  const fit = (ord: number[]) => ord.reduce((a, ci, pos) => a + Math.max(0, Math.abs(t[ci] - target[pos]) - BAND) ** 2 + (pos ? CONT * (1 - jac(ord[pos - 1], ci)) : 0), 0);
  const rms = (ord: number[]) => Math.sqrt(ord.reduce((a, ci, pos) => a + Math.max(0, Math.abs(t[ci] - target[pos]) - BAND) ** 2, 0) / Math.max(1, ord.length));
  const pinned: Restructure['pinned'] = [];
  r.chapters.forEach((c, i) => { if (PART.test(c.title)) pinned.push({ chapter: i + 1, why: 'a part of the book: it marks an act and keeps its place' }); else if (DATED.test(c.title)) pinned.push({ chapter: i + 1, why: 'dated or numbered: its order is part of the story' }); });
  const isPinned = new Set(pinned.map(p => p.chapter - 1));
  const isDated = new Set(r.chapters.map((c, i) => DATED.test(c.title) && !PART.test(c.title) ? i : -1).filter(i => i >= 0));

  // who appears in which chapter (the characters that carry the work), and where each is first introduced
  const major = r.dossiers.filter(d => d.kind === 'character' && d.presence.mentions >= 8);
  const inCh = (name: string) => new Set(r.dossiers.find(d => d.name === name)?.presence.chapters.map(c => c - 1) ?? []);
  const presence = major.map(d => ({ name: d.name, chapters: inCh(d.name) }));
  const firstIn = (ord: number[], chs: Set<number>) => { for (const ci of ord) if (chs.has(ci)) return ci; return -1; };
  const original = Array.from({ length: n }, (_, i) => i);
  const introducer = presence.map(p => firstIn(original, p.chapters));
  const keepsIntroductions = (ord: number[]) => presence.every((p, i) => firstIn(ord, p.chapters) === introducer[i]);

  const apply = (ord: number[], k: number, to: number) => { const o = ord.filter(x => x !== k); o.splice(to, 0, k); return o; };
  let order = original.slice(), base = fit(order);
  const baseFit = base;
  const proposals: MoveProposal[] = [], moved = new Set<number>();
  for (let step = 0; step < maxProposals && n >= 4; step++) {
    let best: { k: number; to: number; cost: number } | null = null;
    for (const k of order) {
      if (isPinned.has(k) || moved.has(k)) continue;
      const from = order.indexOf(k);
      for (let to = Math.max(0, from - MAXMOVE); to <= Math.min(n - 1, from + MAXMOVE); to++) {
        if (to === from) continue;
        const cand = apply(order, k, to);
        // pinned chapters must keep their relative order and their positions among themselves
        const pinOrder = cand.filter(x => isPinned.has(x)), pinOrig = order.filter(x => isPinned.has(x));
        // a diary is read in a row: nothing may be inserted between two dated entries
        if (isDated.has(cand[to - 1] ?? -1) && isDated.has(cand[to + 1] ?? -1)) continue;
        if (pinOrder.join() !== pinOrig.join() || !keepsIntroductions(cand)) continue;
        const c = fit(cand);
        if (!best || c < best.cost) best = { k, to, cost: c };
      }
    }
    if (!best || best.cost >= base * 0.96) break;           // a move must be worth at least 4% of the distance
    const from = order.indexOf(best.k), next = apply(order, best.k, best.to);
    const stand = next[best.to - 1], ch = r.chapters[best.k];
    const reason: string[] = [`its tension is ${t[best.k]} and it stands at position ${from + 1} of ${n}, where the curve of a story asks for about ${target[from]}; at position ${best.to + 1} it asks for ${target[best.to]}`];
    const before = order.slice(Math.max(0, best.to - 3), best.to).map(x => t[x]), prev = order.slice(Math.max(0, from - 3), from).map(x => t[x]);
    if (before.length) reason.push(`it would follow tensions ${before.join(', ')}`);
    if (prev.length && Math.max(...prev) - Math.min(...prev) <= 15) reason.push(`where it stands now the stretch before it is flat (${prev.join(', ')})`);
    const intro = presence.filter((_, i) => introducer[i] === best!.k).map(p => p.name);
    const pg = (ci: number): [number, number] => r.chapters[ci].pages;
    proposals.push({ facts: { tension: t[best.k], fromTarget: target[from], toTarget: target[best.to], follows: before, flatBefore: prev.length && Math.max(...prev) - Math.min(...prev) <= 15 ? prev : null, introduces: intro }, chapter: best.k + 1, title: ch.title, from: from + 1, to: best.to + 1, after: stand === undefined ? null : stand + 1, afterTitle: stand === undefined ? null : r.chapters[stand].title,
      gain: Math.round((base - best.cost) / Math.max(1, baseFit) * 1000) / 10, tension: t[best.k], reason,
      keeps: [intro.length ? `${intro.join(', ')} still ${intro.length > 1 ? 'are' : 'is'} introduced in this chapter` : 'every character is introduced where it was', 'dated entries and parts keep their order'],
      readPages: [pg(best.k), ...(stand !== undefined ? [pg(stand)] : []), ...(next[best.to + 1] !== undefined ? [pg(next[best.to + 1])] : [])] });
    order = next; base = best.cost; moved.add(best.k);
  }
  return { before: { tension: t, fit: Math.round(rms(original)) }, after: { tension: order.map(i => t[i]), fit: Math.round(rms(order)), order: order.map(i => i + 1) }, target, proposals, pinned };
}
