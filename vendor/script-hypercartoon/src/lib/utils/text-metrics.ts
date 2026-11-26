/**
 * text-metrics.ts — readability, key phrases and topics, computed here.
 *
 * These are the ideas behind textstat, pytextrank/sumy and gensim's topic
 * modelling, reimplemented for this codebase rather than imported. The
 * algorithms are small and language-portable; the libraries are Python and
 * would each cost a second backend to reach.
 *
 * Everything is deterministic: no model call, no cost, milliseconds. That
 * matters because it can run in the FREE preview, and because a measured figure
 * beats a model's impression of the same figure — asking an LLM "how complex is
 * this prose" gets a plausible answer; counting syllables gets the right one.
 */

// ── Readability (the textstat idea) ───────────────────────────────────────────

/**
 * Syllables in a word, by vowel groups.
 *
 * Exact syllabification differs per language and needs a dictionary. Vowel-group
 * counting is within a few percent for Romance languages and English alike,
 * which is well inside the noise of a readability score — and unlike a
 * dictionary it never fails on an invented fantasy name.
 */
export function countSyllables(word: string): number {
  const w = word.toLowerCase().replace(/[^a-záéíóúüñàèìòùâêîôûäëïöüãõç]/g, '');
  if (!w) return 0;
  const groups = w.match(/[aeiouáéíóúüàèìòùâêîôûäëïöãõ]+/g) ?? [];
  // Two STRONG vowels side by side are a hiatus, not a diphthong: "extra-or-"
  // is two syllables, while "-rio" is one. Counting vowel groups alone
  // undercounted every word with a strong-vowel pair.
  const STRONG = /[aeoáéóàèòâêôäëöãõ]/;
  let n = groups.reduce((total, g) => {
    let extra = 0;
    for (let i = 1; i < g.length; i++) {
      if (STRONG.test(g[i - 1]) && STRONG.test(g[i])) extra++;
    }
    return total + 1 + extra;
  }, 0) || 1;
  // English silent terminal 'e' ("more" is one syllable, not two).
  if (/[^aeiou]e$/.test(w) && n > 1) n--;
  return Math.max(1, n);
}

export interface Readability {
  /** 0-100. Higher is easier. Flesch reading ease, adapted per language. */
  ease: number;
  /** Approximate years of schooling needed. */
  grade: number;
  /** Plain-language verdict. */
  level: string;
  avgSentenceWords: number;
  avgWordSyllables: number;
  /** Share of words of three or more syllables, 0-100. */
  complexWordPercent: number;
}

/**
 * Readability, with the Fernández Huerta variant for Spanish.
 *
 * Flesch's English constants score Spanish as far harder than it reads, because
 * Spanish words simply carry more syllables. Using the English formula on a
 * Spanish novel would tell the author their prose is impenetrable when it is
 * ordinary.
 */
