/**
 * word-index.ts — a chain for EVERY word, the basic ones included.
 *
 * "De", "el", "agua" and "Rosenborg" are all the same kind of thing: a chain of letters that repeats. For each one the
 * engine keeps how many times it appears, where (page by page, chapter by chapter), which words come right before and
 * right after it, which words stand around it (its solar system, weighted by how rare those neighbours are) and which
 * characters or places it keeps company with. Seen together, the ordinary words show the rhythm and the grammar of the
 * book, and the rare ones show its world: nothing is left out because it is "common".
 */

export interface WordEntry {
  n:        number;
  /** a function word (article, preposition…) or a content word */
  function: boolean;
  class:    string;
  pages:    number;
  first:    number;
  last:     number;
  /** mentions per slice of the work (up to 40 slices) */
  density:  number[];
  /** mentions per chapter */
  chapters: number[];
  /** the page of every mention, when there are few enough to list */
  at?:      number[];
  before:   [string, number][];
  after:    [string, number][];
  /** the words that stand around it, the rare ones weighing more */
  orbit:    string[];
  /** the characters and places that stand around it most often */
  near:     string[];
}

export interface WordIndexInput {
  words:     string[];                    // lower-case word of every counted token, in order
  pages:     number[];                    // page of each of those tokens
  chapters:  number[];                    // chapter index of each (−1 when none)
  NP:        number;
  nChapters: number;
  isFunction: (w: string) => boolean;
  classOf:   (w: string) => string;
  /** rarity of a word (higher = rarer), used to weigh neighbours */
  rarity:    (w: string) => number;
  /** for each counted token, the name of the character/place it is a mention of (or null) */
  nodeAt:    (i: number) => string | null;
}

const STRIDE = 1 << 16;                                   // room for any number of characters and places
const TOP = (m: Map<number, number>, n: number) => [...m].sort((a, b) => b[1] - a[1]).slice(0, n);

