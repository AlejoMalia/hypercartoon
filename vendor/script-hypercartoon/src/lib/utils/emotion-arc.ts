/**
 * emotion-arc.ts — the emotional shape of a text, measured rather than asked.
 *
 * The idea behind textblob and the emotion classifiers in transformers,
 * reimplemented as a lexicon: words carry valence and arousal, a passage
 * inherits the balance of the words in it, and a work is the curve those
 * passages trace.
 *
 * WHY A LEXICON AND NOT A MODEL CALL
 * The audiobook already asks a model to rate each chapter's tension, and the
 * storyboard asks the same of each scene. Those calls are fine, but they are
 * unverifiable: a model asked the same question twice can answer differently,
 * and nothing catches it. A lexicon is crude by comparison and it is also
 * REPEATABLE, free, and instant — which makes it useful as a second opinion
 * that can contradict the model, and as a curve the free preview can show.
 *
 * WHAT IT IS NOT
 * It does not understand irony, negation across clauses, or a calm sentence
 * describing something terrible. It counts charged words. Where it disagrees
 * with a model's reading, the model is usually right — so this is reported
 * alongside, never instead.
 */

export interface EmotionPoint {
  /** 0-1 position through the text. */
  position: number;
  label: string;
  /** -100..100. Negative is dark, positive is bright. */
  valence: number;
  /** 0-100. How charged, regardless of direction. */
  arousal: number;
  words: number;
}

export interface EmotionArc {
  points: EmotionPoint[];
  /** Mean valence across the work. */
  overallValence: number;
  /** The darkest and brightest sections. */
  lowest: EmotionPoint | null;
  highest: EmotionPoint | null;
  /** The section with the most charge — usually the climax. */
  peak: EmotionPoint | null;
  /** Plain-language reading of the curve's shape. */
  shape: string;
}

/**
 * Valence lexicon: negative words score down, positive up.
 *
 * Stems rather than full forms, matched as prefixes, so "matar/mató/matando"
 * all hit one entry. Spanish and English together because a manuscript is one
 * or the other and mixing costs nothing.
 */
const NEGATIVE = [
  // es
  'muert', 'matar', 'mató', 'matan', 'asesin', 'sangre', 'sangri', 'dolor', 'duele', 'herid', 'herir',
  'miedo', 'temor', 'terror', 'pánico', 'horror', 'espant', 'aterr', 'angusti', 'ansied',
  'llor', 'lágrim', 'triste', 'tristez', 'pena', 'sufr', 'agoní', 'desesper', 'soledad', 'solo',
  'odio', 'odiar', 'rabia', 'furi', 'ira', 'grit', 'chill', 'amenaz', 'peligr', 'oscur', 'tinieb',
  'frío', 'helad', 'vacío', 'perdid', 'romp', 'destru', 'ruina', 'derrot', 'fracas', 'culpa',
  'traicion', 'mentir', 'engañ', 'cruel', 'brutal', 'violen', 'guerra', 'batalla', 'enemig',
  'enferm', 'veneno', 'muri', 'cadáver', 'tumba', 'infiern', 'maldi', 'castig', 'prisión', 'encerr',
  // en
  'death', 'died', 'kill', 'murder', 'blood', 'pain', 'hurt', 'wound', 'fear', 'terror', 'horror',
  'panic', 'dread', 'anguish', 'cry', 'tear', 'sad', 'grief', 'suffer', 'despair', 'lonely',
  'hate', 'rage', 'fury', 'anger', 'scream', 'shout', 'threat', 'danger', 'dark', 'cold', 'empty',
  'lost', 'break', 'destroy', 'ruin', 'defeat', 'fail', 'guilt', 'betray', 'lie', 'deceive',
  'cruel', 'brutal', 'violen', 'war', 'battle', 'enemy', 'sick', 'poison', 'corpse', 'grave', 'hell',
];

const POSITIVE = [
  // es
  'amor', 'amar', 'ama', 'quer', 'beso', 'abraz', 'caric', 'ternur', 'dulce', 'feliz', 'felicid',
  'alegr', 'ríe', 'reír', 'risa', 'sonri', 'sonrisa', 'luz', 'brilla', 'ilumin', 'calor', 'cálid',
  'paz', 'calma', 'tranquil', 'seren', 'esperanz', 'sueñ', 'libert', 'libre', 'salv', 'protej',
  'belle', 'hermos', 'bell', 'precios', 'perfect', 'triunf', 'vict', 'logr', 'gana', 'éxito',
  'amig', 'familia', 'hogar', 'casa', 'refugi', 'nace', 'nacer', 'vida', 'vivir', 'flor', 'jardín',
  // en
  'love', 'kiss', 'embrace', 'tender', 'sweet', 'happy', 'joy', 'laugh', 'smile', 'light', 'shine',
  'warm', 'peace', 'calm', 'serene', 'hope', 'dream', 'free', 'save', 'protect', 'beauty',
  'beautiful', 'perfect', 'triumph', 'victory', 'achieve', 'win', 'success', 'friend', 'family',
  'home', 'shelter', 'born', 'life', 'live', 'flower', 'garden', 'gentle', 'safe',
];

/**
 * Arousal lexicon: words that carry charge in EITHER direction.
 *
 * Separate from valence because a scene can be intensely joyful or intensely
 * dreadful, and "how much is happening" is a different question from "is it
 * good or bad" — the audiobook needs the first to drive delivery.
 */