export function readability(text: string, lang = 'en'): Readability {
  const sentences = text.split(/[.!?…]+/).map(s => s.trim()).filter(s => s.length > 1);
  const words = text.match(/[\p{L}\p{N}']+/gu) ?? [];
  if (!sentences.length || !words.length) {
    return { ease: 0, grade: 0, level: 'unknown', avgSentenceWords: 0, avgWordSyllables: 0, complexWordPercent: 0 };
  }

  const syllables = words.reduce((n, w) => n + countSyllables(w), 0);
  const asw = words.length / sentences.length;      // words per sentence
  const aws = syllables / words.length;             // syllables per word
  const complex = words.filter(w => countSyllables(w) >= 3).length;

  const isEs = lang.slice(0, 2).toLowerCase() === 'es';
  const ease = isEs
    ? 206.84 - 60 * aws - 1.02 * asw                // Fernández Huerta
    : 206.835 - 1.015 * asw - 84.6 * aws;          // Flesch

  const grade = 0.39 * asw + 11.8 * aws - 15.59;   // Flesch-Kincaid

  const clamped = Math.max(0, Math.min(100, ease));
  const level =
    clamped >= 80 ? 'very easy'
    : clamped >= 65 ? 'easy'
    : clamped >= 50 ? 'moderate'
    : clamped >= 35 ? 'demanding'
    : 'very demanding';

  return {
    ease: Math.round(clamped),
    grade: Math.round(Math.max(0, grade) * 10) / 10,
    level,
    avgSentenceWords: Math.round(asw * 10) / 10,
    avgWordSyllables: Math.round(aws * 100) / 100,
    complexWordPercent: Math.round((complex / words.length) * 100),
  };
}

// ── Stopwords ─────────────────────────────────────────────────────────────────

const STOPWORDS: Record<string, Set<string>> = {
  es: new Set('el la los las un una unos unas de del al a ante bajo con contra desde durante en entre hacia hasta para por según sin sobre tras y o u pero sino que como cuando donde quien cual si no ni se le lo les me te nos os su sus mi mis tu tus este esta estos estas ese esa esos esas aquel aquella es son era eran ser estar haber ha han había habían fue fueron muy más menos ya también solo sólo todo todos toda todas otro otra cada mismo así aunque porque pues entonces después antes ahora aquí allí bien tan'.split(/\s+/)),
  en: new Set('the a an of to in on at by for from with without and or but so that which who whom whose this that these those is are was were be been being have has had do does did not no nor as if then than there here it its he she they we you i his her their our your my me him them us at up out over under again further once all any both each few more most other some such only own same too very can will just should now'.split(/\s+/)),
};

function stopwordsFor(lang: string): Set<string> {
  return STOPWORDS[lang.slice(0, 2).toLowerCase()] ?? STOPWORDS.en;
}

const tokenize = (s: string) => (s.toLowerCase().match(/[\p{L}\p{N}']{2,}/gu) ?? []);

// ── Key phrases (the pytextrank idea) ─────────────────────────────────────────

export interface KeyPhrase {
  phrase: string;
  score: number;
  count: number;
}

/**
 * Key phrases by co-occurrence ranking.
 *
 * TextRank in essence: words that keep appearing near other important words are
 * important. Implemented as a co-occurrence graph over a sliding window with a
 * few rounds of score propagation, then adjacent high-scoring words are joined
 * into phrases — "duquesa de Alba" beats "duquesa" and "Alba" separately.
 */
export function keyPhrases(text: string, lang = 'en', limit = 12): KeyPhrase[] {
  const stop = stopwordsFor(lang);
  const words = tokenize(text);
  if (words.length < 20) return [];

  // Co-occurrence graph over a 4-word window.
  const graph = new Map<string, Map<string, number>>();
  const freq = new Map<string, number>();
  const WINDOW = 4;

  for (let i = 0; i < words.length; i++) {
    const w = words[i];
    if (stop.has(w) || w.length < 3) continue;
    freq.set(w, (freq.get(w) ?? 0) + 1);
    if (!graph.has(w)) graph.set(w, new Map());
    for (let j = i + 1; j < Math.min(i + WINDOW, words.length); j++) {
      const v = words[j];
      if (stop.has(v) || v.length < 3 || v === w) continue;
      graph.get(w)!.set(v, (graph.get(w)!.get(v) ?? 0) + 1);
      if (!graph.has(v)) graph.set(v, new Map());
      graph.get(v)!.set(w, (graph.get(v)!.get(w) ?? 0) + 1);
    }
  }

  // Score propagation, PageRank-style. Three rounds is enough to settle the
  // ordering; more only refines decimals nobody reads.
  let score = new Map([...graph.keys()].map(k => [k, 1]));
  const DAMPING = 0.85;
  for (let round = 0; round < 3; round++) {
    const next = new Map<string, number>();
    for (const [node, edges] of graph) {
      let sum = 0;
      for (const [nb, weight] of edges) {
        const outWeight = [...(graph.get(nb)?.values() ?? [])].reduce((a, b) => a + b, 0) || 1;
        sum += ((score.get(nb) ?? 1) * weight) / outWeight;
      }
      next.set(node, 1 - DAMPING + DAMPING * sum);
    }
    score = next;
  }

  // Join adjacent strong words into phrases.
  const strong = new Set([...score.entries()].sort((a, b) => b[1] - a[1]).slice(0, 60).map(([w]) => w));
  const phraseCount = new Map<string, number>();
  let run: string[] = [];
  const flush = () => {
    if (run.length) {
      const p = run.join(' ');
      phraseCount.set(p, (phraseCount.get(p) ?? 0) + 1);
      run = [];
    }
  };
  for (const w of words) {
    if (strong.has(w)) run.push(w);
    else { flush(); }
    if (run.length >= 3) flush();
  }
  flush();

  return [...phraseCount.entries()]
    .map(([phrase, count]) => ({
      phrase,
      count,
      score: phrase.split(' ').reduce((n, w) => n + (score.get(w) ?? 0), 0) * Math.log(1 + count),
    }))
    .filter(p => p.count > 1 || p.phrase.includes(' '))
    .sort((a, b) => b.score - a.score)
    .slice(0, limit)
    .map(p => ({ ...p, score: Math.round(p.score * 100) / 100 }));
}

// ── Topics (the gensim idea) ──────────────────────────────────────────────────

export interface Topic {
  terms: string[];
  weight: number;
}

/**
 * Rough topics by term co-occurrence clustering.
 *
 * Not LDA — LDA needs iterations and tuning that would be dishonest to claim
 * at this cost. This groups the strongest terms with the terms they most often
 * appear beside, which surfaces what a document keeps returning to. Presented
 * as "recurring term clusters", not as a topic model, because that is what it
 * is.
 */
export function topicClusters(text: string, lang = 'en', count = 5): Topic[] {
  const phrases = keyPhrases(text, lang, 40);
  if (phrases.length === 0) return [];

  const stop = stopwordsFor(lang);
  const words = tokenize(text).filter(w => !stop.has(w) && w.length > 3);
  const positions = new Map<string, number[]>();
  words.forEach((w, i) => {
    if (!positions.has(w)) positions.set(w, []);
    positions.get(w)!.push(i);
  });

  const seeds = phrases.slice(0, count * 3).map(p => p.phrase.split(' ')[0]);
  const used = new Set<string>();
  const topics: Topic[] = [];

  for (const seed of seeds) {
    if (used.has(seed) || topics.length >= count) continue;
    const seedPos = positions.get(seed) ?? [];
    if (seedPos.length < 2) continue;

    // Terms appearing within 30 words of the seed, ranked by how often.
    const near = new Map<string, number>();
    for (const p of seedPos) {
      for (let j = Math.max(0, p - 30); j < Math.min(words.length, p + 30); j++) {
        const w = words[j];
        if (w === seed || used.has(w)) continue;
        near.set(w, (near.get(w) ?? 0) + 1);
      }
    }
    const terms = [seed, ...[...near.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5).map(([w]) => w)];
    terms.forEach(t => used.add(t));
    topics.push({ terms, weight: Math.round((seedPos.length / words.length) * 10000) / 100 });
  }

  return topics.sort((a, b) => b.weight - a.weight);
}

// ── Extractive summary (the sumy idea) ────────────────────────────────────────

/**
 * The sentences that carry the most of the document's own vocabulary.
 *
 * Extractive, so every sentence is the author's, verbatim. Useful as a cheap
 * spine for a prompt: it gives a lens the document's own strongest sentences
 * without paying to have them written.
 */
export function extractiveSummary(text: string, lang = 'en', sentenceCount = 5): string[] {
  const stop = stopwordsFor(lang);
  const sentences = text.split(/(?<=[.!?…])\s+/).map(s => s.trim()).filter(s => s.split(/\s+/).length >= 6);
  if (sentences.length <= sentenceCount) return sentences;

  const freq = new Map<string, number>();
  for (const w of tokenize(text)) {
    if (stop.has(w) || w.length < 3) continue;
    freq.set(w, (freq.get(w) ?? 0) + 1);
  }
  const max = Math.max(1, ...freq.values());

  const scored = sentences.map((s, i) => {
    const ws = tokenize(s).filter(w => !stop.has(w) && w.length >= 3);
    if (!ws.length) return { i, s, score: 0 };
    // Normalised by length so a long sentence does not win on volume alone.
    const score = ws.reduce((n, w) => n + (freq.get(w) ?? 0) / max, 0) / Math.sqrt(ws.length);
    return { i, s, score };
  });

  return scored
    .sort((a, b) => b.score - a.score)
    .slice(0, sentenceCount)
    .sort((a, b) => a.i - b.i)          // restore reading order
    .map(x => x.s);
}