export function buildWordIndex(inp: WordIndexInput): Record<string, WordEntry> {
  const { words, pages, chapters, NP, nChapters } = inp;
  const id = new Map<string, number>(), list: string[] = [];
  const ids = new Int32Array(words.length);
  words.forEach((w, i) => { let x = id.get(w); if (x === undefined) { x = list.length; id.set(w, x); list.push(w); } ids[i] = x; });
  const V = list.length, bins = Math.min(Math.max(NP, 1), 40);
  const total = new Int32Array(V); for (let i = 0; i < ids.length; i++) total[ids[i]]++;      // how often each word occurs, known before the main pass
  const n = new Int32Array(V), first = new Int32Array(V).fill(1 << 30), last = new Int32Array(V);
  const density = Array.from({ length: V }, () => new Uint16Array(bins));
  const chap = Array.from({ length: V }, () => new Uint16Array(Math.max(1, nChapters)));
  const pageSets = Array.from({ length: V }, () => new Set<number>());
  const at: number[][] = Array.from({ length: V }, () => []);
  const before = new Map<number, number>(), after = new Map<number, number>(), orbit = new Map<number, number>(), near = new Map<number, number>();
  const nodeId = new Map<string, number>(), nodeNames: string[] = [];
  const WIN = 6;
  const isFn = list.map(w => inp.isFunction(w));
  const lonely = new Map<number, number>();                  // words that occur once → where
  for (let i = 0; i < words.length; i++) {
    const w = ids[i], pg = pages[i];
    if (total[w] === 1) lonely.set(w, i);
    n[w]++; first[w] = Math.min(first[w], pg); last[w] = Math.max(last[w], pg); pageSets[w].add(pg);
    density[w][Math.min(bins - 1, Math.floor((pg - 1) / Math.max(NP, 1) * bins))]++;
    if (chapters[i] >= 0) chap[w][Math.min(nChapters - 1, chapters[i])]++;
    if (at[w].length <= 80) at[w].push(pg);
    if (i > 0) { const k = ids[i - 1] * V + w; after.set(k, (after.get(k) ?? 0) + 1); const k2 = w * V + ids[i - 1]; before.set(k2, (before.get(k2) ?? 0) + 1); }
    // neighbour counts for words that occur more than once (a word that occurs once has its single window read directly below)
    if (total[w] > 1) for (let d = 1; d <= WIN && i + d < words.length; d++) {
      const o = ids[i + d]; if (o === w || total[o] < 2) continue;
      if (!isFn[o]) { const k = w * V + o; orbit.set(k, (orbit.get(k) ?? 0) + 1 / d); }
      if (!isFn[w]) { const k = o * V + w; orbit.set(k, (orbit.get(k) ?? 0) + 1 / d); }
    }
    const nm = inp.nodeAt(i);
    if (nm) {
      let nid = nodeId.get(nm); if (nid === undefined) { nid = nodeNames.length; nodeId.set(nm, nid); nodeNames.push(nm); }
      for (let d = -8; d <= 8; d++) { const j = i + d; if (j < 0 || j >= words.length || d === 0 || inp.nodeAt(j) === nm) continue; const k = ids[j] * STRIDE + nid; near.set(k, (near.get(k) ?? 0) + 1); }
    }
  }
  // gather the top neighbours of every word
  const perBefore = new Map<number, Map<number, number>>(), perAfter = new Map<number, Map<number, number>>(), perOrbit = new Map<number, Map<number, number>>();
  const bucket = (src: Map<number, number>, dst: Map<number, Map<number, number>>) => { for (const [k, c] of src) { const a = Math.floor(k / V), b = k % V; (dst.get(a) ?? dst.set(a, new Map()).get(a)!).set(b, c); } };
  bucket(before, perBefore); bucket(after, perAfter);
  for (const [k, c] of orbit) { const a = Math.floor(k / V), b = k % V; (perOrbit.get(a) ?? perOrbit.set(a, new Map()).get(a)!).set(b, c); }
  const nearBy = new Map<number, Map<number, number>>();
  for (const [k, c] of near) { const w = Math.floor(k / STRIDE), nid = k % STRIDE; (nearBy.get(w) ?? nearBy.set(w, new Map()).get(w)!).set(nid, c); }

  const out: Record<string, WordEntry> = {};
  for (let w = 0; w < V; w++) {
    const word = list[w], fn = inp.isFunction(word);
    const ob = perOrbit.get(w);
    let orb: string[];
    if (total[w] === 1) {                                         // the single window of a word that occurs once
      const i = lonely.get(w)!, seen = new Map<number, number>();
      for (let d = -WIN; d <= WIN; d++) { const j = i + d; if (d === 0 || j < 0 || j >= words.length || isFn[ids[j]]) continue; seen.set(ids[j], (seen.get(ids[j]) ?? 0) + 1 / Math.abs(d)); }
      orb = [...seen].map(([o, c]) => [o, c * Math.max(0.2, inp.rarity(list[o]))] as const).sort((a, b) => b[1] - a[1]).slice(0, 8).map(x => list[x[0]]);
    } else orb = ob ? [...ob].map(([o, c]) => [o, c * Math.max(0.2, inp.rarity(list[o]))] as const).sort((a, b) => b[1] - a[1]).slice(0, 8).map(x => list[x[0]]) : [];
    const nr = nearBy.get(w);
    const entry: WordEntry = {
      n: n[w], function: fn, class: fn ? 'function' : inp.classOf(word), pages: pageSets[w].size, first: first[w], last: last[w],
      density: [...density[w]], chapters: [...chap[w]],
      before: TOP(perBefore.get(w) ?? new Map(), 5).map(([o, c]) => [list[o], c] as [string, number]),
      after:  TOP(perAfter.get(w) ?? new Map(), 5).map(([o, c]) => [list[o], c] as [string, number]),
      orbit: orb, near: nr ? TOP(nr, 3).map(([nid]) => nodeNames[nid]) : [],
    };
    if (n[w] <= 80) entry.at = at[w];
    out[word] = entry;
  }
  return out;
}