const HIGH_AROUSAL = [
  'corr', 'salt', 'golpe', 'grit', 'estall', 'explo', 'romp', 'lucha', 'pelea', 'persig', 'huy',
  'atac', 'defiend', 'dispar', 'clav', 'arranc', 'arroj', 'precipit', 'urgen', 'súbit', 'repent',
  'de pronto', 'de golpe', 'jamás', 'nunca', 'siempre', 'todo', 'nada',
  'run', 'jump', 'strike', 'scream', 'burst', 'explo', 'break', 'fight', 'chase', 'flee',
  'attack', 'defend', 'shoot', 'sudden', 'urgent', 'never', 'always',
];

function buildMatcher(stems: string[]): RegExp {
  // Escaped and joined into one pass: matching 150 stems separately over a
  // whole novel is measurably slower than one alternation.
  const escaped = stems.map(s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  return new RegExp(`\\b(?:${escaped.join('|')})`, 'gi');
}

const NEG_RE = buildMatcher(NEGATIVE);
const POS_RE = buildMatcher(POSITIVE);
const AROUSE_RE = buildMatcher(HIGH_AROUSAL);

/** The lexicon's reading of ONE word: valence −1 dark / +1 bright / 0 uncharged, and whether it carries arousal. Seeds for the node engine. */
export function wordCharge(word: string): { valence: number; arousal: number } {
  const neg = (word.match(NEG_RE) ?? []).length, pos = (word.match(POS_RE) ?? []).length;
  return { valence: pos > neg ? 1 : neg > pos ? -1 : 0, arousal: (word.match(AROUSE_RE) ?? []).length > 0 ? 1 : 0 };
}

export interface SectionScore {
  valence: number;
  arousal: number;
  words: number;
}

/** Score one passage. Exposed so a caller can weigh a single chapter. */
export function scoreSection(text: string): SectionScore {
  const words = (text.match(/\S+/g) ?? []).length;
  if (words < 20) return { valence: 0, arousal: 0, words };

  const neg = (text.match(NEG_RE) ?? []).length;
  const pos = (text.match(POS_RE) ?? []).length;
  const arouse = (text.match(AROUSE_RE) ?? []).length;

  // Per thousand words, so a long chapter is not automatically more emotional.
  const per1k = (n: number) => (n / words) * 1000;
  const negRate = per1k(neg), posRate = per1k(pos);
  const total = negRate + posRate;

  // Valence is the BALANCE, not the volume: a chapter thick with both is
  // turbulent, not neutral, and its arousal reflects that instead.
  const valence = total > 0 ? Math.round(((posRate - negRate) / total) * 100) : 0;

  // Charge saturates: past ~40 charged words per thousand, more does not read
  // as more intense, it reads as purple.
  const arousal = Math.round(Math.min(100, ((total + per1k(arouse)) / 40) * 100));

  return { valence, arousal, words };
}

/**
 * The emotional curve of a work, section by section.
 *
 * Sections are supplied by the caller — chapters for a novel, scenes for a
 * script — because the caller already knows the real structure and re-deriving
 * it here would produce a second, worse answer.
 */
export function emotionArc(sections: { label: string; text: string }[]): EmotionArc {
  const scored = sections.map((s, i) => {
    const sc = scoreSection(s.text);
    return {
      position: sections.length > 1 ? i / (sections.length - 1) : 0,
      label: s.label,
      valence: sc.valence,
      arousal: sc.arousal,
      words: sc.words,
    };
  }).filter(p => p.words >= 20);

  if (scored.length === 0) {
    return { points: [], overallValence: 0, lowest: null, highest: null, peak: null, shape: 'unknown' };
  }

  const overall = Math.round(scored.reduce((n, p) => n + p.valence, 0) / scored.length);
  const lowest  = scored.reduce((a, b) => (b.valence < a.valence ? b : a));
  const highest = scored.reduce((a, b) => (b.valence > a.valence ? b : a));
  const peak    = scored.reduce((a, b) => (b.arousal > a.arousal ? b : a));

  return { points: scored, overallValence: overall, lowest, highest, peak, shape: describeShape(scored) };
}

/**
 * Name the curve, in the terms a writer uses.
 *
 * Deliberately coarse. The classic six shapes are a literary claim, not a
 * measurement, and asserting "this is Icarus" from a word count would be
 * dressing a rough number as an insight.
 */
function describeShape(points: EmotionPoint[]): string {
  if (points.length < 3) return 'too short to trace';
  const third = Math.max(1, Math.floor(points.length / 3));
  const mean = (arr: EmotionPoint[]) => arr.reduce((n, p) => n + p.valence, 0) / arr.length;

  const start = mean(points.slice(0, third));
  const middle = mean(points.slice(third, points.length - third));
  const end = mean(points.slice(-third));

  const rising = end - start > 15;
  const falling = start - end > 15;
  const dipped = middle < start - 15 && middle < end - 15;
  const arched = middle > start + 15 && middle > end + 15;

  if (dipped)  return 'falls into a dark middle and recovers';
  if (arched)  return 'rises through the middle and darkens at the end';
  if (rising)  return 'darkest at the start, brightening towards the end';
  if (falling) return 'brightest at the start, darkening towards the end';
  return 'holds an even emotional register throughout';
}

/** A compact sparkline of the curve, for a prompt or a PDF caption. */
export function arcSparkline(arc: EmotionArc, width = 24): string {
  if (!arc.points.length) return '';
  const bars = '▁▂▃▄▅▆▇█';
  const step = Math.max(1, Math.floor(arc.points.length / width));
  const sampled = arc.points.filter((_, i) => i % step === 0).slice(0, width);
  return sampled.map(p => bars[Math.min(bars.length - 1, Math.floor(((p.valence + 100) / 200) * bars.length))]).join('');
}
