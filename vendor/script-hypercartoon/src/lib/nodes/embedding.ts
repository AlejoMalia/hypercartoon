/**
 * embedding.ts — the vocabulary laid out in space (a mathematical EMBEDDING) and its equivalence classes.
 *
 * EMBEDDING (encaje). Every word is mapped, injectively and keeping its relations, to a vector: the words that
 * share a solar system (the words that stand around it again and again) land close together. It is built the
 * classical, cheap way — no model, no network, deterministic:
 *   1. count how often each pair of words stands within a few words of one another, inside a sentence;
 *   2. keep the pairs that meet MORE than chance would (positive pointwise mutual information);
 *   3. squeeze each word's row into a few dozen dimensions with a seeded random projection, which preserves
 *      distances (Johnson–Lindenstrauss) — so similarity of vectors ≈ similarity of solar systems.
 * Close vectors mean "same neighbourhood": that is what lets a word be read through its solar system instead of alone.
 *
 * EQUIVALENCE CLASSES (clase de equivalencia). "Names the same thing" is reflexive, symmetric and transitive; the
 * classes are therefore the connected components of the relation, found with union–find. If rey ~ monarca and
 * monarca ~ John, then rey, monarca and John are one class, whatever order the pairs were met in.
 */

export interface Embedding {
  dim:       number;
  vec:       Map<string, Float32Array>;
  sim:       (a: string, b: string) => number;
  neighbors: (w: string, k?: number) => { word: string; sim: number }[];
  /** cosine between a word and an arbitrary vector (e.g. the centroid of a set of seed words) */
  simToVec:  (w: string, v: Float32Array) => number;
  centroid:  (words: string[]) => Float32Array | null;
}

export interface EmbeddingOptions { dim?: number; window?: number; minCount?: number; maxVocab?: number }

/** small deterministic generator so the same text always gives the same space */
function rng(seed: number) { let x = (seed ^ 0x9e3779b9) >>> 0 || 1; return () => { x ^= x << 13; x >>>= 0; x ^= x >>> 17; x ^= x << 5; x >>>= 0; return x / 4294967296; }; }

export function buildEmbedding(sentences: string[][], opts: EmbeddingOptions = {}): Embedding {
  const dim = opts.dim ?? 128, win = opts.window ?? 12, minCount = opts.minCount ?? 2, maxVocab = opts.maxVocab ?? 5000;
  const freq = new Map<string, number>();
  for (const s of sentences) for (const w of s) freq.set(w, (freq.get(w) ?? 0) + 1);
  const vocab = [...freq].filter(([, c]) => c >= minCount).sort((a, b) => b[1] - a[1]).slice(0, maxVocab).map(x => x[0]);
  const id = new Map(vocab.map((w, i) => [w, i]));
  const V = vocab.length;
  const vec = new Map<string, Float32Array>();
  if (V < 4) return { dim, vec, sim: () => 0, neighbors: () => [], simToVec: () => 0, centroid: () => null };

  // 1. co-occurrence inside the sentence, nearer words counting more
  const co = new Map<number, number>(); const row = new Float64Array(V); let total = 0;
  for (const s of sentences) {
    const ids = s.map(w => id.get(w) ?? -1);
    for (let i = 0; i < ids.length; i++) {
      if (ids[i] < 0) continue;
      for (let j = Math.max(0, i - win); j <= Math.min(ids.length - 1, i + win); j++) {
        if (j === i || ids[j] < 0) continue;
        const wgt = 1 / Math.abs(i - j);
        const k = ids[i] * V + ids[j];
        co.set(k, (co.get(k) ?? 0) + wgt); row[ids[i]] += wgt; total += wgt;
      }
    }
  }
  // 2. positive PMI, with the context counts smoothed so rare words do not dominate
  const alpha = 0.75; let ctxTotal = 0; const ctx = new Float64Array(V);
  for (let i = 0; i < V; i++) { ctx[i] = Math.pow(row[i], alpha); ctxTotal += ctx[i]; }
  // 3. seeded random projection of each context word
  const R: Float32Array[] = vocab.map((w, i) => { const g = rng(i * 2654435761 + w.length); const v = new Float32Array(dim); for (let d = 0; d < dim; d++) v[d] = g() < 0.5 ? -1 : 1; return v; });
  const acc: Float32Array[] = vocab.map(() => new Float32Array(dim));
  for (const [k, c] of co) {
    const a = Math.floor(k / V), b = k % V;
    const pmi = Math.log((c / total) / ((row[a] / total) * (ctx[b] / ctxTotal)));
    if (pmi <= 0) continue;
    const t = acc[a], r = R[b]; for (let d = 0; d < dim; d++) t[d] += pmi * r[d];
  }
  for (let i = 0; i < V; i++) {
    const t = acc[i]; let n = 0; for (let d = 0; d < dim; d++) n += t[d] * t[d];
    n = Math.sqrt(n); if (n > 0) for (let d = 0; d < dim; d++) t[d] /= n;
    vec.set(vocab[i], t);
  }
  const dot = (a: Float32Array, b: Float32Array) => { let s = 0; for (let d = 0; d < dim; d++) s += a[d] * b[d]; return s; };
  return {
    dim, vec,
    sim: (a, b) => { const x = vec.get(a), y = vec.get(b); return x && y ? dot(x, y) : 0; },
    simToVec: (w, v) => { const x = vec.get(w); return x ? dot(x, v) : 0; },
    neighbors: (w, k = 8) => {
      const x = vec.get(w); if (!x) return [];
      const out: { word: string; sim: number }[] = [];
      for (const [o, y] of vec) if (o !== w) out.push({ word: o, sim: dot(x, y) });
      return out.sort((p, q) => q.sim - p.sim).slice(0, k);
    },
    centroid: words => {
      const c = new Float32Array(dim); let n = 0;
      for (const w of words) { const x = vec.get(w); if (!x) continue; for (let d = 0; d < dim; d++) c[d] += x[d]; n++; }
      if (!n) return null; let m = 0; for (let d = 0; d < dim; d++) m += c[d] * c[d]; m = Math.sqrt(m) || 1; for (let d = 0; d < dim; d++) c[d] /= m; return c;
    },
  };
}

/** Equivalence classes of a relation: connected components via union–find (reflexive, symmetric, transitive by construction). */
export function equivalenceClasses<T>(items: T[], related: (a: T, b: T) => boolean): T[][] {
  const parent = items.map((_, i) => i);
  const find = (x: number): number => { while (parent[x] !== x) { parent[x] = parent[parent[x]]; x = parent[x]; } return x; };
  for (let i = 0; i < items.length; i++) for (let j = i + 1; j < items.length; j++) if (related(items[i], items[j])) parent[find(i)] = find(j);
  const groups = new Map<number, T[]>();
  items.forEach((it, i) => { const r = find(i); (groups.get(r) ?? groups.set(r, []).get(r)!).push(it); });
  return [...groups.values()];
}

export interface Field {
  id:      number;
  /** the words that sit nearest the centre of the field: the field's own name */
  label:   string[];
  members: string[];
}

/**
 * SEMANTIC FIELDS. The embedding is cut into regions (spherical k-means, seeded, deterministic): each region gathers
 * the words that live in the same solar systems — petals, kisses, garden, gaze in one; knife, blood, run, death in
 * another. A field is named by its own central words. No list of topics is involved, so it works in any language.
 */
export function clusterVocabulary(emb: Embedding, k: number, iterations = 10): { fields: Field[]; fieldOf: Map<string, number> } {
  const words = [...emb.vec.keys()]; const fullDim = emb.dim;
  const fieldOf = new Map<string, number>();
  if (words.length < k * 3 || k < 2) return { fields: [], fieldOf };
  // The projection spreads information evenly over its dimensions, so the first ones carry the geometry well enough to cut the space.
  const dim = Math.min(fullDim, 96), N = words.length;
  const M = new Float32Array(N * dim);
  words.forEach((w, i) => { const v = emb.vec.get(w)!; let n = 0; for (let d = 0; d < dim; d++) n += v[d] * v[d]; n = Math.sqrt(n) || 1; for (let d = 0; d < dim; d++) M[i * dim + d] = v[d] / n; });
  const dotRC = (i: number, c: Float32Array) => { let s = 0; const o = i * dim; for (let d = 0; d < dim; d++) s += M[o + d] * c[d]; return s; };
  const g = rng(N * 7919 + fullDim);
  const first = Math.floor(g() * N);
  const centres: Float32Array[] = [M.slice(first * dim, first * dim + dim)];
  const bestSim = new Float32Array(N).fill(-2);
  while (centres.length < k) {                                    // k-means++ start: the next centre is drawn far from those already chosen
    const last = centres[centres.length - 1]; let sum = 0;
    for (let i = 0; i < N; i++) { const sm = dotRC(i, last); if (sm > bestSim[i]) bestSim[i] = sm; const d = 1 - bestSim[i]; sum += d * d; }
    let r = g() * sum, pick = 0;
    for (let i = 0; i < N; i++) { const d = 1 - bestSim[i]; r -= d * d; if (r <= 0) { pick = i; break; } }
    centres.push(M.slice(pick * dim, pick * dim + dim));
  }
  const assign = new Int32Array(N).fill(-1);
  for (let it = 0; it < iterations; it++) {
    let moved = 0;
    for (let i = 0; i < N; i++) { let b = 0, bs = -2; for (let c = 0; c < k; c++) { const sm = dotRC(i, centres[c]); if (sm > bs) { bs = sm; b = c; } } if (assign[i] !== b) { assign[i] = b; moved++; } }
    const acc = centres.map(() => new Float32Array(dim)), cnt = new Array<number>(k).fill(0);
    for (let i = 0; i < N; i++) { const a = acc[assign[i]], o = i * dim; for (let d = 0; d < dim; d++) a[d] += M[o + d]; cnt[assign[i]]++; }
    acc.forEach((a, ci) => { if (!cnt[ci]) return; let n = 0; for (let d = 0; d < dim; d++) n += a[d] * a[d]; n = Math.sqrt(n) || 1; for (let d = 0; d < dim; d++) centres[ci][d] = a[d] / n; });
    if (!moved) break;
  }
  const fields: Field[] = centres.map((c, id) => {
    const idx: number[] = []; for (let i = 0; i < N; i++) if (assign[i] === id) idx.push(i);
    const label = [...idx].sort((a, b) => dotRC(b, c) - dotRC(a, c)).slice(0, 5).map(i => words[i]);
    return { id, label, members: idx.map(i => words[i]) };
  }).filter(f => f.members.length >= 3);
  const remap = new Map(fields.map((f, i) => [f.id, i])); fields.forEach((f, i) => { f.id = i; });
  words.forEach((w, i) => { const ni = remap.get(assign[i]); if (ni !== undefined) fieldOf.set(w, ni); });
  return { fields, fieldOf };
}
