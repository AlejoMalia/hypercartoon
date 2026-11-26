/**
 * engine.ts — the NODE mechanism: reads a whole text in milliseconds, with no model
 * and no network, and projects it as nodes laid out over its pages.
 *
 *   • Every page is a layer of time (page = words / 250 unless the text carries real
 *     page breaks). A node is a recurring chain of letters; where it appears, and how
 *     densely, is its trajectory through the work.
 *   • Nothing is discarded: every word keeps its positions, and carries a weight that
 *     grows with how rare it is at page level. Common words stay catalogued, they just
 *     weigh little.
 *   • A node's "solar system" is the bag of every word around every one of its
 *     appearances. What a node IS (character / place) is decided by comparing that whole
 *     system, never by a single feature. A node is never judged by its name.
 *   • Identity (two names for one entity) is decided only with evidence of its own:
 *     mutual-closest solar systems that share the same pages, or a title glued once to
 *     one name ("rey John" ⇒ every "rey" is John, because there is no second king).
 *     Everything else stays a LINK between nodes with a strength, never a fusion.
 *   • What sits before the first scene (or in a bare list of capitalised words before the
 *     story starts) is paratext; what sits in the last tokens is an end mark.
 */
import { LEXICONS, detectLang, type Lexicon, type NodesLang } from './lexicon';
import { scoreSection, wordCharge } from '@/lib/utils/emotion-arc';
import { buildEmbedding, equivalenceClasses, clusterVocabulary } from './embedding';
import { buildCompletionBrief, type CompletionBrief } from './completion';
import { proposeRestructure, isPartTitle, type Restructure } from './restructure';
import { buildSections, buildReportPlan, type BuiltSection, type ReportPlan } from './dossier-spec';
import { buildWordIndex, type WordEntry } from './word-index';
import { topicClusters } from '@/lib/utils/text-metrics';

// ─── public shapes ──────────────────────────────────────────────────────────────
export type NodeKind = 'character' | 'place' | 'paratext' | 'end-mark';

export interface StoryNode {
  name:     string;
  aliases:  string[];
  kind:     NodeKind;
  /** summed evidence from the node's solar system (per mention) */
  evidence: { character: number; place: number };
  mentions: number;
  pages:    number;
  first:    number;
  last:     number;
  /** a name is written with a capital wherever it stands; 1 = always, near 0 = it is a common word that opens sentences (One, Even, Because) */
  nameConsistency: number;
  /** share of its mentions inside speech, inside an action tag, or in plain narration */
  voice:    { dialogue: number; action: number; narration: number };
  /** shortest page window holding 80% of the mentions */
  core:     [number, number];
  /** mentions per slice of the work (up to 40 slices) */
  density:  number[];
  /** the heaviest words of its solar system */
  orbit:    string[];
}

export interface WordNode {
  word:     string;
  mentions: number;
  pages:    number;
  first:    number;
  last:     number;
  weight:   number;
  /** rarity at three scales: within the page, within the chapter, within the whole work */
  scales:   { page: number; chapter: number; book: number };
  density:  number[];
}

export interface NodeLink {
  a: string;
  b: string;
  strength:    number;
  sharedPages: number;
}

export interface AddressReading {
  page: number;
  form: string;
  /** who says it: the name beside the speech verb ("—Sí, mi señor —dijo Beto"); it cannot be the one it refers to */
  speaker: string | null;
  /** most likely referents, best first, with the words of the scene that support each */
  to:   { node: string; score: number; evidence: string[]; present: boolean }[];
}

export interface StructureReading {
  /** what the work contains that is NOT the story: dedication, epigraph, introduction… before the first chapter; notes, index, acknowledgments… after the last */
  frontSections: { title: string; pages: [number, number] }[];
  backSections:  { title: string; pages: [number, number] }[];
  /** where the chapters come from: a counter (Chapter 1,2,3), isolated titles, equal windows, or none */
  chapterSource: 'numbered' | 'titles' | 'titles-loose' | 'windows' | 'none';
  /** layers read as the body of the work (continuous prose); null when the whole text is body */
  body:       [number, number] | null;
  frontMatter: number[];
  backMatter:  number[];
  /** short isolated lines; `numbered` ones repeat one shape with a counter (Chapter 1, 2, 3…) */
  headings:   { page: number; text: string; numbered: boolean }[];
  /** share of function words per layer (the signal that tells prose from lists and notes) */
  proseShare: number[];
}

export interface SentenceReading {
  total:    number;
  /** how many sentences fall in each exoticity class, 1 = common … 5 = most exotic */
  classes:  number[];
  perPage:  number[];
  top:      { page: number; text: string; words: number; exotic: string[]; score: number; gap: number | null; /** the most exotic word of the sentence read at three scales: in its page, in its chapter, in the whole work */ scales: { page: string; chapter: string; book: string } | null }[];
}

export interface EventSegment {
  pages:  [number, number];
  /** who is on stage (carried over from the last sentence that named anyone) */
  actors: string[];
  /** where (the last place named) */
  place:  string | null;
  /** the words that mark this stretch of the chapter, in the order they happen: its event chain */
  words:  string[];
  charge: number;
}

export interface SymbolField {
  /** the field's own central words */
  label:   string[];
  /** share of the chapter's event words that belong to it */
  share:   number;
  /** −1 dark … +1 bright, read from the charged words that live in the field */
  valence: number;
}

export interface ForestTree {
  /** an important node is a tree of its own */
  root:     string;
  kind:     NodeKind;
  mentions: number;
  first:    number;
  last:     number;
  core:     [number, number];
  /** the words that stand around it (its solar system) */
  orbit:    string[];
  /** primary: carries a large share of the work; secondary: matters for a stretch or grows from a primary */
  rank:     'primary' | 'secondary';
  /** branches that are important trees of their own: the nodes this one generates */
  generates: string[];
  /** what grows around it: nodes that live inside its pages, or are born while it is active */
  branches: { name: string; kind: NodeKind; first: number; inside: number; born: boolean }[];
}

export interface TreeRelation {
  a: string; b: string;
  sharedBranches: string[];
  coreOverlap:    number;
  /** how the two trees sit in time */
  relation:       'a hands over to b' | 'b hands over to a' | 'run together' | 'nested';
}

export interface ChapterReading {
  index:     number;
  title:     string;
  pages:     [number, number];
  words:     number;
  /** the words that identify this chapter against the others (rare at chapter level) */
  signature: string[];
  /** the nodes that carry it */
  nodes:     string[];
  /** its most exotic sentence: the island that sums the chapter up */
  island:    string | null;
  /** what the chapter's words say it is about: charge (valence −100 dark … +100 bright, arousal 0–100) and its recurring term clusters */
  /** 0–100: tension of the chapter, ranked against the work's own chapters */
  tension:   number;
  tone:      { valence: number; arousal: number; /** the same reading taken over the event chain's words through their semantic fields (−1…1) */ eventBalance: number | null; label: 'violent / dark' | 'tense' | 'tender / bright' | 'calm' | 'turbulent' | 'neutral' };
  clusters:  string[][];
  /** the chapter as a chain of events: scenes, each with its actors, its place and the words that happen in it, in order */
  events:    EventSegment[];
  /** the symbolism of the chapter: the semantic fields its event words belong to */
  symbols:   SymbolField[];
  /** what the chapter is made of: share of action / place / object words, and of speech */
  mix:       { action: number; place: number; object: number; element: number; dialogue: number };
  /** the element trees most active in this chapter */
  themes:    string[];
  /** true when the chapter was not seen as a title but deduced from the rhythm of the others */
  inferred:  boolean;
  /** a chapter with its own title; a part of the book (primera parte…); or a stretch the rhythm recovered that carries no title and may not be a chapter at all */
  kind:      'chapter' | 'part' | 'untitled';
  /** what supported the deduction: a looser title island, a change of vocabulary, or both */
  inferredBy: 'island+shift' | 'island' | 'shift' | null;
}

export interface KnotReading {
  windows: { pages: [number, number]; crossings: number; nodes: string[] }[];
  pairs:   { a: string; b: string; crossings: number }[];
  closest: { a: string; b: string; distance: number }[];
}

export interface ThemeTree {
  /** an element (object, material, place, action…) that carries a theme of its own */
  root:       string;
  /** what kind of element it behaves as, read from the frames it appears in */
  class:      'place' | 'object' | 'action' | 'element';
  mentions:   number;
  /** chapters (1-based) where it is present */
  chapters:   number[];
  /** share of the book's chapters that carry it */
  share:      number;
  /** how it flows through the book */
  flow:       'constant motif' | 'burst' | 'fades' | 'builds' | 'mid-book arc' | 'recurring';
  peaks:      number[];
  /** the words closest to it in the embedding: its solar system, whether or not it grows branches */
  orbit:      string[];
  /** the elements that live beside it in the same sentences */
  branches:   { word: string; class: ThemeTree['class']; strength: number; born: boolean }[];
  /** the characters / places that move with it */
  carriers:   string[];
  rank:       'primary' | 'secondary';
  generates:  string[];
}

export interface ThemeRelation {
  a: string; b: string;
  sharedBranches: string[];
  /** correlation of the two trees' flow through the chapters (−1 … 1) */
  coFlow:   number;
  relation: 'flow together' | 'alternate' | 'independent';
}

export interface EquivalenceClass {
  representative: string;
  /** every name the engine decided is the same thing (reflexive, symmetric, transitive) */
  members:        string[];
  /** why they are one: contained in a longer name, closest solar systems on the same pages, or a title glued to a single name */
  reasons:        string[];
}

export interface Injectivity {
  /** distinct entities (character / place identities) after every merge */
  entities:   number;
  /** mentions each assigned to exactly ONE entity */
  mentions:   number;
  /** tokens that two entities claimed at once; resolved to the more specific name */
  collisions: number;
  /** pairs of distinct names whose solar systems and pages are close enough to tempt a merge, kept apart because both are names */
  keptApart:  { a: string; b: string; similarity: number; sharedPages: number }[];
  /** merges refused because they would have joined two distinct names through a common word */
  refused:    string[];
}

export interface RouteLeg { pages: [number, number]; place: string }

export interface Route {
  name:   string;
  kind:   'character' | 'place';
  mentions: number;
  /** where it is, stretch by stretch */
  legs:   RouteLeg[];
}

export interface RoutePair {
  kind:   'node-node' | 'tree-tree' | 'node-tree';
  a:      string;
  b:      string;
  /** slices of the work (of up to 40) where both are present */
  together: number;
  /** stretches where they stand within a scene of each other */
  encounters: [number, number][];
  /** closest approach: the pages, the distance in words between their nearest mentions, and the distance between their solar systems then (0 same … 1 unrelated) */
  closest: { pages: [number, number]; words: number; solar: number } | null;
  trend:  'converging' | 'diverging' | 'steady';
  relation: 'companions' | 'crossing' | 'contained' | 'apart';
  sharedPlaces: string[];
}

export interface Affinity {
  node: string;
  /** the elements that stand around THIS node more than around the others: lift over the whole work, and the share of the word's company that is this node's */
  elements: { word: string; count: number; lift: number; exclusivity: number }[];
  /** the actions that belong more to this node than to the others */
  actions:  { word: string; count: number; lift: number; exclusivity: number }[];
}

export interface Circle {
  node:   string;
  /** A: the elements in its own circle — what stands around it in its own sentences, far more than around anything else */
  inner:  string[];
  /** B \ A: the elements of the scenes where it is on stage that lie outside its circle (they can belong to other nodes too) */
  outer:  string[];
  /** elements of A or B that other nodes also hold, and who */
  shared: { word: string; with: string[] }[];
  /** the elements of A that no other node holds: what is proper to it */
  proper: string[];
}

export interface Arc {
  node:     string;
  mentions: number;
  /** identity function: share of its circle that is the SAME early and late (1 = F(x)=x, nothing changed; 0 = everything around it changed) */
  identity: number;
  kept:     string[];
  lost:     string[];
  gained:   string[];
  /** charge of what surrounds it, early and late (−1 dark … +1 bright) */
  chargeEarly: number;
  chargeLate:  number;
  direction:   'rises' | 'falls' | 'steady';
  verdict:     'identity' | 'partial' | 'transforms';
  /** share of the other nodes that change MORE than this one (1 = it changes least in the whole work). In a work where everything moves, this is what tells who holds. */
  relative:    number;
  /** how much the reading rests on: 1 = ten or more mentions on each side */
  confidence:  number;
  /** what early and late mean for this node: its first and last chapters, or its own pages within one chapter */
  basis:       string;
}

export interface WorldIdentity {
  /** words whose solar system is the same at the start and at the end of the work, though everything else moved */
  invariant: { word: string; mentions: number; stability: number }[];
  /** words whose solar system changed most */
  drift:     { word: string; mentions: number; stability: number }[];
  /** the end set against the beginning: does the story come back to where it started? */
  circularity: { similarity: number; samePlace: boolean; verdict: 'circular' | 'open' };
}

export interface Moment {
  chapter: number;
  title:   string;
  pages:   [number, number];
  actors:  string[];
  place:   string | null;
  /** the words that happen, in order */
  words:   string[];
  charge:  number;
}

export interface Dossier {
  name:     string;
  kind:     'character' | 'place';
  aliases:  string[];
  rank:     'primary' | 'secondary';
  presence: { mentions: number; first: number; last: number; chapters: number[]; share: number; density: number[] };
  voice:    { dialogue: number; action: number; narration: number };
  /** the first and the last sentence in which it appears */
  introduced: { page: number; chapter: number; line: string };
  lastSeen:   { page: number; chapter: number; line: string };
  route:    RouteLeg[];
  /** where it lives: its main place, and its weight in each place it frequents */
  home:     string | null;
  places:   { place: string; home: number; weight: number; role: PlaceCastMember['role'] }[];
  circle:   { inner: string[]; outer: string[]; proper: string[] };
  /** what is proper to it (traits that distinguish it from the others) */
  traits:   { elements: string[]; actions: string[] };
  /** who it relates to, strongest first */
  relations: { with: string; relation: RoutePair['relation']; together: number; encounters: number; closest: [number, number] | null; trend: RoutePair['trend']; sharedPlaces: string[]; tone: { valence: number; tension: number; bond: PairTone['bond']; trend: PairTone['trend']; peak: number | null } | null }[];
  /** its own tone and how it runs through the work */
  tone: NodeTone | null;
  generates: string[];
  /** where it stands in the hierarchy, with the evidence, and what belongs to it */
  standing: { level: number; score: number; evidence: string[] } | null;
  owns:     string[];
  arc:      Arc | null;
  /** the scenes in which it matters most */
  keyMoments: Moment[];
  /** the scene of greatest intensity within its most intense chapter */
  climax:   Moment | null;
  /** chapters whose skeleton of relations repeats the ones it lives in (with the map of the cast) */
  parallels: { chapters: [number, number]; kind: SkeletonParallel['kind']; similarity: number; becomes: string | null }[];
  /** motifs (theme trees) present in at least a third of its chapters */
  themes:   { root: string; flow: ThemeTree['flow']; share: number }[];
  /** the report structure: every section, how complete it is and which engine mechanisms feed it */
  sections: BuiltSection[];
}

export interface PlaceCastMember {
  name:   string;
  /** share of everything said about characters in this place that is this character's */
  weight: number;
  /** share of the character's own presence that happens in this place (1 = it lives here) */
  home:   number;
  role:   'native' | 'regular' | 'visitor';
}

export interface PlaceMeeting {
  a: string; b: string;
  /** sentences in which they stand together here */
  times: number;
  /** of those, the ones spoken (dialogue) */
  dialogue: number;
  /** mean charge of those sentences: negative = tense */
  charge: number;
  kind: 'between natives' | 'host and guest' | 'between guests';
}

export interface PlaceCast {
  place:    string;
  pages:    [number, number];
  mentions: number;
  cast:     PlaceCastMember[];
  /** who meets whom here, and under what tension */
  meetings: PlaceMeeting[];
}

export interface SkeletonParallel {
  a: { chapter: number; title: string };
  b: { chapter: number; title: string };
  /** how well the relations of one chapter survive the best map of its cast onto the other's (1 = the same skeleton) */
  similarity: number;
  /** how much of the cast is the same people/places (0 = entirely different names) */
  castOverlap: number;
  /** the map that preserves the structure: a ↦ b */
  mapping: [string, string][];
  kind: 'hidden parallel' | 'echo';
}

export interface Rank {
  node:     string;
  kind:     'character' | 'place';
  /** 0 = the top of the hierarchy */
  level:    number;
  score:    number;
  /** what the rank rests on */
  evidence: string[];
}

export interface Hierarchy {
  /** forms of address LEARNED from the book: chains of words in dialogue that keep turning towards the same node, whoever speaks ("mi señor" → the king) */
  forms: { form: string; toward: string; times: number; speakers: string[] }[];
  /** who defers to whom (forms of address towards a referent, in the scenes where both stand) */
  deference:   { from: string; to: string; times: number }[];
  characters:  Rank[];
  places:      Rank[];
  /** a place inside another: its presence lies within the other's stretch */
  containment: { outer: string; inner: string; share: number }[];
  /** the element that belongs to one node far more than to any other */
  ownership:   { element: string; owner: string; exclusivity: number; lift: number }[];
}

export interface ThematicConsistency {
  root:         string;
  early:        [number, number];
  late:         [number, number];
  /** share of the relations among the theme's words that survive from the first half of its life to the second (identity map) */
  preservation: number;
  kept:         string[];
  broken:       string[];
  verdict:      'coherent' | 'shifts';
}

export interface Morphisms {
  parallels: SkeletonParallel[];
  hierarchy: Hierarchy;
  thematic:  ThematicConsistency[];
}

/**
 * The 4D map as the author defined it: no projection. Time is the layer (one page = one layer); each layer holds the nodes that are on it, where they stand,
 * what they are with (other nodes in the same solar systems), what surrounds them (the exotic words of those sentences) and which elements of the theme forest
 * they touch. Chaining the layers gives each node's trajectory.
 */
export interface Layer {
  page: number; chapter: number;
  nodes: { name: string; kind: NodeKind; n: number; place: string | null; with: string[]; around: string[]; elements: string[]; tone: { valence: number; tension: number } }[];
}
export interface Interaction { node: string; element: string; class: ThemeTree['class']; sentences: number; pages: number[]; first: number; last: number }
export interface Trajectory {
  node: string; kind: NodeKind; layers: number; first: number; last: number;
  /** uninterrupted stretches of layers where it is present, with the place it carries there */
  runs: { from: number; to: number; place: string | null }[];
  /** how much its company (the nodes and elements it is with) is renewed from one layer where it appears to the next: 0 = the same, 1 = all new */
  elasticity: number;
  /** who it is most with, over all layers */
  mostWith: { name: string; layers: number }[];
}
export interface LayerMap { layers: Layer[]; interactions: Interaction[]; trajectories: Trajectory[] }

/**
 * Tone belongs to the characters and to what happens between them. Every sentence (a solar system) has a charge: the net of its charged words (valence) and how many of them are
 * arousing (arousal), both read through the lexicon extended by the embedding. A character's tone is the tone of its sentences; the tone between two characters is the tone of the
 * sentences where they stand together (or in consecutive sentences, as in an exchange); tension is arousal made darker by what is charged, and the plot's levels are the tension
 * of every page, chapter and pair.
 */
export interface NodeTone {
  node: string; kind: NodeKind; sentences: number;
  /** −100 dark … +100 bright, over the charged words of its sentences */
  valence: number;
  /** 0–100, rank of the arousal of its sentences among all the sentences of the work */
  arousal: number;
  /** 0–100, arousal made darker by dark charge */
  tension: number;
  /** share of its sentences that are spoken */
  spoken: number;
  trend: 'darkens' | 'brightens' | 'steady';
  peak: number | null;
  byChapter: { chapter: number; valence: number; tension: number; sentences: number }[];
}
export interface PairTone {
  a: string; b: string; sentences: number; pages: [number, number];
  valence: number; arousal: number; tension: number; spoken: number;
  /** how the tension runs between them from their first shared sentence to their last */
  trend: 'escalates' | 'eases' | 'steady';
  peak: number | null;
  /** what the tone says about the bond */
  bond: 'hostile' | 'strained' | 'warm' | 'calm';
}
export interface ToneMap {
  nodes: NodeTone[]; pairs: PairTone[];
  /** tension of every page, smoothed */
  curve: { page: number; tension: number }[];
  peaks: number[];
  chapters: { chapter: number; tension: number }[];
}

export interface NodesResult {
  language:   NodesLang;
  words:      number;
  layers:     number;
  pageMode:   'real-pages' | 'words-per-page';
  elapsedMs:  number;
  catalogued: number;
  locations:  { heading: string; place: string; time: string; scene: string }[];
  paratext:   { items: string[]; appearancesInWork: Record<string, number> }[];
  nodes:      StoryNode[];
  wordNodes:  WordNode[];
  places:     { name: string; core: [number, number]; inhabitants: { name: string; scenes: number }[] }[];
  links:      NodeLink[];
  fusions:    string[];
  address:    AddressReading[];
  /** capitalised words that are the book's own scaffolding (CHAPTER, PART…), kept out of the nodes */
  structuralWords: string[];
  /** capitalised words that behave as common words (a lower-case twin as frequent as the capital one): not names */
  notNames: string[];
  /** every mention belongs to exactly one entity, and no two distinct names ever merge, however close they stand */
  injectivity: Injectivity;
  /** where each important node is, stretch by stretch */
  routes: Route[];
  /** how routes relate: node–node, tree–tree, node–tree */
  routePairs: RoutePair[];
  /** who has weight in each place, who is native and who a guest, and the tension of the meetings that follow */
  placeCasts: PlaceCast[];
  /** which elements are more proper to one node than to the others */
  affinity: Affinity[];
  /** canonical injection: each node's circle A inside the universe of its scenes, and what lies outside it */
  circles: Circle[];
  /** identity function: what stays the same for each node from the beginning to the end, and which way what surrounds it moves */
  arcs: Arc[];
  tension: ToneMap;
  map4d: LayerMap;
  /** structure-preserving maps: chapters with the same skeleton of relations, the hierarchy among characters, places and objects, the consistency of the themes */
  morphisms: Morphisms;
  /** everything the engine knows about each important character and place, gathered so a report can write about it */
  dossiers: Dossier[];
  /** the whole report (≈40 pages): its blocks, the sheets per character / location, and which mechanisms feed each section */
  reportPlan: ReportPlan;
  /** what a model needs to finish the work: where it stops, who is still on stage, what is left open */
  completion: CompletionBrief;
  /** the text of each page (only with `keepPages`): page n is pageText[n - 1] */
  pageText?: string[];
  /** blocks that would work better somewhere else, with what each move gains and keeps */
  restructure: Restructure;
  /** milliseconds spent in each stage of the engine */
  timings: Record<string, number>;
  /** the same for the world: what remains unchanged, what drifts, whether the book returns to its origin */
  worldIdentity: WorldIdentity;
  /** a chain for EVERY word, the basic ones too: count, positions, neighbours, solar system, the nodes it keeps company with */
  wordIndex: Record<string, WordEntry>;
  /** the identity classes of the work: John de Bohême = John = Bohême = rey = monarca */
  equivalenceClasses: EquivalenceClass[];
  structure:  StructureReading;
  sentences:  SentenceReading;
  forest:     ForestTree[];
  treeRelations: TreeRelation[];
  chapters:   ChapterReading[];
  /** the semantic fields of the work (clusters of the embedding), each named by its central words */
  fields:     { id: number; label: string[]; size: number; valence: number }[];
  themeForest: ThemeTree[];
  themeRelations: ThemeRelation[];
  knots:      KnotReading;
  timeAxis:   { months: { month: string; day: number | null; year: number | null; page: number }[]; yearFirstPage: Record<number, number> };
}

export interface NodesOptions {
  /** keep a chain for every word of the work (default true). Turn it off to get a lighter result. */
  wordIndex?: boolean;
  /** keep the text of every page in the result, so a model can be handed exactly the pages the map points at */
  keepPages?: boolean;
  language?: NodesLang;
  /** words per page when the text has no real page breaks (default 250) */
  pageWords?: number;
}

// ─── internals ──────────────────────────────────────────────────────────────────
interface Tok { w: string; idx: number; end: number; pdf: number; par: boolean; slug: boolean }
interface Occ { pg: number; k: number }
interface Ent {
  name: string; aliases: string[]; occ: Occ[]; lex: boolean;
  bag?: Map<string, number>;
  kind?: NodeKind; ch?: number; pl?: number;
}

const BINS_MAX = 40;
const round2 = (x: number) => Math.round(x * 100) / 100;
const DASH_START = /^[—–―«“「『"]/;
const WINDOW = 14;                       // tokens each side that make up a solar system
/** length of a word in Latin-letter terms: an ideograph or kana carries about as much as two letters, so the minimum-length filters tuned for alphabets do not erase whole scripts */
const CJK_LIKE = /[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Thai}\p{Script=Lao}\p{Script=Khmer}\p{Script=Myanmar}]/u;
const wl = (w: string) => CJK_LIKE.test(w) ? [...w].length * 2 : w.length;
const isCapBase = (w: string) => /^\p{Lu}/u.test(w) && w.length > 1 && !/['’]/.test(w);
const isAllCaps = (w: string) => /^\p{Lu}{2,}$/u.test(w);
const normCache = new WeakMap<Map<string, number>, { n: number; size: number }>();
const normOf = (A: Map<string, number>) => { const c = normCache.get(A); if (c && c.size === A.size) return c.n; let n = 0; for (const v of A.values()) n += v * v; normCache.set(A, { n, size: A.size }); return n; };
const mergeBag = (into: Map<string, number>, from: Map<string, number>) => { for (const [w, c] of from) into.set(w, (into.get(w) ?? 0) + c); normCache.delete(into); };
const cosine = (A: Map<string, number>, B: Map<string, number>) => {
  const [S, T] = A.size <= B.size ? [A, B] : [B, A];
  let d = 0; for (const [w, c] of S) { const o = T.get(w); if (o) d += c * o; }
  return d / Math.sqrt(normOf(A) * normOf(B) || 1);
};

export function analyzeNodes(text: string, opts: NodesOptions = {}): NodesResult {
  const t0 = Date.now();
  const timings: Record<string, number> = {}; let curStage = 'start', lastLap = t0;
  const lap = (next: string) => { const t = Date.now(); timings[curStage] = (timings[curStage] ?? 0) + t - lastLap; lastLap = t; curStage = next; };
  const lang: NodesLang = opts.language ?? detectLang(text);
  const L: Lexicon = LEXICONS[lang];
  const stopSet: Set<string> = lang === 'auto' ? new Set() : L.stop;

  lap('1 clean');
  // ── 1. clean: drop watermark / running-header lines (short lines that repeat), keep cues ──
  const lineCount = new Map<string, number>();
  for (const l of text.split('\n')) { const s = l.trim(); if (s && s.length <= 14) lineCount.set(s, (lineCount.get(s) ?? 0) + 1); }
  const junk = new Set([...lineCount].filter(([s, c]) => c >= 3 && !/^\p{Lu}{3,}$/u.test(s)).map(([s]) => s));
  const rawPages = text.split('\f');
  // page furniture: a line (digits ignored) that shows up on a quarter of the pages is a running header / footer, not text
  const furniture = new Set<string>();
  if (rawPages.length >= 2) {
    const onPages = new Map<string, number>();
    for (const pg of rawPages) for (const k of new Set(pg.split('\n').map(l => l.trim().replace(/\d+/g, '#').replace(/\s+/g, ' ')).filter(Boolean))) onPages.set(k, (onPages.get(k) ?? 0) + 1);
    // long documents: a quarter of the pages; a handful of pages (a short film): the same line on at least half of them. ALL-CAPS cue lines never count.
    const need = rawPages.length >= 8 ? Math.max(4, rawPages.length * 0.25) : Math.max(2, Math.ceil(rawPages.length * 0.5));
    for (const [k, c] of onPages) if (c >= need && k.length >= (rawPages.length >= 8 ? 6 : 12) && k !== k.toUpperCase()) furniture.add(k);
  }
  const pdfPages = rawPages.map(p => p.split('\n').filter(l => !junk.has(l.trim()) && !furniture.has(l.trim().replace(/\d+/g, '#').replace(/\s+/g, ' '))).join('\n').replace(/\u200b/g, ''));
  const raw = pdfPages.join(' \f ').replace(/-\n(?=[a-zñáéíóú])/g, '').replace(/[ \t]*\n[ \t]*/g, ' ¶ ').replace(/ +/g, ' ');

  const inParen = new Uint8Array(raw.length);
  { let d = 0; for (let i = 0; i < raw.length; i++) { if (raw[i] === '(') d++; inParen[i] = d > 0 ? 1 : 0; if (raw[i] === ')' && d > 0) d--; } }
  const slugs = [...raw.matchAll(/(\d+)\.\s*(INT|EXT)\.?\s+(.+?)\.\s+([A-ZÁÉÍÓÚ ]+)\./g)]
    .map(m => ({ a: m.index ?? 0, b: (m.index ?? 0) + m[0].length, id: m[1], ie: m[2], place: m[3].trim(), time: m[4].trim() }));
  const inSlug = (i: number) => slugs.some(s => i >= s.a && i < s.b);

  lap('2 tokens');
  // ── 2. tokens ─────────────────────────────────────────────────────────────────
  const toks: Tok[] = [];
  let pdfPg = 1;
  // Scripts written without spaces (Chinese, Thai, Lao, Khmer, Myanmar): where words end is learned from the text itself — a stretch that repeats is a word, and the split that
  // makes the most of repeated stretches wins. Katakana runs and hiragana runs are cut at the change of script.
  const SPACELESS = /[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Thai}\p{Script=Lao}\p{Script=Khmer}\p{Script=Myanmar}]/u;
  const scriptRuns = (w: string): string[] => w.match(/\p{Script=Han}+|\p{Script=Hiragana}+|\p{Script=Katakana}+|[\p{Script=Thai}\p{Script=Lao}\p{Script=Khmer}\p{Script=Myanmar}]+|[^\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Thai}\p{Script=Lao}\p{Script=Khmer}\p{Script=Myanmar}]+/gu) ?? [w];
  const segLex = new Map<string, number>();
  const isLong = (r: string) => /^[\p{Script=Han}\p{Script=Thai}\p{Script=Lao}\p{Script=Khmer}\p{Script=Myanmar}]+$/u.test(r);
  if (SPACELESS.test(raw)) {
    const runs: string[] = []; for (const m of raw.matchAll(/[\p{L}\p{M}]+/gu)) if (SPACELESS.test(m[0])) for (const r of scriptRuns(m[0])) if (isLong(r) && [...r].length >= 2) runs.push(r);
    const cnt = new Map<string, number>(); for (const r of runs) { const cs = [...r]; for (let n = 1; n <= 4; n++) for (let i = 0; i + n <= cs.length; i++) { const g = cs.slice(i, i + n).join(''); cnt.set(g, (cnt.get(g) ?? 0) + 1); } }
    const thr = Math.max(2, Math.round(runs.length / 4000));
    // a stretch is a word when it repeats AND it holds together: wherever one of its halves appears, the other is usually there too (cohesion = its count over the rarer half's count)
    for (const [g, c] of cnt) { const cs = [...g]; if (cs.length < 2 || c < thr) continue; let coh = 1; for (let i = 1; i < cs.length; i++) coh = Math.min(coh, c / Math.max(1, Math.min(cnt.get(cs.slice(0, i).join('')) ?? 1, cnt.get(cs.slice(i).join('')) ?? 1))); if (coh >= 0.5) segLex.set(g, c * 1000 + Math.round(coh * 999)); }
  }
  const segment = (r: string): string[] => {
    const cs = [...r]; if (cs.length < 2 || !segLex.size) return cs.length < 2 ? [r] : cs;
    const best = new Array<number>(cs.length + 1).fill(-1e9), from = new Array<number>(cs.length + 1).fill(0); best[0] = 0;
    for (let i = 1; i <= cs.length; i++) for (let n = 1; n <= 4 && n <= i; n++) { const g = cs.slice(i - n, i).join(''), e = n === 1 ? 0 : (segLex.get(g) ?? 0), c = Math.floor(e / 1000), coh = (e % 1000) / 999; const sc = n === 1 ? 0.05 : c ? Math.log(c) * coh * Math.sqrt(n) : -1e9; if (best[i - n] + sc > best[i]) { best[i] = best[i - n] + sc; from[i] = i - n; } }
    const out: string[] = []; for (let i = cs.length; i > 0; i = from[i]) out.unshift(cs.slice(from[i], i).join('')); return out;
  };
  for (const m of raw.matchAll(/\f|[\p{L}\p{M}][\p{L}\p{M}'’]*|\d+/gu)) {
    if (m[0] === '\f') { pdfPg++; continue; }
    const idx = m.index ?? 0;
    if (SPACELESS.test(m[0])) { let off = idx; for (const r of scriptRuns(m[0])) { for (const sg of (isLong(r) ? segment(r) : [r])) { toks.push({ w: sg, idx: off, end: off + sg.length, pdf: pdfPg, par: inParen[off] === 1, slug: inSlug(off) }); off += sg.length; } } continue; }
    toks.push({ w: m[0].replace(L.possessive, ''), idx, end: idx + m[0].length, pdf: pdfPg, par: inParen[idx] === 1, slug: inSlug(idx) });
  }
  const realPages = pdfPg > 1;
  const PAGE = opts.pageWords ?? 250;
  const page = (k: number) => realPages ? toks[k].pdf : Math.floor(k / PAGE) + 1;
  const NP = toks.length ? page(toks.length - 1) : 0;
  // Writing systems without capitals (Chinese, Japanese, Arabic, Hebrew, Thai…) cannot mark a name by its first letter. There, a node is a word that recurs, is not a function word
  // (those are spread over most sentences) and is not a bare particle; katakana runs, the script's own mark for foreign and proper names, always qualify.
  const letterCount = (raw.match(/\p{L}/gu) ?? []).length, casedCount = (raw.match(/[\p{Lu}\p{Ll}]/gu) ?? []).length;
  const caseless = letterCount > 50 && casedCount / letterCount < 0.2;
  const caselessCand = new Set<string>();
  const isCap = (w: string) => caseless ? caselessCand.has(w) : isCapBase(w);
  const sid = new Int32Array(toks.length);       // sentence index of every token (terminators of every script, or a line break)
  { let c = 0; for (let k = 0; k < toks.length; k++) { sid[k] = c; if (k + 1 < toks.length && /[.!?…。！？｡؟۔।॥¶\f]/.test(raw.slice(toks[k].end, toks[k + 1].idx))) c++; } }
  const lw = (k: number) => toks[k]?.w.toLowerCase() ?? '';
  const before = (k: number) => raw.slice(Math.max(0, toks[k].idx - 4), toks[k].idx);
  const sentStart = (k: number) => k === 0 || (!(abbrTok[k - 1] === 1) && (/[.!?"”»—¶(。！？｡؟۔।]\s*$/.test(before(k)) || /[¿¡]$/.test(before(k).trim())));
  const alone = (k: number) => (k === 0 || /¶\s*$/.test(before(k))) && (/^\s*(\([^)]*\)\s*)?¶/.test(raw.slice(toks[k].end, toks[k].end + 40)) || raw.slice(toks[k].end).trim() === '');
  // Abbreviations (Dr., Sr., Mr., St.) are learned from the text: a short capitalised word that is followed by a full stop and then, in nearly every occurrence, by another capitalised
  // word on the same line. Its full stop closes nothing: the sentence goes on and the name behind it belongs to it ("Dr. Anthony").
  const abbrTok = new Uint8Array(toks.length);
  { const tot = new Map<string, number>(), hit = new Map<string, number>(), at: number[] = [];
    for (let k = 0; k < toks.length - 1; k++) { const w = toks[k].w; if (w.length > 4 || !/^\p{Lu}/u.test(w) || w !== w[0] + w.slice(1).toLowerCase()) continue; tot.set(w, (tot.get(w) ?? 0) + 1);
      const gap = raw.slice(toks[k].end, toks[k + 1].idx); if (/^\.[ \t]+$/.test(gap) && /^\p{Lu}/u.test(toks[k + 1].w)) { hit.set(w, (hit.get(w) ?? 0) + 1); at.push(k); } }
    const ok = new Set([...hit].filter(([w, h]) => h >= 2 && h / (tot.get(w) ?? 1) >= 0.8).map(([w]) => w));
    for (const k of at) if (ok.has(toks[k].w)) abbrTok[k] = 1; }
  const glue = (a: number, b: number) => { const g = raw.slice(toks[a].end, toks[b].idx).trim(); return g === '' || (g === '.' && abbrTok[a] === 1); };

  lap('2b function words of THIS text');
  // ── 2b. function words of THIS text: the most frequent ones. Used for structure, and as the stop list when no list fits ──
  const monthSet0 = new Set(L.months);
  const freq = new Map<string, number>();
  for (const t of toks) { const w = t.w.toLowerCase(); freq.set(w, (freq.get(w) ?? 0) + 1); }
  const topFreq = new Set([...freq].sort((a, b) => b[1] - a[1]).slice(0, 80).map(x => x[0]));
  if (lang === 'auto') {
    // No list fits: a function word is frequent, not a name (rarely capitalised mid-sentence) and, in a long text, spread over most pages
    const cand = [...freq].sort((a, b) => b[1] - a[1]).slice(0, NP < 8 ? 40 : 150).map(x => x[0]);
    const capN = new Map<string, number>(), pgsOf = new Map<string, Set<number>>();
    const sentCover = new Map<string, Set<number>>(); toks.forEach((t, k) => { const w = t.w.toLowerCase(); (sentCover.get(w) ?? sentCover.set(w, new Set()).get(w)!).add(sid[k]); });
    toks.forEach((t, k) => { const w = t.w.toLowerCase(); if (isCap(t.w) && !sentStart(k)) capN.set(w, (capN.get(w) ?? 0) + 1); (pgsOf.get(w) ?? pgsOf.set(w, new Set()).get(w)!).add(page(k)); });
    for (const w of cand) {
      const capShare = (capN.get(w) ?? 0) / (freq.get(w) ?? 1);
      if (caseless) { const cov = (sentCover.get(w)?.size ?? 0) / Math.max(1, sid[toks.length - 1] + 1); if (cov < 0.25) continue; }       // a function word is spread over most sentences; a name is not
      if (capShare >= 0.3) continue;
      if (NP >= 8 && (pgsOf.get(w)?.size ?? 0) < NP * 0.5) continue;
      stopSet.add(w);
    }
  }

  lap('2c voice');
  // ── 2c. voice: a dash or an opening quote starts a character's speech; a second dash is an action tag ──
  const tmode = new Uint8Array(toks.length);          // 0 narration · 1 dialogue · 2 action tag
  {
    const DASH = '—–―', OPEN = '«“「『', CLOSE = '»”」』', TERMINAL = '.!?…:»”"」』)。！？';
    let mode = 0, ti = 0, paraStart = true, last = '';
    for (let i = 0; i < raw.length; i++) {
      while (ti < toks.length && toks[ti].idx === i) { tmode[ti] = mode; ti++; }
      const c = raw[i];
      if (c === '¶' || c === '\f') {
        let j = i + 1, breaks = c === '\f' ? 2 : 1;
        while (j < raw.length && (raw[j] === ' ' || raw[j] === '¶' || raw[j] === '\f')) { if (raw[j] !== ' ') breaks++; j++; }
        const next = raw[j] ?? '';
        const startsNew = /[\p{Lu}¿¡\d]/u.test(next) || DASH.includes(next) || OPEN.includes(next) || next === '"';
        if (j >= raw.length || breaks >= 2 || (TERMINAL.includes(last) && startsNew)) { mode = 0; paraStart = true; }
        continue;
      }
      if (c === ' ') continue;
      if (DASH.includes(c)) { mode = paraStart ? 1 : (mode === 1 ? 2 : (mode === 2 ? 1 : 2)); }
      else if (OPEN.includes(c)) mode = 1;
      else if (CLOSE.includes(c)) mode = 0;
      else if (c === '"') mode = mode === 1 ? 0 : 1;
      paraStart = false; last = c;
    }
  }

  // screenplay: the lines after a cue (an ALL-CAPS name alone on a line, repeated) are that character speaking; (…) is an action tag
  {
    const cueCount = new Map<string, number>();
    for (let k = 0; k < toks.length; k++) if (isAllCaps(toks[k].w) && !toks[k].slug && alone(k)) cueCount.set(toks[k].w, (cueCount.get(toks[k].w) ?? 0) + 1);
    const cues = new Set([...cueCount].filter(([, c]) => c >= 2).map(([w]) => w));
    if (cues.size) {
      let speaking = false;
      for (let k = 0; k < toks.length; k++) {
        if (cues.has(toks[k].w) && alone(k)) { speaking = true; tmode[k] = 1; continue; }
        if (k > 0 && /¶\s*¶/.test(raw.slice(toks[k - 1].end, toks[k].idx))) speaking = false;
        if (speaking && !toks[k].slug) tmode[k] = toks[k].par ? 2 : 1;
      }
    }
  }

  if (caseless) {
    // Without capitals, a character is the word that stands beside speech: it recurs, it is not spread over most sentences (function words are) and a good part of its mentions sit
    // right next to a quotation (it speaks, or is spoken to). Katakana runs, the script's own mark for foreign and proper names, always qualify. Places carry no such mark in these
    // scripts, so they are only found when a katakana run or a scene heading names them.
    const nSent = Math.max(1, sid[toks.length - 1] + 1), cover = new Map<string, Set<number>>(), near = new Map<string, number>();
    const inQ = (j: number) => j >= 0 && j < toks.length && tmode[j] === 1;
    toks.forEach((t, k) => { (cover.get(t.w) ?? cover.set(t.w, new Set()).get(t.w)!).add(sid[k]); if (!inQ(k) && (inQ(k - 1) || inQ(k - 2) || inQ(k - 3) || inQ(k + 1) || inQ(k + 2) || inQ(k + 3) || inQ(k + 4))) near.set(t.w, (near.get(t.w) ?? 0) + 1); });
    for (const orig of cover.keys()) { const w = orig.toLowerCase(), c = freq.get(w) ?? 0;
      if (/\d/.test(orig) || stopSet.has(w) || monthSet0.has(w)) continue;
      if (/^\p{Script=Katakana}{2,}$/u.test(orig)) { if (c >= 2) caselessCand.add(orig); continue; }
      if (c >= 4 && wl(orig) >= 4 && (cover.get(orig)?.size ?? 0) / nSent < 0.25 && (near.get(orig) ?? 0) / c >= 0.3) caselessCand.add(orig); }
  }
  lap('2d structure');
  // ── 2d. structure: body of the work vs front / back matter, and headings ────────
  const layerOf = (k: number) => page(k);
  const proseShare = new Array<number>(NP).fill(0), layerTokens = new Array<number>(NP).fill(0);
  toks.forEach((t, k) => { const p = layerOf(k) - 1; layerTokens[p]++; if (topFreq.has(t.w.toLowerCase())) proseShare[p]++; });
  for (let p = 0; p < NP; p++) proseShare[p] = layerTokens[p] ? proseShare[p] / layerTokens[p] : 0;
  let body: [number, number] | null = null;
  if (NP >= 8) {
    const sorted = [...proseShare].sort((a, b) => a - b), ref = sorted[Math.floor(sorted.length * 0.6)];
    const isBody = proseShare.map(v => v >= ref * 0.8);
    let bestLo = -1, bestHi = -1, lo = -1, gaps = 0;
    for (let p = 0; p <= NP; p++) {
      if (p < NP && isBody[p]) { if (lo < 0) lo = p; gaps = 0; }
      else if (lo >= 0 && (p === NP || ++gaps > 2)) { const hi = p === NP ? p - 1 - gaps : p - gaps; if (hi - lo > bestHi - bestLo) { bestLo = lo; bestHi = hi; } lo = -1; gaps = 0; }
    }
    if (bestLo >= 0 && bestHi - bestLo + 1 >= NP * 0.4 && (bestLo > 0 || bestHi < NP - 1)) body = [bestLo + 1, bestHi + 1];
  }
  const inBody = (k: number) => !body || (layerOf(k) >= body[0] && layerOf(k) <= body[1]);
  type Ln = { page: number; text: string; words: number; term: boolean; prevBlank: boolean; nextBlank: boolean; nextWords: number; gapAbove: number; gapBelow: number };
  let allLines: Ln[] = [];
  const headings: StructureReading['headings'] = [];
  const chapterMarks: { page: number; title: string; inferred?: boolean }[] = [];
  let chapterSource: StructureReading['chapterSource'] = 'none';
  {
    const lines: Ln[] = []; let tc = 0; const allGaps: number[] = [];       // the blank lines above EVERY line of text: the document's own space between paragraphs
    pdfPages.forEach((pg, pi) => {
      const ls = pg.split('\n');
      ls.forEach((l, li) => {
        const t = l.trim(); const n = (t.match(/[\p{L}\p{N}]+/gu) ?? []).length;
        if (t && li > 0) { let g = 0; for (let q = li - 1; q >= 0 && ls[q].trim() === ''; q--) g++; if (g > 0) allGaps.push(g); }
        if (t && n >= 1 && n <= 8 && !DASH_START.test(t) && /\p{L}|\d/u.test(t)) {
          // the prose that follows: the longest of the next three non-empty lines (a title may be followed by a subtitle first)
          let j = li + 1, seen = 0, nw = 0; for (; j < ls.length && seen < 3; j++) { if (ls[j].trim() === '') continue; seen++; nw = Math.max(nw, (ls[j].match(/[\p{L}\p{N}]+/gu) ?? []).length); }
          lines.push({ page: realPages ? pi + 1 : Math.floor(tc / PAGE) + 1, text: t, words: n, term: /[.!?…,;:]$/.test(t),
            prevBlank: li === 0 || ls[li - 1].trim() === '', nextBlank: li === ls.length - 1 || ls[li + 1].trim() === '',
            nextWords: nw, gapAbove: (() => { let g = 0; for (let q = li - 1; q >= 0 && ls[q].trim() === ''; q--) g++; return g; })(), gapBelow: (() => { let g = 0; for (let q = li + 1; q < ls.length && ls[q].trim() === ''; q++) g++; return g; })() });
        }
        tc += n;
      });
    });
    allLines = lines;
    const lineFreq = new Map<string, number>(); for (const l of lines) lineFreq.set(l.text, (lineFreq.get(l.text) ?? 0) + 1);
    for (let i = lines.length - 1; i >= 0; i--) if ((lineFreq.get(lines[i].text) ?? 0) >= 3 && lines[i].text === lines[i].text.toUpperCase() && !/\d/.test(lines[i].text)) lines.splice(i, 1);
    const shape = (t: string) => t.toLowerCase().replace(/\b[ivxlcdm]+\b/g, '#').replace(/\d+/g, '#');
    const byShape = new Map<string, Ln[]>();
    for (const l of lines) if (l.prevBlank && !l.term && /#/.test(shape(l.text))) (byShape.get(shape(l.text)) ?? byShape.set(shape(l.text), []).get(shape(l.text))!).push(l);
    for (const grp of byShape.values()) if (grp.length >= 3 && grp.length < NP * 0.5 && new Set(grp.map(g => g.text)).size >= 3) for (const g of grp) { headings.push({ page: g.page, text: g.text, numbered: true }); chapterMarks.push({ page: g.page, title: g.text }); }
    // A counter wins only if it really carries the book: many marks, or marks spread over half of it. Three dated headings in the last third («Día 24 de Diciembre»)
    // are a device inside the story, not its chapters: the islands decide, and the counter's marks are added to them.
    const bodyLen0 = body ? body[1] - body[0] + 1 : NP, numMarks = chapterMarks.slice(), numPages = numMarks.map(m => m.page);
    const numCovers = numMarks.length >= 6 || (numMarks.length >= 3 && (Math.max(...numPages) - Math.min(...numPages)) / Math.max(1, bodyLen0) >= 0.5);
    if (chapterMarks.length >= 3 && numCovers) chapterSource = 'numbered';
    else {
      chapterMarks.length = 0;
      // no counter: an ISLAND is a title — a short line with empty space above AND below, then a full line of prose.
      // (When the text carries no empty space below its short lines at all, fall back to "blank above + prose right after".)
      const bodyOk = (l: Ln) => !body || (l.page >= body[0] && l.page <= body[1]);
      // THE SIZE OF THE SPACE. In a document where every paragraph already stands apart, a short line is a title only if the space around it is clearly larger than the one
      // between paragraphs. The usual space is measured on the document itself; a title stands in at least that plus two lines, above and below, whatever its case.
      const gaps = allGaps.slice().sort((a, b) => a - b), g0 = gaps.length ? gaps[Math.floor(gaps.length / 2)] : 1, bigGap = Math.max(g0 + 2, Math.ceil(g0 * 1.8));
      const sentenceLike = (l: Ln) => /[.!?…]$/.test(l.text) && l.words >= 4;                      // a line that ends like a sentence and has words enough is a sentence, not a title
      const gapIslands = lines.filter(l => l.gapAbove >= bigGap && l.gapBelow >= bigGap && l.words <= 8 && !sentenceLike(l) && !DASH_START.test(l.text) && l.nextWords >= 5 && bodyOk(l));
      const strict0 = lines.filter(l => l.prevBlank && l.nextBlank && l.words <= 8 && /^\p{Lu}/u.test(l.text) && !/\d/.test(l.text) && l.nextWords >= 7 && bodyOk(l));
      const strict = strict0.filter(l => !sentenceLike(l));
      const loose = lines.filter(l => l.prevBlank && l.words <= 4 && /^\p{Lu}/u.test(l.text) && l.nextWords >= 7 && (!l.term || l.words <= 3) && bodyOk(l));
      const bodyLen = body ? body[1] - body[0] + 1 : NP;
      const fits = (a: Ln[]) => a.length >= 3 && a.length <= NP / 2 && bodyLen / a.length >= 2;
      const pick = gapIslands.length >= 5 && fits(gapIslands) ? gapIslands : fits(strict) ? strict : fits(loose) ? loose : null;
      if (pick) { for (const g of pick) { headings.push({ page: g.page, text: g.text, numbered: false }); chapterMarks.push({ page: g.page, title: g.text }); } chapterSource = pick === loose ? 'titles-loose' : 'titles';
        for (const m of numMarks) if (!chapterMarks.some(x => x.page === m.page)) chapterMarks.push(m); }
      else if (numMarks.length >= 3) { for (const m of numMarks) chapterMarks.push(m); chapterSource = 'numbered'; }
    }
    const used = new Set(headings.map(h => h.text));
    for (const l of lines) if (l.prevBlank && !l.term && !used.has(l.text) && (!body || l.page < body[0] || l.page > body[1]) && headings.length < 80) headings.push({ page: l.page, text: l.text, numbered: false });
    headings.sort((a, b) => a.page - b.page);
  }
  // chapters: marks inside the body; the body's first page opens chapter 1. Without marks the body is cut in equal islands.
  let bodyFrom = body ? body[0] : 1, bodyTo = body ? body[1] : NP;
  let starts = [...new Set(chapterMarks.map(m => m.page).filter(pg => pg >= bodyFrom && pg <= bodyTo))].sort((x, y) => x - y);
  if (starts.length < 2) { chapterSource = NP >= 8 ? 'windows' : 'none'; const n = NP >= 8 ? Math.min(12, Math.max(2, Math.round((bodyTo - bodyFrom + 1) / 8))) : 1; starts = Array.from({ length: n }, (_, i) => bodyFrom + Math.round(i * (bodyTo - bodyFrom + 1) / n)); }
  else if (starts[0] > bodyFrom) starts.unshift(bodyFrom);
  // A chapter must exist where the rhythm says so. Chapters repeat at a roughly regular distance; a gap much wider than
  // the usual one is searched again, with looser eyes, for the title island that was missed — or, failing that, for the page
  // where the vocabulary of the text changes the most.
  const inferred = new Map<number, 'island+shift' | 'island' | 'shift'>();
  if (starts.length >= 6 && (chapterSource === 'numbered' || chapterSource === 'titles' || chapterSource === 'titles-loose')) {
    const sp = starts.slice(1).map((v, i) => v - starts[i]).sort((a, b) => a - b), med = sp[Math.floor(sp.length / 2)];
    const pageSets: Set<string>[] = Array.from({ length: NP + 2 }, () => new Set<string>());
    toks.forEach((t, k) => { const w = t.w.toLowerCase(); if (wl(w) >= 4 && !topFreq.has(w) && !stopSet.has(w) && !/\d/.test(w)) pageSets[page(k)].add(w); });
    const shift = (pg: number) => {                    // how different are the 2 pages after pg from the 2 pages before it
      const A = new Set<string>(), B = new Set<string>();
      for (const d of [-2, -1]) pageSets[pg + d]?.forEach(w => A.add(w));
      for (const d of [0, 1]) pageSets[pg + d]?.forEach(w => B.add(w));
      let i = 0; for (const w of A) if (B.has(w)) i++;
      return 1 - i / (A.size + B.size - i || 1);
    };
    // How regular is the rhythm? When chapters keep a steady distance (low spread around the median), a gap of about twice that distance
    // IS a missing chapter: no further evidence is needed, only a place to put it. When the book's chapters vary a lot, evidence is required.
    const dev = sp.map(v => Math.abs(v - med)).sort((a, b) => a - b), mad = dev[Math.floor(dev.length / 2)];
    const regular = med > 0 && mad / med <= 0.12;
    const bounds = [...starts, bodyTo + 1];
    const shifts = new Map<number, number>(); for (let q = bodyFrom + 2; q <= bodyTo - 1; q++) shifts.set(q, shift(q));
    const sortedShifts = [...shifts.values()].sort((x, y) => x - y), p80 = sortedShifts[Math.floor(sortedShifts.length * 0.8)] ?? 1, p90 = sortedShifts[Math.floor(sortedShifts.length * 0.9)] ?? 1;
    for (let g = 0; g + 1 < bounds.length; g++) {
      const a = bounds[g], b = bounds[g + 1], span = b - a;
      if (span <= med * (regular ? 1.6 : 1.4) || span < 6) continue;
      const missing = Math.max(1, Math.round(span / med) - 1);
      const margin = Math.max(2, Math.round(med * 0.4));
      const taken: number[] = [];
      for (let m = 1; m <= missing; m++) {
        const expect = a + Math.round(span * m / (missing + 1));
        // every page of the gap is a candidate: a looser title island and/or a strong change of vocabulary there
        let best: { pg: number; score: number; title: string; by: 'island+shift' | 'island' | 'shift' } | null = null;
        for (let q = a + margin; q <= b - margin; q++) {
          if (taken.some(t => Math.abs(t - q) < margin)) continue;
          const isl = allLines.filter(l => l.page === q && l.prevBlank && l.nextBlank && l.words <= 10 && /^\p{Lu}/u.test(l.text) && !l.term && !DASH_START.test(l.text))[0];
          const sh = shifts.get(q) ?? 0;
          const score = (isl ? 2 : 0) + sh - Math.abs(q - expect) / span;
          if (!regular && !isl && sh < p90) continue;           // irregular book: no island and no sharp change of vocabulary → not a chapter
          if (!best || score > best.score) best = { pg: q, score, title: isl?.text ?? '', by: isl ? (sh >= p80 ? 'island+shift' : 'island') : 'shift' };
        }
        if (best && !starts.includes(best.pg)) { starts.push(best.pg); taken.push(best.pg); inferred.set(best.pg, best.by); chapterMarks.push({ page: best.pg, title: best.title || 'Chapter ?', inferred: true }); }
      }
    }
    starts.sort((x, y) => x - y);
  }
  // What is not the story: whatever stands before the first real chapter (dedication, epigraph, introduction…) and after the last (notes, index,
  // acknowledgments…). The unnamed stretch before the first title is front matter by definition; the others are told by their own heading.
  const frontSections: StructureReading['frontSections'] = [], backSections: StructureReading['backSections'] = [];
  { const fold = (t: string) => t.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^\p{L}]/gu, '');
    const markAt = (pg: number) => chapterMarks.find(m => m.page === pg);
    // THE CONTENTS LIST. A label word that begins many short lines ("CHAPTER ONE", "Kapitel 2", "Capítulo III") in the first pages lists the chapters of the
    // book; the entries that stand in that list WITHOUT the label (Introduction, Characters…) before the first labelled one are front matter, and after the
    // last labelled one, back matter. No word of any language is needed: the book shows it with its own layout.
    let tocLabel: string | null = null; const labelled = new Set<string>(), unlabelled = new Set<string>(); let firstLabelledPage = Infinity;
    if (NP >= 8) {
      const front = allLines.filter(l => l.page <= Math.max(12, Math.ceil(NP * 0.08)));
      const ft = (t: string) => t.toLowerCase().match(/^\p{L}{3,}/u)?.[0] ?? '';
      const cnt = new Map<string, number>(); for (const l of front) { const f = ft(l.text); if (f) cnt.set(f, (cnt.get(f) ?? 0) + 1); }
      const top = [...cnt].sort((a, b) => b[1] - a[1])[0];
      if (top && top[1] >= 6) {
        tocLabel = top[0];
        const idx = allLines.map((l, i) => ({ l, i })).filter(x => x.l.page <= Math.max(12, Math.ceil(NP * 0.08)) && ft(x.l.text) === tocLabel);
        const isEntryOf = new Set<number>(idx.map(x => x.i + 1));
        const pgLo = idx[0].l.page - 1, pgHi = idx[idx.length - 1].l.page + 1;
        for (const x of idx) { const e = allLines[x.i + 1]; if (e && ft(e.text) !== tocLabel) labelled.add(fold(e.text)); }
        allLines.forEach((l, i) => { if (l.page >= pgLo && l.page <= pgHi && ft(l.text) !== tocLabel && !isEntryOf.has(i)) unlabelled.add(fold(l.text)); });
      }
    }
    const inSet = (set: Set<string>, f: string) => wl(f) >= 4 && [...set].some(x => wl(x) >= 4 && (x.includes(f) || f.includes(x)));
    const kindOf = (pg: number): 'front' | 'back' | 'story' => {
      const m = markAt(pg); if (!m) return 'story'; const f = fold(m.title);
      if (L.sections.front.some(w => f.includes(w))) return 'front';
      if (L.sections.back.some(w => f.includes(w))) return 'back';
      if (tocLabel && !inSet(labelled, f) && inSet(unlabelled, f)) return pg < firstLabelledPage ? 'front' : 'back';
      return 'story';
    };
    if (tocLabel) for (const st of starts) { const m = markAt(st); if (m && inSet(labelled, fold(m.title))) { firstLabelledPage = Math.min(firstLabelledPage, st); } }
    if ((L.sections.front.length || tocLabel) && chapterSource !== 'windows' && chapterSource !== 'none') {
      // the title page, the epigraph and its author stand before the prologue / introduction: whatever precedes the last front title of the opening stretch is front matter too
      { const lim = bodyFrom + Math.max(6, Math.round((bodyTo - bodyFrom + 1) * 0.12)); let lastF = -1; starts.forEach((st, i) => { if (st <= lim && kindOf(st) === 'front') lastF = i; });
        for (let i = 0; i < lastF && starts.length > 1; i++) { frontSections.push({ title: markAt(starts[0])?.title ?? 'Front matter', pages: [starts[0], starts[1] - 1] }); starts.shift(); } }
      while (starts.length > 1 && (!markAt(starts[0]) || kindOf(starts[0]) === 'front')) { frontSections.push({ title: markAt(starts[0])?.title ?? 'Front matter', pages: [starts[0], starts[1] - 1] }); starts.shift(); }
      while (starts.length > 1 && kindOf(starts[starts.length - 1]) === 'back') { const st = starts.pop()!; backSections.unshift({ title: markAt(st)?.title ?? '', pages: [st, bodyTo] }); bodyTo = st - 1; }
      if (frontSections.length || backSections.length) { bodyFrom = starts[0]; body = [bodyFrom, bodyTo]; }
    }
  }
  // Whatever lies outside the body also has its headings: the sections the body detection left out (notes, appendix, index… / contents, characters…)
  if (body) {
    const norm = (t: string) => t.toLowerCase().replace(/[^\p{L}]/gu, '');
    const known = new Set([...frontSections, ...backSections].map(x => norm(x.title)));
    const after = headings.filter(h => !h.numbered && h.page > body![1] && !known.has(norm(h.text))).filter((h, i, a) => a.findIndex(x => norm(x.text) === norm(h.text)) === i).slice(0, 12);
    after.forEach((h, i) => backSections.push({ title: h.text, pages: [h.page, i + 1 < after.length ? after[i + 1].page - 1 : NP] }));
  }
  const chapterOfPage = (pg: number) => { let c = 0; for (let i = 0; i < starts.length; i++) if (pg >= starts[i]) c = i; return c; };
  // A chapter title is a label, not part of the chapter's text: its words never count as mentions, as rarity, as event words or as tone.
  const titleTok = new Uint8Array(toks.length);
  {
    const norm = (t: string) => t.toLowerCase().replace(/[^\p{L}]/gu, '');
    const titles = chapterMarks.map(m => ({ page: m.page, key: norm(m.title) })).filter(t => t.key.length > 0 && t.key !== 'chapter');
    if (titles.length) {
      let s0 = 0;
      for (let k = 0; k < toks.length; k++) {
        const endOfLine = k === toks.length - 1 || /[¶\f]/.test(raw.slice(toks[k].end, toks[k + 1].idx));
        if (!endOfLine) continue;
        const key = norm(raw.slice(toks[s0].idx, toks[k].end)), pg = realPages ? toks[s0].pdf : Math.floor(s0 / PAGE) + 1;
        if (key && titles.some(t => t.key === key && Math.abs(t.page - pg) <= 1)) for (let j = s0; j <= k; j++) titleTok[j] = 1;
        s0 = k + 1;
      }
    }
  }
  const structure: StructureReading = {
    frontSections, backSections, chapterSource, body, proseShare: proseShare.map(v => Math.round(v * 100) / 100),
    frontMatter: body ? Array.from({ length: body[0] - 1 }, (_, i) => i + 1) : [],
    backMatter:  body ? Array.from({ length: NP - body[1] }, (_, i) => body![1] + 1 + i) : [],
    headings: headings.slice(0, 60),
  };

  lap('3 calendar events month  number/year and the yea');
  // ── 3. calendar events (month + number/year) and the year axis ───────────────
  const monthSet = new Set(L.months);
  if (lang === 'en') for (const m of L.months) monthSet.add(m.slice(0, 3));
  const monthEvents: NodesResult['timeAxis']['months'] = [];
  const yearFirstPage: Record<number, number> = {};
  const isYear = (w: string) => /^(1[5-9]|20)\d\d$/.test(w);
  const isDay = (w: string) => /^\d{1,2}$/.test(w) && +w >= 1 && +w <= 31;
  for (let k = 0; k < toks.length; k++) {
    const w = toks[k].w;
    if (isYear(w)) { const y = +w; if (yearFirstPage[y] === undefined) yearFirstPage[y] = page(k); }
    const m = w.toLowerCase();
    if (!monthSet.has(m)) continue;
    const p1 = toks[k - 1]?.w, p2 = toks[k - 2]?.w, n1 = toks[k + 1]?.w, n2 = toks[k + 2]?.w;
    const day = p1 && isDay(p1) ? +p1 : (p1 && L.joiners.has(p1.toLowerCase()) && p2 && isDay(p2) ? +p2 : (n1 && isDay(n1) ? +n1 : null));
    const year = n1 && isYear(n1) ? +n1 : (n1 && L.joiners.has(n1.toLowerCase()) && n2 && isYear(n2) ? +n2 : (n2 && isDay(n1 ?? '') && isYear(n2) ? +n2 : null));
    if (day || year) monthEvents.push({ month: m, day, year, page: page(k) });
  }

  lap('4 nodes  capital runs');
  // ── 4. nodes = capital runs ───────────────────────────────────────────────────
  const midCap = new Map<string, number>();
  toks.forEach((t, k) => { if (isCap(t.w) && !sentStart(k) && !t.par) midCap.set(t.w, (midCap.get(t.w) ?? 0) + 1); });
  // A name is capitalised wherever it stands. A capitalised word whose lower-case twin is as frequent as the capital one ("One day", "Even then",
  // "Because") only opens sentences: the work itself shows it is not a name. All-caps cues (CHICO) follow their own convention and are exempt.
  const capTok = new Map<string, number>(), lowTok = new Map<string, number>();
  for (let k = 0; k < toks.length; k++) { if (titleTok[k] || !inBody(k)) continue; const w = toks[k].w; if (isCap(w)) capTok.set(w, (capTok.get(w) ?? 0) + 1); else lowTok.set(w.toLowerCase(), (lowTok.get(w.toLowerCase()) ?? 0) + 1); }
  const consistency = (name: string) => { if (name.includes(' ')) return 1; const cap = capTok.get(name) ?? 0, low = lowTok.get(name.toLowerCase()) ?? 0; return cap + low ? cap / (cap + low) : 1; };
  const named = new Map<string, Occ[]>();
  for (let k = 0; k < toks.length; k++) {
    const w = toks[k].w;
    if (titleTok[k] || !inBody(k) || !isCap(w) || toks[k].slug || (sentStart(k) && !isAllCaps(w) && consistency(w) < 0.5 && (capTok.get(w) ?? 0) + (lowTok.get(w.toLowerCase()) ?? 0) >= 6) || stopSet.has(w.toLowerCase()) || monthSet.has(w.toLowerCase())) continue;
    const caps = isAllCaps(w);
    if (caps) { if (!alone(k) && !((midCap.get(w) ?? 0) >= 2)) continue; if (!alone(k) && (lowTok.get(w.toLowerCase()) ?? 0) >= 2) continue; }       // shouted in the middle of prose and written in lower case elsewhere («NAVE», «FORMA») is emphasis, not a name
    else if (!caseless && sentStart(k) && !((midCap.get(w) ?? 0) >= 3) && !abbrTok[k]) continue;
    let j = k; const run = [w];
    while (j + 1 < toks.length) {
      const n = toks[j + 1].w;
      if (!caps && !caseless && glue(j, j + 1) && isCap(n) && !stopSet.has(n.toLowerCase()) && !monthSet.has(n.toLowerCase())) { run.push(n); j++; }
      else if (!caps && !caseless && glue(j, j + 1) && L.joiners.has(n.toLowerCase()) && j + 2 < toks.length && isCap(toks[j + 2].w)) { run.push(n, toks[j + 2].w); j += 2; }
      else break;
    }
    let name = run.join(' '); { const parts: string[] = []; for (let q = k; q <= j; q++) parts.push(toks[q].w + (abbrTok[q] === 1 ? '.' : '')); name = parts.join(' '); }
    if (run.length === 1 && abbrTok[k] === 1) continue;
    (named.get(name) ?? named.set(name, []).get(name)!).push({ pg: page(k), k });
    k = j;
  }
  const notNames: string[] = [];
  for (const name of [...named.keys()]) { if (name.includes(' ') || isAllCaps(name)) continue; const cap = capTok.get(name) ?? 0, low = lowTok.get(name.toLowerCase()) ?? 0; if (cap + low >= 6 && cap / (cap + low) < 0.5) { named.delete(name); notNames.push(name); } }
  // a single word folds into the multiword name that dominates it ("Jobs" ⊂ "Steve Jobs")
  const byWord = new Map<string, string[]>();
  for (const n of named.keys()) if (n.includes(' ')) for (const p of new Set(n.split(' '))) (byWord.get(p) ?? byWord.set(p, []).get(p)!).push(n);
  const fusions: string[] = [];
  const aliasesOf = new Map<string, string[]>();
  // Alphabets without capitals glue small particles to the front of a word (Arabic لـ, و, ب; Hebrew ל, ב). A particle is learned when the same one is found in front of two or more different
  // names; a name wearing it is that name, not a second one.
  if (caseless) { const ns = [...named.keys()].filter(n => !n.includes(' ') && !CJK_LIKE.test(n)), pre = new Map<string, Set<string>>(), pairs: [string, string, string][] = [];
    for (const t of ns) for (const u of ns) { const d = t.length - u.length; if (t !== u && d >= 1 && d <= 2 && u.length >= 3 && t.endsWith(u)) { const p = t.slice(0, d); (pre.get(p) ?? pre.set(p, new Set()).get(p)!).add(u); pairs.push([t, u, p]); } }
    for (const [t, u, p] of pairs) if ((pre.get(p)?.size ?? 0) >= 2 && named.has(t) && named.has(u) && (named.get(t)!.length <= named.get(u)!.length * 1.5)) { named.get(u)!.push(...named.get(t)!); named.delete(t); aliasesOf.set(u, [...(aliasesOf.get(u) ?? []), t]); } }
  // two passes: folding a first name (Steve) into its full name raises that name's weight, which can then settle who the bare surname (Jobs) is
  for (const s of [...named.keys(), ...named.keys()]) {
    if (s.includes(' ') || !named.has(s)) continue;
    const multi = byWord.get(s); if (!multi) continue;
    const tot = multi.reduce((a, n) => a + named.get(n)!.length, 0); if (tot < 3) continue;
    multi.sort((a, b) => named.get(b)!.length - named.get(a)!.length);
    const best = multi[0];
    const second = multi[1] ? named.get(multi[1])!.length : 0;
    if (named.get(best)!.length / tot >= 0.7 || (named.get(best)!.length >= 3 * second && named.get(best)!.length >= 5)) {      // dominates the other bearers of the same word, or leads them clearly (Steve Jobs 58 vs Paul Jobs 13)
      named.get(best)!.push(...named.get(s)!); named.delete(s);
      (aliasesOf.get(best) ?? aliasesOf.set(best, []).get(best)!).push(s);
      fusions.push(`${s} → ${best}`);
    }
  }

  lap('5 catalogue EVERY word weight  rarity at page le');
  // ── 5. catalogue EVERY word; weight = rarity at page level ───────────────────
  const occL = new Map<string, Occ[]>(), pgset = new Map<string, Set<number>>();
  toks.forEach((t, k) => {
    const w = t.w.toLowerCase();
    if (titleTok[k] || !inBody(k) || wl(w) < 3 || stopSet.has(w) || /\d/.test(w)) return;
    (occL.get(w) ?? occL.set(w, []).get(w)!).push({ pg: page(k), k });
    (pgset.get(w) ?? pgset.set(w, new Set()).get(w)!).add(page(k));
  });
  const wt = (c: number, p: number) => c * Math.log(1 + NP / p);
  // Rarity of a word in the page it stands on. A work of a few pages has too few pages to tell rare from common by page alone, so the pages count as one and the word is weighed by how often it occurs in the whole work.
  const idf = (w: string) => NP < 8 ? Math.log((toks.length + 1) / (1 + (occL.get(w)?.length ?? 0))) : Math.log((NP + 1) / (1 + (pgset.get(w)?.size ?? 0)));

  lap('5b every sentence is a solar system');
  // ── 5b. every sentence is a solar system: how many word-sets, which is the most exotic, how far apart ──
  const idfs = [...pgset.keys()].map(idf).sort((a, b) => a - b);
  const highIdf = idfs.length ? idfs[Math.floor(idfs.length * 0.75)] : 0;
  const sentRows: { s: number; e: number; words: number; max: number; ex: string[]; gap: number | null }[] = [];
  const sentOf = new Int32Array(toks.length).fill(-1);
  {
    let s0 = 0;
    for (let k = 0; k < toks.length; k++) {
      const last = k === toks.length - 1;
      const gapTxt = last ? '.' : raw.slice(toks[k].end, toks[k + 1].idx);
      const abbr = abbrTok[k] === 1;
      if (!last && !(/[.!?…。！？｡؟۔।॥]/.test(gapTxt) && !abbr)) continue;
      if (inBody(s0) && !titleTok[s0]) {
        let words = 0; const ex: { w: string; k: number }[] = []; const seenEx = new Set<string>(); let max = 0;
        for (let j = s0; j <= k; j++) {
          const w = toks[j].w.toLowerCase(); if (wl(w) < 3 || stopSet.has(w) || /\d/.test(w)) continue;
          words++; const v = idf(w); if (v >= highIdf) { ex.push({ w, k: j }); if (!seenEx.has(w)) { seenEx.add(w); max += v; } }   // exoticity = summed rarity of its exotic words
        }
        if (words >= 2) {
          let gap: number | null = null;
          if (ex.length >= 2) { let g = 0; for (let i = 1; i < ex.length; i++) g += ex[i].k - ex[i - 1].k; gap = Math.round((g / (ex.length - 1)) * 10) / 10; }
          sentRows.push({ s: s0, e: k, words, max, ex: [...new Set(ex.map(x => x.w))].slice(0, 5), gap });
          for (let j = s0; j <= k; j++) sentOf[j] = sentRows.length - 1;
        }
      }
      s0 = k + 1;
    }
  }
  // class 1 = no exotic word at all; classes 2–5 = quartiles of the sentences that have some
  lap('5c the vocabulary laid out in space');
  // ── 5c. the vocabulary laid out in space: words that share a solar system sit close together (an embedding) ──
  const seqs: string[][] = sentRows.map(r => { const out: string[] = []; for (let j = r.s; j <= r.e; j++) { const w = toks[j].w.toLowerCase(); if (wl(w) >= 3 && !stopSet.has(w) && !/\d/.test(w)) out.push(w); } return out; });
  const emb = buildEmbedding(seqs);
  // Charge travels through the solar system: a word nobody listed ("espada", "rodaba") takes the charge of the words it stands among.
  const axis = (seedOf: (w: string) => number) => {
    const seeds = [...emb.vec.keys()].filter(w => seedOf(w) > 0); const c = emb.centroid(seeds);
    if (!c || seeds.length < 3) return null;
    const raw = new Map<string, number>(); let m = 0; for (const w of emb.vec.keys()) { const v = emb.simToVec(w, c); raw.set(w, v); m += v; }
    m /= raw.size; let sd = 0; for (const v of raw.values()) sd += (v - m) ** 2; sd = Math.sqrt(sd / raw.size) || 1;
    return (w: string) => ((raw.get(w) ?? m) - m) / sd;
  };
  const charge = new Map<string, { valence: number; arousal: number }>(); for (const w of emb.vec.keys()) charge.set(w, wordCharge(w));
  const posAxis = axis(w => (charge.get(w)?.valence ?? 0) > 0 ? 1 : 0), negAxis = axis(w => (charge.get(w)?.valence ?? 0) < 0 ? 1 : 0), aroAxis = axis(w => charge.get(w)?.arousal ?? 0);
  // The lexicon grows through the solar systems: a word that stands among dark words, again and again, is dark too — at half weight.
  const extV = new Map<string, number>(), extA = new Map<string, number>();
  for (const [w, c] of charge) {
    const lean = posAxis && negAxis ? (posAxis(w) - negAxis(w)) / 2 : 0;           // which pole the words around it lean to
    if (c.valence) extV.set(w, (c.valence > 0 && lean <= -1.0) || (c.valence < 0 && lean >= 1.0) ? 0 : c.valence);   // a listed word whose whole neighbourhood says the opposite ("salvaje") is not charged
    else if (lean >= 1.0) extV.set(w, 0.5); else if (lean <= -1.0) extV.set(w, -0.5);
    if (c.arousal) extA.set(w, 1); else if (aroAxis && aroAxis(w) >= 1.5) extA.set(w, 0.5);
  }
  // The vocabulary cut into semantic FIELDS; each field's charge is read from the charged words that live inside it.
  const { fields: semFields, fieldOf } = clusterVocabulary(emb, Math.max(8, Math.min(24, Math.round(emb.vec.size / 90))));
  const fieldValence = semFields.map(f => { let p = 0, n = 0; for (const w of f.members) { const v = extV.get(w) ?? 0; if (v > 0) p += v; else if (v < 0) n -= v; } return p + n >= 3 ? (p - n) / (p + n) : 0; });
  const sentSorted = sentRows.map(r => r.max).filter(v => v > 0).sort((a, b) => a - b);
  const q = (f: number) => sentSorted.length ? sentSorted[Math.min(sentSorted.length - 1, Math.floor(sentSorted.length * f))] : 0;
  const cuts = [q(0.25), q(0.5), q(0.75)];
  const classes = [0, 0, 0, 0, 0]; const pageSum = new Array<number>(NP).fill(0), pageCnt = new Array<number>(NP).fill(0);
  for (const r of sentRows) { classes[r.max <= 0 ? 0 : 1 + cuts.filter(c => r.max > c).length]++; const p = page(r.s) - 1; pageSum[p] += r.max; pageCnt[p]++; }
  const sentences: SentenceReading = {
    total: sentRows.length, classes,
    perPage: pageSum.map((v, i) => pageCnt[i] ? Math.round((v / pageCnt[i]) * 100) / 100 : 0),
    top: [...sentRows].sort((a, b) => (b.max + b.ex.length * 0.01) - (a.max + a.ex.length * 0.01)).slice(0, 12).map(r => ({
      page: page(r.s), text: raw.slice(toks[r.s].idx, toks[r.e].end).replace(/[¶\f]/g, ' ').replace(/\s+/g, ' ').slice(0, 170),
      words: r.words, exotic: r.ex, score: Math.round(r.max * 100) / 100, gap: r.gap, scales: null,
    })),
  };

  const core80 = (occ: Occ[]): [number, number] => {
    const s = occ.map(o => o.pg).sort((a, b) => a - b); const need = Math.max(1, Math.ceil(s.length * 0.8));
    let bi = 0, bw = Infinity;
    for (let a = 0; a + need - 1 < s.length; a++) { const w = s[a + need - 1] - s[a]; if (w < bw) { bw = w; bi = a; } }
    return [s[bi], s[bi + need - 1]];
  };
  const density = (occ: Occ[]) => {
    const bins = Math.min(NP, BINS_MAX) || 1, b = new Array<number>(bins).fill(0);
    for (const o of occ) b[Math.min(bins - 1, Math.floor((o.pg - 1) / NP * bins))]++;
    return b;
  };
  const bagOf = (e: Ent) => {
    const own = new Set(e.name.toLowerCase().split(/[ =]+/));
    const bag = new Map<string, number>();
    for (const o of e.occ) for (let d = -WINDOW; d <= WINDOW; d++) {
      const t = toks[o.k + d]; if (!t || d === 0 || titleTok[o.k + d] || (sentOf[o.k] >= 0 && sentOf[o.k + d] !== sentOf[o.k])) continue;   // the solar system lives between two full stops
      const w = t.w.toLowerCase();
      if (own.has(w) || stopSet.has(w) || wl(w) < 3) continue;
      bag.set(w, (bag.get(w) ?? 0) + 1);
    }
    return bag;
  };

  // the threshold follows the number of layers: few layers → fine grain, many → coarse
  const MIN_N = Math.max(1, Math.ceil(NP / 80));
  const MIN_LEX = Math.max(2, Math.round(NP / 25));
  // Structure is not story: a word that lives almost only on short isolated lines and never speaks ("CHAPTER", "PART", "EPILOGUE") is
  // the book's own scaffolding. Inside a book the context says so; it is never a name.
  const shortLine = new Uint8Array(toks.length);
  { let s0 = 0; for (let k = 0; k < toks.length; k++) { if (k === toks.length - 1 || /[¶\f]/.test(raw.slice(toks[k].end, toks[k + 1].idx))) { if (k - s0 + 1 <= 8) for (let j = s0; j <= k; j++) shortLine[j] = 1; s0 = k + 1; } } }
  const structuralWords: string[] = [];
  const ents: Ent[] = [...named].map(([name, occ]) => ({ name, aliases: aliasesOf.get(name) ?? [], occ, lex: false })).filter(e => e.occ.length >= MIN_N).filter(e => {
    if (e.occ.length < 3) return true;
    const inShort = e.occ.filter(o => shortLine[o.k]).length / e.occ.length, speaks = e.occ.filter(o => tmode[o.k] === 1).length / e.occ.length;
    if (inShort >= 0.7 && speaks < 0.2) { structuralWords.push(e.name); return false; }
    return true;
  });

  lap('6 what each node IS');
  // ── 6. what each node IS: compare its WHOLE solar system ─────────────────────
  const storyStart = slugs.length ? slugs[0].a : 0;
  const lastK = toks.length - 6;
  for (const e of ents) {
    e.bag = bagOf(e);
    let ch = 0, pl = 0;
    for (const [w, c] of e.bag) { if (L.personCues.has(w) || L.speech.has(w)) ch += c; if (L.placeCues.has(w)) pl += c; }
    pl += e.occ.filter(o => L.placePreps.has(lw(o.k - 1))).length * 1.5;
    for (const o of e.occ) if (isAllCaps(toks[o.k].w) && alone(o.k)) ch += 4;       // a screenplay cue speaks
    for (const o of e.occ) { const m = tmode[o.k]; if (m === 1) ch += 0.25; else if (m === 2) ch += 1.5; }   // inside speech (light: names are spoken ABOUT too) / an action tag
    e.ch = ch / e.occ.length; e.pl = pl / e.occ.length;
    e.kind = ch >= pl ? 'character' : 'place';
    if (e.occ.length <= 3 && e.occ.every(o => o.k >= lastK)) e.kind = 'end-mark';
    else if (slugs.length && e.occ.every(o => toks[o.k].idx < storyStart)) e.kind = 'paratext';
  }

  lap('7 paratext lists');
  // ── 7. paratext lists: bare capitalised words, one per line, before/outside the story ──
  const blocks: string[][] = [];
  { let cur: string[] = [];
    for (const l of pdfPages.join('\n').split('\n').map(x => x.trim())) {
      if (/^\p{Lu}[\p{L}]+$/u.test(l)) cur.push(l);
      else if (l === '') continue;
      else { if (cur.length >= 3) blocks.push(cur); cur = []; }
    }
    if (cur.length >= 3) blocks.push(cur); }
  const countWord = (w: string) => { let n = 0; for (const t of toks) if (t.w === w) n++; return n; };
  const paratext = blocks.map(items => ({ items, appearancesInWork: Object.fromEntries(items.map(w => [w, countWord(w)])) }));
  const inList = new Set(blocks.flat());
  for (const e of ents) if (inList.has(e.name) && e.occ.length <= 2 && e.kind !== 'end-mark') e.kind = 'paratext';

  // ── 8. words that behave as entities (bestia, rey, asesor…) join the candidates ──
  const lexEnts: Ent[] = [...occL].filter(([w, o]) => o.length >= MIN_LEX && !L.verbish.test(w) && !named.has(w[0].toUpperCase() + w.slice(1)))
    .map(([w, o]) => ({ name: w, aliases: [], occ: o, lex: true }));
  const wCache = new Map<Ent, number>();
  const weightOf = (e: Ent) => { let v = wCache.get(e); if (v === undefined) { v = wt(e.occ.length, pgset.get(e.name)?.size ?? new Set(e.occ.map(o => o.pg)).size); wCache.set(e, v); } return v; };
  lexEnts.sort((a, b) => weightOf(b) - weightOf(a));
  const lexRank = new Map(lexEnts.map((e, i) => [e, i]));

  const chars = ents.filter(e => e.kind === 'character');
  const roleSet = new Set(L.roleWords);
  const roleEnts = lexEnts.filter(e => roleSet.has(e.name) || (L.entityWords.has(e.name) && (lexRank.get(e) ?? 99) < 60));
  const cand: Ent[] = [...chars, ...roleEnts.filter(e => !L.address.has(e.name) || roleSet.has(e.name))];       // a form of address that is also a role («majestad») may be the same person as the king
  cand.forEach(c => { c.bag = c.bag ?? bagOf(c); });

  lap('9 identity');
  // ── 9. identity: mutual-closest solar systems that share the same pages ─────
  const slices = Math.max(1, NP / BINS_MAX);
  const pgSlices = (e: Ent) => new Set(e.occ.map(o => Math.floor((o.pg - 1) / slices)));
  const jac = (a: Ent, b: Ent) => { const A = pgSlices(a), B = pgSlices(b); let i = 0; for (const x of A) if (B.has(x)) i++; return i / (A.size + B.size - i || 1); };
  const pageSetCache = new Map<Ent, Set<number>>();
  const pageSet = (e: Ent) => { let v = pageSetCache.get(e); if (!v) { v = new Set(e.occ.map(o => o.pg)); pageSetCache.set(e, v); } return v; };
  // Closest solar system, and how far it stands out from the rest: a candidate's resemblance to its nearest neighbour must exceed its usual resemblance to
  // the others by two deviations; and the nearest neighbour must hold it among its own closest three (a very common word has many neighbours, so the
  // relation is not required to be exactly mutual).
  const nC = cand.length, cosM: number[][] = Array.from({ length: nC }, () => new Array<number>(nC).fill(0));
  for (let i = 0; i < nC; i++) for (let j = i + 1; j < nC; j++) { const c = cosine(cand[i].bag!, cand[j].bag!); cosM[i][j] = c; cosM[j][i] = c; }
  const stats = cosM.map((row, i) => { const v = row.filter((_, j) => j !== i); const mean = v.reduce((a, b) => a + b, 0) / (v.length || 1), sd = Math.sqrt(v.reduce((a, b) => a + (b - mean) ** 2, 0) / (v.length || 1)); return { mean, sd }; });
  const zOf = (i: number, j: number) => stats[i].sd > 0 ? (cosM[i][j] - stats[i].mean) / stats[i].sd : 0;
  const rankIn = (i: number, j: number) => cosM[i].filter((c, q) => q !== i && c > cosM[i][j]).length;      // 0 = j is the closest to i
  const best = cand.map((_, i) => { let bj = -1, bs = 0; cosM[i].forEach((c, j) => { if (j !== i && c > bs) { bs = c; bj = j; } }); return { j: bj, s: bs, z: bj >= 0 ? zOf(i, bj) : 0 }; });
  const injRefused: string[] = [];
  const keptApart: Injectivity['keptApart'] = [];
  // Injectivity: two different NAMES are never one thing, however close their solar systems and pages. A merge needs a word (rey, monarca) on one side.
  cand.forEach((a, i) => { const j = best[i].j; if (j > i && !a.lex && !cand[j].lex && best[i].s >= 0.4 && best[j].j === i) { const A = pageSet(a), B = pageSet(cand[j]); let sh = 0; for (const x of A) if (B.has(x)) sh++; keptApart.push({ a: a.name, b: cand[j].name, similarity: round2(best[i].s), sharedPages: sh }); } });
  const near = (i: number, j: number) => rankIn(i, j) === 0 && zOf(i, j) >= 2 && rankIn(j, i) <= 2 && zOf(j, i) >= 1.5;
  // Synonyms (rey / majestad / monarca, bestia / monstruo): two words that name the same person REPLACE each other — they live in the same stretches of the work, are each other's nearest word of
  // their kind and almost never stand in the same sentence. A king and a queen, who share scenes and sentences, are not folded however alike their surroundings.
  const sentSet = new Map<Ent, Set<number>>(); const sentsOf = (e: Ent) => { let v = sentSet.get(e); if (!v) { v = new Set(e.occ.map(o => sentOf[o.k]).filter(x => x >= 0)); sentSet.set(e, v); } return v; };
  const lexIdx = cand.map((c, i) => c.lex ? i : -1).filter(i => i >= 0);
  const rankLex = (i: number, j: number) => lexIdx.filter(q => q !== i && q !== j && cosM[i][q] > cosM[i][j]).length;
  const within = (a: Ent, b: Ent) => { const A = pgSlices(a), B = pgSlices(b); const [small, big] = A.size <= B.size ? [A, B] : [B, A]; let n = 0; for (const x of small) if (big.has(x)) n++; return n / (small.size || 1); };       // how much of the rarer word's stretches the commoner one also covers
  const synonym = (i: number, j: number) => { if (!cand[i].lex || !cand[j].lex || cosM[i][j] < 0.2 || within(cand[i], cand[j]) < 0.8 || !(rankLex(i, j) === 0 || rankLex(j, i) === 0)) return false;
    const A = sentsOf(cand[i]), B = sentsOf(cand[j]); let co = 0; for (const x of A) if (B.has(x)) co++; return co / Math.max(1, Math.min(A.size, B.size)) <= 0.1; };
  const mutual = (i: number, j: number) => (cosM[i][j] >= 0.2 && (near(i, j) || near(j, i)) && jac(cand[i], cand[j]) >= 0.6 && (cand[i].lex || cand[j].lex)) || synonym(i, j);
  const idClasses = equivalenceClasses(cand.map((_, i) => i), mutual);              // transitive closure: a~b and b~c make one class
  const dead = new Set<number>();
  const classReasons = new Map<string, string[]>();
  for (const cls of idClasses) {
    if (cls.length < 2) continue;
    const members = cls.map(i => cand[i]).sort((x, y) => y.occ.length - x.occ.length), keep = members[0];
    for (const drop of members.slice(1)) {
      keep.occ = [...keep.occ, ...drop.occ]; mergeBag(keep.bag!, drop.bag!);
      keep.aliases = [...keep.aliases, drop.name, ...drop.aliases];
      fusions.push(`${drop.name} → ${keep.name} (closest solar systems, shared pages)`);
      (classReasons.get(keep.name) ?? classReasons.set(keep.name, []).get(keep.name)!).push(`${drop.name}: closest solar system on the same pages`);
      dead.add(cand.indexOf(drop));
    }
  }
  let live = cand.filter((_, i) => !dead.has(i));

  // A word glued to exactly ONE name is that name: "rey John", "el presidente JEFFERSON". No list of titles is needed — the work itself
  // shows it: the word stands directly before a name (no punctuation between), it never stands before any other, and it is used for that
  // name more often than not. From then on every use of the word, with or without the name beside it, is that name.
  const glued = new Map<string, Map<string, number>>();
  for (const e of ents) for (const o of e.occ) {
    if (o.k === 0) continue;
    const prev = toks[o.k - 1], p = prev.w.toLowerCase();
    if (isCap(prev.w) || stopSet.has(p) || wl(p) < 3 || /\d/.test(p) || L.determiners.has(p) || !glue(o.k - 1, o.k)) continue;
    const m = glued.get(p) ?? glued.set(p, new Map()).get(p)!; m.set(e.name, (m.get(e.name) ?? 0) + 1);
  }
  for (const [word, names] of glued) {
    if (names.size !== 1) continue;
    const [[nm, cnt]] = [...names];
    const uses = occL.get(word)?.length ?? cnt, known = L.titles.has(word);
    if (!known && !(cnt >= 3 && cnt / uses >= 0.5)) continue;                       // a listed title needs one sighting; any other word needs a habit
    const N = live.find(c => c.name === nm); if (!N) continue;
    let T = live.find(c => c.name === word || c.aliases.includes(word));
    if (!T) { const oc = occL.get(word); if (!oc || oc.length < cnt) continue; T = { name: word, aliases: [], occ: oc.map(o => ({ ...o })), lex: true }; T.bag = bagOf(T); }
    if (T === N) continue;
    if (!T.lex) { injRefused.push(`${word} ≡ ${nm} refused: «${word}» already belongs to ${T.name}`); continue; }         // a word maps to ONE entity
    if (!known && cosine(T.bag!, N.bag!) < 0.3) continue;                         // an appositive stands in the name's own solar system ("in the meantime" does not)
    N.occ = [...N.occ, ...T.occ]; mergeBag(N.bag!, T.bag!);
    N.aliases = [...N.aliases, T.name, ...T.aliases];
    fusions.push(`${word} ≡ ${nm} (the only name ever glued to «${word}», ${cnt}×)`);
    classReasons.set(N.name, [...(classReasons.get(N.name) ?? []), ...(classReasons.get(T.name) ?? [])]);
    live = live.filter(c => c !== T);
  }

  wCache.clear();                                                                   // merged entities weigh by their merged pages
  // The identity classes of the work, with the reason for each member
  const equivalence: EquivalenceClass[] = [];
  for (const e of live) {
    const members = [...new Set([e.name, ...e.aliases])];
    if (members.length < 2) continue;
    const reasons: string[] = [];
    for (const m of members.slice(1)) {
      if (e.name.split(' ').includes(m) || e.name.includes(m)) reasons.push(`${m}: contained in the longer name`);
      else if (fusions.some(f => f.startsWith(`${m} ≡`))) reasons.push(`${m}: the only name ever glued to that title`);
      else reasons.push(...(classReasons.get(e.name) ?? []).filter(r => r.startsWith(m + ':')));
    }
    equivalence.push({ representative: e.name, members, reasons: [...new Set(reasons)] });
  }

  lap('10 scene links');
  // ── 10. scene links: who shares pages and a solar system with whom ───────────
  const links: NodeLink[] = [];
  for (let i = 0; i < live.length; i++) for (let j = i + 1; j < live.length; j++) {
    const A = pageSet(live[i]), B = pageSet(live[j]); let sh = 0; for (const x of A) if (B.has(x)) sh++;
    const strength = (sh / (A.size + B.size - sh || 1)) * cosine(live[i].bag!, live[j].bag!);
    if (strength >= 0.04 && sh >= 2 && Math.min(live[i].occ.length, live[j].occ.length) >= 3) links.push({ a: live[i].name, b: live[j].name, strength: Math.round(strength * 100) / 100, sharedPages: sh });
  }
  links.sort((a, b) => b.strength - a.strength);

  lap('11 places and who acts in them');
  // ── 11. places and who acts in them ───────────────────────────────────────────
  const placeEnts = ents.filter(e => e.kind === 'place' && e.occ.length >= 3);
  // is there a mention of this entity within `d` tokens of position k? (sorted positions + binary search, not a scan)
  const ksCache = new Map<Ent, number[]>();
  const sortedKs = (e: Ent) => { let v = ksCache.get(e); if (!v) { v = e.occ.map(o => o.k).sort((a, b) => a - b); ksCache.set(e, v); } return v; };
  const hasNear = (ks: number[], k: number, d: number) => { let lo = 0, hi = ks.length; while (lo < hi) { const m = (lo + hi) >> 1; if (ks[m] < k - d) lo = m + 1; else hi = m; } return lo < ks.length && ks[lo] <= k + d; };
  const places = placeEnts.map(p => {
    const c = new Map<string, number>();
    for (const o of p.occ) for (const r of live) { if (r.lex || r.kind === 'place') continue; if (hasNear(sortedKs(r), o.k, 30)) c.set(r.name, (c.get(r.name) ?? 0) + 1); }
    return { name: p.name, core: core80(p.occ), inhabitants: [...c].sort((a, b) => b[1] - a[1]).slice(0, 5).map(([name, scenes]) => ({ name, scenes })) };
  });

  const orbit = (e: Ent) => [...(e.bag ?? bagOf(e))].map(([w, c]) => [w, c * idf(w)] as const).sort((a, b) => b[1] - a[1]).slice(0, 8).map(x => x[0]);
  lap('11b');
  // ── 11b. the forest: every important node is a tree, with its own branches ──────────────
  const treeSet: Ent[] = [...live.filter(e => !e.lex || e.aliases.length > 0 || roleSet.has(e.name)), ...placeEnts.filter(p => !live.includes(p))]
    .filter(e => e.kind !== 'paratext' && e.kind !== 'end-mark' && e.occ.length >= 3);
  const firstPage = (e: Ent) => Math.min(...e.occ.map(o => o.pg));
  const importance = (e: Ent) => e.occ.length * Math.log(1 + NP / new Set(e.occ.map(o => o.pg)).size);
  const ranked = [...treeSet].sort((a, b) => importance(b) - importance(a));
  const topI = ranked.length ? importance(ranked[0]) : 0;
  const winP = Math.max(1, Math.round(NP * 0.03));
  // roots: the lasting nodes, plus the ones that matter intensely for a few pages (a kingdom in the prologue, a group in one chapter) —
  // a place that lasts ten pages is not "agua": it carries its own words around it, and it deserves its own tree
  const major = ranked.filter(e => importance(e) >= topI * 0.12).slice(0, 8);
  const bursty = ranked.filter(e => !major.includes(e) && e.occ.length >= 8 && (() => { const c = core80(e.occ); return c[1] - c[0] + 1 <= Math.max(3, NP * 0.12); })()).slice(0, 8);
  const rootEnts = [...major, ...bursty];
  const forest: ForestTree[] = rootEnts.map(R => {
    const rp = pageSet(R), rc = core80(R.occ), rf = firstPage(R);
    const branches = treeSet.filter(x => x !== R).map(X => {
      const xp = pageSet(X); let sh = 0; for (const g of xp) if (rp.has(g)) sh++;
      const inside = sh / xp.size, fx = firstPage(X);
      const born = fx >= rf && fx <= rc[1] + winP && rp.has(fx) || (fx >= rf && fx <= rc[1] + winP && [...rp].some(g => Math.abs(g - fx) <= winP));
      return { X, sh, inside, born, fx, strength: (inside + (born ? 0.5 : 0)) * Math.log(1 + X.occ.length) };
    }).filter(b => b.sh >= 2 && (b.inside >= 0.4 || b.born)).sort((a, b) => b.strength - a.strength).slice(0, 10);
    return {
      root: R.name, kind: R.kind ?? 'character', mentions: R.occ.length, first: rf, last: Math.max(...R.occ.map(o => o.pg)), core: rc, orbit: orbit(R).slice(0, 6), rank: 'secondary' as const, generates: [] as string[],
      branches: branches.map(b => ({ name: b.X.name, kind: b.X.kind ?? 'character', first: b.fx, inside: Math.round(b.inside * 100) / 100, born: b.born })),
    };
  });
  const rootNames = new Set(forest.map(f => f.root));
  for (const f of forest) {
    const ent = rootEnts.find(e => e.name === f.root)!;
    f.rank = importance(ent) >= topI * 0.35 ? 'primary' : 'secondary';
    f.generates = f.branches.filter(b => b.born && rootNames.has(b.name)).map(b => b.name);
  }
  const treeRelations: TreeRelation[] = [];
  for (let i = 0; i < forest.length; i++) for (let j = i + 1; j < forest.length; j++) {
    const A = forest[i], B = forest[j];
    const sb = A.branches.map(b => b.name).filter(n => B.branches.some(x => x.name === n));
    const ov = Math.max(0, Math.min(A.core[1], B.core[1]) - Math.max(A.core[0], B.core[0]) + 1);
    const shorter = Math.min(A.core[1] - A.core[0] + 1, B.core[1] - B.core[0] + 1);
    const relation: TreeRelation['relation'] = ov / shorter < 0.15 ? (A.core[1] <= B.core[0] ? 'a hands over to b' : 'b hands over to a')
      : (A.core[0] <= B.core[0] && A.core[1] >= B.core[1]) || (B.core[0] <= A.core[0] && B.core[1] >= A.core[1]) ? 'nested' : 'run together';
    treeRelations.push({ a: A.root, b: B.root, sharedBranches: sb, coreOverlap: ov, relation });
  }
  treeRelations.sort((x, y) => y.sharedBranches.length - x.sharedBranches.length || y.coreOverlap - x.coreOverlap);

  lap('11c');
  // ── 11c. knots: each node is a strand over the work; where strands swap order they cross ──
  const strands = [...treeSet].sort((a, b) => b.occ.length - a.occ.length).slice(0, 12);
  const SL = Math.min(NP, BINS_MAX) || 1;
  const curve = strands.map(e => density(e.occ));
  const pairCross = new Map<string, number>(); const sliceCross = new Array<{ n: Set<string>; c: number }>(Math.max(0, SL - 1));
  for (let t = 0; t < SL - 1; t++) {
    const involved = new Set<string>(); let c = 0;
    for (let i = 0; i < strands.length; i++) for (let j = i + 1; j < strands.length; j++) {
      const a0 = curve[i][t] - curve[j][t], a1 = curve[i][t + 1] - curve[j][t + 1];
      if (curve[i][t] && curve[j][t] && curve[i][t + 1] && curve[j][t + 1] && a0 * a1 < 0) {
        c++; involved.add(strands[i].name); involved.add(strands[j].name);
        const key = strands[i].name + '|' + strands[j].name; pairCross.set(key, (pairCross.get(key) ?? 0) + 1);
      }
    }
    sliceCross[t] = { n: involved, c };
  }
  const toPage = (slice: number) => Math.max(1, Math.round(slice * NP / SL) + 1);
  const wins: KnotReading['windows'] = [];
  { const order = sliceCross.map((v, t) => ({ t, c: (sliceCross[t - 1]?.c ?? 0) + v.c + (sliceCross[t + 1]?.c ?? 0) })).sort((a, b) => b.c - a.c);
    const used = new Set<number>();
    for (const o of order) { if (o.c < 3 || wins.length >= 5) break; if ([-1, 0, 1].some(d => used.has(o.t + d))) continue; used.add(o.t); used.add(o.t - 1); used.add(o.t + 1);
      const nodesIn = new Set<string>(); for (const d of [-1, 0, 1]) sliceCross[o.t + d]?.n.forEach(n => nodesIn.add(n));
      wins.push({ pages: [toPage(Math.max(0, o.t - 1)), toPage(Math.min(SL, o.t + 2))], crossings: o.c, nodes: [...nodesIn] }); } }
  const norm = curve.map(c => { const mx = Math.max(...c) || 1; return c.map(v => v / mx); });
  const closest: KnotReading['closest'] = [];
  for (let i = 0; i < strands.length; i++) for (let j = i + 1; j < strands.length; j++) {
    let d = 0; for (let t = 0; t < SL; t++) d += (norm[i][t] - norm[j][t]) ** 2;
    closest.push({ a: strands[i].name, b: strands[j].name, distance: Math.round(Math.sqrt(d / SL) * 100) / 100 });
  }
  closest.sort((a, b) => a.distance - b.distance);
  const knots: KnotReading = {
    windows: wins.sort((a, b) => a.pages[0] - b.pages[0]),
    pairs: [...pairCross].map(([k, c]) => { const [a, b] = k.split('|'); return { a, b, crossings: c }; }).sort((a, b) => b.crossings - a.crossings).slice(0, 8),
    closest: closest.slice(0, 6),
  };

  lap('12 forms of address');
  // ── 12. forms of address: read the whole scene against every candidate's solar system ──
  const dfc = new Map<string, number>(); live.forEach(c => { for (const w of c.bag!.keys()) dfc.set(w, (dfc.get(w) ?? 0) + 1); });
  const address: AddressReading[] = [];
  // who speaks: the name beside the nearest speech verb ("—Sí, mi señor —dijo Beto")
  const nameTokAt = new Map<number, string>(); for (const e of ents) if (e.kind === 'character') for (const o of e.occ) nameTokAt.set(o.k, e.name);
  const speakerOf = (k0: number): string | null => {
    for (let d = 0; d <= 14; d++) for (const sg of (d === 0 ? [1] : [1, -1])) {
      const j = k0 + sg * d; if (!toks[j] || !L.speech.has(toks[j].w.toLowerCase()) || sentOf[j] !== sentOf[k0]) continue;
      for (const q of [1, 2, 3, -1, -2, -3]) { const nm = nameTokAt.get(j + q); if (nm) return nm; }
    }
    return null;
  };
  toks.forEach((t, k) => {
    const w = t.w.toLowerCase();
    if (!L.address.has(w)) return;
    if (!(L.addressPoss.has(lw(k - 1)) || isCap(t.w))) return;
    const speaker = speakerOf(k);
    const scene = new Set<string>();
    for (let d = -40; d <= 40; d++) { const u = toks[k + d]; if (u && d) scene.add(u.w.toLowerCase()); }
    const sc = live.filter(c => c.name.toLowerCase() !== w && !c.aliases.some(a => a.toLowerCase() === w) && !(speaker && (c.name === speaker || c.aliases.includes(speaker)))).map(c => {
      const sz = Math.sqrt([...c.bag!.values()].reduce((a, b) => a + b, 0)) || 1;
      let s = 0; const hits: string[] = [];
      for (const x of scene) {
        const tf = c.bag!.get(x); if (!tf) continue;
        const dw = Math.log(1 + live.length / (dfc.get(x) ?? 1));
        s += Math.min(tf, 6) * dw / sz; if (tf >= 2 && dw > 0.9) hits.push(x);
      }
      const present = hasNear(sortedKs(c), k, 25);
      if (present) s *= 1.8;
      return { node: c.name, score: Math.round(s * 100) / 100, evidence: hits.slice(0, 3), present };
    }).sort((a, b) => b.score - a.score);
    address.push({ page: page(k), form: (L.addressPoss.has(lw(k - 1)) ? lw(k - 1) + ' ' : '') + t.w, speaker, to: sc.slice(0, 2) });
  });

  lap('13 assemble the public result');
  // ── 13. assemble the public result ───────────────────────────────────────────
  const voiceOf = (e: Ent) => {
    let d = 0, a = 0, n = 0; for (const o of e.occ) { const m = tmode[o.k]; if (m === 1) d++; else if (m === 2) a++; else n++; }
    const t = e.occ.length || 1; const r = (x: number) => Math.round((x / t) * 100) / 100;
    return { dialogue: r(d), action: r(a), narration: r(n) };
  };
  const publicNode = (e: Ent): StoryNode => {
    const pages = new Set(e.occ.map(o => o.pg));
    return {
      name: e.name, aliases: [...new Set(e.aliases)], kind: e.kind ?? 'character',
      evidence: { character: Math.round((e.ch ?? 0) * 100) / 100, place: Math.round((e.pl ?? 0) * 100) / 100 },
      mentions: e.occ.length, pages: pages.size, first: Math.min(...pages), last: Math.max(...pages), nameConsistency: round2(consistency(e.name)), voice: voiceOf(e), core: core80(e.occ), density: density(e.occ), orbit: orbit(e),
    };
  };
  // every named node, plus any common word that absorbed synonyms (rey = monarca)
  // A role word that carries the work («bestia», «monstruo», «asesor») is a character like any other even when no name was found for it: it stands on enough pages to be traced
  const bigRole = (e: Ent) => e.lex && (roleSet.has(e.name) || L.entityWords.has(e.name)) && !L.address.has(e.name) && e.occ.length >= Math.max(10, 3 * MIN_LEX) && new Set(e.occ.map(o => o.pg)).size >= Math.max(4, NP * 0.05);
  const nodeList = [...ents, ...live.filter(e => e.lex && (e.aliases.length > 0 || bigRole(e)))].map(publicNode);
  nodeList.sort((a, b) => b.mentions * Math.log(1 + NP / b.pages) - a.mentions * Math.log(1 + NP / a.pages));
  lap('chapters');
  // ── chapters: each is an island with its own signature (rarity at chapter level) ──
  const nCh = starts.length;
  const chapOf = (e: Ent) => new Set(e.occ.map(o => chapterOfPage(o.pg)));
  const chWords = Array.from({ length: nCh }, () => new Map<string, number>()), chTokens = new Array<number>(nCh).fill(0);
  const wordChapters = new Map<string, Set<number>>();
  toks.forEach((t, k) => {
    if (!inBody(k)) return; const c = chapterOfPage(page(k)); chTokens[c]++;
    const w = t.w.toLowerCase(); if (wl(w) < 4 || stopSet.has(w) || /\d/.test(w)) return;
    chWords[c].set(w, (chWords[c].get(w) ?? 0) + 1); (wordChapters.get(w) ?? wordChapters.set(w, new Set()).get(w)!).add(c);
  });
  const chapterRar = (w: string) => Math.log((nCh + 1) / (1 + (wordChapters.get(w)?.size ?? 0)));
  // What a word IS, read from the frames it stands in: "en la X" (a place), "con la X" (an instrument), after an article (a noun), a verb form.
  const classCache = new Map<string, { cls: ThemeTree['class']; nounShare: number; isAction: boolean }>();
  const classifyWord = (w: string) => {
    const hit = classCache.get(w); if (hit) return hit;
    const occ = occL.get(w) ?? [];
    let place = 0, tool = 0, noun = 0, pre = 0;
    for (const o of occ) {
      if (L.determiners.has(lw(o.k - 1)) || L.determiners.has(lw(o.k - 2))) noun++;
      if (L.preVerb.has(lw(o.k - 1)) || isCap(toks[o.k - 1]?.w ?? '')) pre++;
      for (const d of [1, 2, 3]) { const pw = lw(o.k - d); if (L.placePreps.has(pw)) { place++; break; } if (L.toolPreps.has(pw)) { tool++; break; } }
    }
    const n = occ.length || 1, nounShare = noun / n, hasDet = L.determiners.size > 0;
    const isAction = L.verbish.test(w) && w.length >= 6 && (!hasDet || (nounShare < 0.2 && pre / n >= 0.2));
    const cls: ThemeTree['class'] = isAction ? 'action' : place / n >= 0.25 || L.placeCues.has(w) ? 'place' : tool / n >= 0.15 ? 'object' : 'element';
    const out = { cls, nounShare, isAction }; classCache.set(w, out); return out;
  };
  // characters are not event words; who stands in which sentence
  const charNameWords = new Set<string>([...L.entityWords, ...L.roleWords]);
  for (const e of ents) { for (const part of e.name.toLowerCase().split(' ')) charNameWords.add(part); for (const a of e.aliases) charNameWords.add(a.toLowerCase()); }
  const placeNameSet = new Set(ents.filter(e => e.kind === 'place').map(e => e.name));
  const entSentE = new Map<number, string[]>();
  for (const e of ents) if (e.kind === 'character' || e.kind === 'place') for (const o of e.occ) { const si = sentOf[o.k]; if (si >= 0) { const arr = entSentE.get(si) ?? entSentE.set(si, []).get(si)!; if (!arr.includes(e.name)) arr.push(e.name); } }
  const rareHere = (w: string) => wl(w) >= 4 && !stopSet.has(w) && !/\d/.test(w) && !charNameWords.has(w) && (wordChapters.get(w)?.size ?? 99) <= Math.max(2, Math.round(nCh * 0.12));
  const toneRaw: { v: number; a: number; lex: { valence: number; arousal: number }; ev: number | null }[] = [];
  // one pass: the token range and the sentences of every chapter
  const chRange = Array.from({ length: nCh }, () => ({ lo: -1, hi: -1 })), chSents: number[][] = Array.from({ length: nCh }, () => []);
  for (let k = 0; k < toks.length; k++) { if (!inBody(k)) continue; const c = chapterOfPage(page(k)); if (c < 0 || c >= nCh) continue; if (chRange[c].lo < 0) chRange[c].lo = k; chRange[c].hi = k; }
  sentRows.forEach((r, si) => { const c = chapterOfPage(page(r.s)); if (c >= 0 && c < nCh) chSents[c].push(si); });
  const chapters: ChapterReading[] = starts.map((from, i) => {
    const to = i + 1 < nCh ? starts[i + 1] - 1 : bodyTo;
    const sig = [...chWords[i]].filter(([, c]) => c >= 2).map(([w, c]) => [w, c * chapterRar(w)] as const).sort((a, b) => b[1] - a[1]).slice(0, 6).map(x => x[0]);
    const nodesHere = ents.filter(e => e.kind !== 'paratext' && e.kind !== 'end-mark').map(e => [e.name, e.occ.filter(o => chapterOfPage(o.pg) === i).length] as const)
      .filter(x => x[1] > 0).sort((a, b) => b[1] - a[1]).slice(0, 4).map(x => x[0]);
    const best = chSents[i].map(si => sentRows[si]).reduce<(typeof sentRows)[number] | undefined>((b, r) => (!b || r.max > b.max ? r : b), undefined);
    // the chapter's own text, to read its charge and its recurring term clusters
    const lo = chRange[i].lo, hi = chRange[i].hi;
    const chText = lo >= 0 ? raw.slice(toks[lo].idx, toks[hi].end).replace(/[¶\f]/g, ' ') : '';
    const sc = emb.vec.size ? { valence: 0, arousal: 0, words: 0 } : scoreSection(chText);   // a text too small for an embedding falls back on the lexicon alone
    // A sentence is one event: its words are read TOGETHER. Charged words that stand in the same sentence form one reading —
    // the sentence leans to whichever pole carries more charge, and the opposite words around it are part of that event
    // (a beautiful young woman in a sentence about a kidnapping is the victim, not tenderness).
    let pos = 0, neg = 0, aro = 0, sn = 0;
    if (lo >= 0 && emb.vec.size) for (const r of sentRows) {
      if (page(r.s) < from || page(r.s) > to) continue;
      let net = 0, anyCharged = 0;
      for (let j = r.s; j <= r.e; j++) { const w = toks[j].w.toLowerCase(); sn++; const v = extV.get(w) ?? 0; if (v) { net += v; anyCharged++; } aro += extA.get(w) ?? 0; }
      if (anyCharged) { if (net > 0) pos += net; else if (net < 0) neg -= net; }
    }
    const per1k = (n: number) => sn ? (n / sn) * 1000 : 0, tot = per1k(pos) + per1k(neg);
    const sentenceBalance = tot > 0 ? (per1k(pos) - per1k(neg)) / tot : 0;
    const balance = sentenceBalance;
    const extScore = { valence: Math.round(balance * 100), arousal: tot + per1k(aro) };           // raw, uncapped: it is ranked against the book's own chapters below
    toneRaw.push({ v: extScore.valence, a: extScore.arousal, lex: sc, ev: null });
    // ── THE EVENT CHAIN of this chapter (every chapter, same mechanism): sentence by sentence, who is there, where, and which rare words happen ──
    type Beat = { page: number; actors: string[]; place: string | null; words: string[]; charge: number };
    const beats: Beat[] = []; let lastActors: string[] = [], lastPlace: string | null = null;
    for (let si = 0; si < sentRows.length; si++) {
      const r = sentRows[si], pg = page(r.s); if (pg < from || pg > to) continue;
      const names = entSentE.get(si) ?? [], places = names.filter(n => placeNameSet.has(n)), actors = names.filter(n => !placeNameSet.has(n));
      if (actors.length) lastActors = actors.slice(0, 2); if (places.length) lastPlace = places[0];
      const words: string[] = []; let net = 0;
      for (let j = r.s; j <= r.e; j++) { const w = toks[j].w.toLowerCase(); net += extV.get(w) ?? 0; if (rareHere(w) && !words.includes(w)) words.push(w); }
      if (words.length) beats.push({ page: pg, actors: lastActors, place: lastPlace, words: words.slice(0, 3), charge: net });
    }
    // beats that share the stage and the place are one scene
    const segs: { b: Beat[] }[] = [];
    for (const b of beats) { const last = segs[segs.length - 1]; const lb = last?.b[last.b.length - 1]; if (last && lb && lb.place === b.place && (lb.actors.some(a => b.actors.includes(a)) || (!lb.actors.length && !b.actors.length)) && last.b.length < 8) last.b.push(b); else segs.push({ b: [b] }); }
    while (segs.length > 10) { let bi = 0, bs = Infinity; for (let q = 0; q + 1 < segs.length; q++) { const sz = segs[q].b.length + segs[q + 1].b.length; if (sz < bs) { bs = sz; bi = q; } } segs.splice(bi, 2, { b: [...segs[bi].b, ...segs[bi + 1].b] }); }
    const events: EventSegment[] = segs.map(sg => {
      const words: string[] = []; for (const b of sg.b) for (const w of b.words) if (!words.includes(w)) words.push(w);
      const cnt = new Map<string, number>(); for (const b of sg.b) for (const a of b.actors) cnt.set(a, (cnt.get(a) ?? 0) + 1);
      return { pages: [sg.b[0].page, sg.b[sg.b.length - 1].page] as [number, number], actors: [...cnt].sort((x, y) => y[1] - x[1]).slice(0, 2).map(x => x[0]), place: sg.b[0].place, words: words.slice(0, 8), charge: Math.round(sg.b.reduce((a, b) => a + b.charge, 0) * 10) / 10 };
    });
    // symbolism: which semantic fields the event words live in
    const fcount = new Map<number, number>(); let evWords = 0;
    for (const b of beats) for (const w of b.words) { const f = fieldOf.get(w); evWords++; if (f !== undefined) fcount.set(f, (fcount.get(f) ?? 0) + chapterRar(w)); }
    const ftotal = [...fcount.values()].reduce((a, b) => a + b, 0) || 1;
    const symbols: SymbolField[] = [...fcount].sort((a, b) => b[1] - a[1]).slice(0, 3).map(([f, v]) => ({ label: semFields[f].label, share: Math.round((v / ftotal) * 100) / 100, valence: Math.round(fieldValence[f] * 100) / 100 }));
    // the event words' own charge, each read through the field it lives in when the lexicon does not list it
    let evNum = 0, evDen = 0;
    for (const b of beats) for (const w of b.words) { const own = extV.get(w) ?? 0, f = fieldOf.get(w), fv = f !== undefined ? fieldValence[f] : 0, wt2 = chapterRar(w); evNum += wt2 * (own !== 0 ? own : 0.5 * fv); evDen += wt2; }
    const evBalance = evWords >= 3 && evDen > 0 ? Math.max(-1, Math.min(1, evNum / evDen * 2)) : null;
    // what the chapter is made of
    const mixCount = { action: 0, place: 0, object: 0, element: 0, dialogue: 0 }; let mixN = 0;
    for (let k = lo; lo >= 0 && k <= hi; k++) { if (tmode[k] === 1) mixCount.dialogue++; const w = toks[k].w.toLowerCase(); if (wl(w) < 4 || stopSet.has(w) || !occL.has(w)) continue; mixCount[classifyWord(w).cls]++; mixN++; }
    const mixDen = mixN || 1, mix = { action: round2(mixCount.action / mixDen), place: round2(mixCount.place / mixDen), object: round2(mixCount.object / mixDen), element: round2(mixCount.element / mixDen), dialogue: round2(mixCount.dialogue / Math.max(1, hi - lo + 1)) };
    toneRaw[toneRaw.length - 1].ev = evBalance;
    const clusters = chText.length > 800 ? topicClusters(chText.slice(0, 12000), lang === 'es' ? 'es' : 'en', 2).map(t => t.terms.slice(0, 6)) : [];
    const mark = chapterMarks.find(m => m.page === from);
    return { index: i + 1, title: mark?.title ?? `Chapter ${i + 1}`, pages: [from, to] as [number, number], words: chTokens[i], signature: sig, nodes: nodesHere,
      island: best ? raw.slice(toks[best.s].idx, toks[best.e].end).replace(/[¶\f]/g, ' ').replace(/\s+/g, ' ').slice(0, 170) : null, tension: 0, tone: { valence: 0, arousal: 0, eventBalance: null as number | null, label: 'neutral' as ChapterReading['tone']['label'] }, clusters, themes: [], events, symbols, mix, inferred: inferred.has(from), kind: isPartTitle(mark?.title ?? '') ? 'part' as const : inferred.has(from) && !mark?.title.trim().length ? 'untitled' as const : inferred.has(from) && /^chapter\b/i.test(mark?.title ?? '') ? 'untitled' as const : 'chapter' as const, inferredBy: inferred.get(from) ?? null };
  });
  // Chapter charge: the lexicon's own balance-and-charge formula, over the lexicon EXTENDED through the solar systems.
  { const mn = Math.min(...toneRaw.map(t => t.a)), mx = Math.max(...toneRaw.map(t => t.a)); toneRaw.forEach((t, i) => { chapters[i].tone.valence = t.v; chapters[i].tone.eventBalance = t.ev === null ? null : round2(t.ev); chapters[i].tone.arousal = toneRaw.length > 1 ? Math.round(100 * (t.a - mn) / ((mx - mn) || 1)) : t.lex.arousal; }); }
  // The label is RELATIVE to this book: the lexicon saturates, so what counts is how a chapter sits against the others.
  if (chapters.length >= 4) {
    const vs = chapters.map(c => c.tone.valence), as = chapters.map(c => c.tone.arousal);
    const mean = vs.reduce((x, y) => x + y, 0) / vs.length, sd = Math.sqrt(vs.reduce((x, y) => x + (y - mean) ** 2, 0) / vs.length) || 1;
    const sortedA = [...as].sort((x, y) => x - y), pct = (v: number) => sortedA.filter(x => x <= v).length / sortedA.length;
    for (const c of chapters) {
      const z = (c.tone.valence - mean) / sd, ap = pct(c.tone.arousal);
      c.tone.label = z <= -0.55 ? (ap >= 0.45 ? 'violent / dark' : 'tense') : z >= 0.55 ? 'tender / bright' : ap >= 0.85 ? 'turbulent' : ap <= 0.25 ? 'calm' : 'neutral';
    }
  }
  void chapOf;
  lap('the thematic forest');
  // ── the thematic forest: trees of elements (objects, materials, places, actions), apart from the characters ──
  const chIdx = (pg: number) => chapterOfPage(pg);
  const nChap = Math.max(1, nCh);
  type El = { w: string; occ: Occ[]; cls: ThemeTree['class']; chaps: number[]; score: number; conc: number; present: number };
  const elWords: El[] = [];
  // characters are not elements: their names, aliases and role nouns (rey, bestia…) belong to the character forest
  const charWords = new Set<string>([...L.entityWords, ...L.roleWords]);
  for (const e of ents) { for (const part of e.name.toLowerCase().split(' ')) charWords.add(part); for (const a of e.aliases) charWords.add(a.toLowerCase()); }
  for (const [w, occ] of occL) {
    if (occ.length < Math.max(3, MIN_LEX) || named.has(w[0].toUpperCase() + w.slice(1)) || charWords.has(w) || wl(w) < 4) continue;
    const perCh = new Array<number>(nChap).fill(0); for (const o of occ) perCh[Math.min(nChap - 1, chIdx(o.pg))]++;
    const present = perCh.filter(v => v > 0).length;
    if (nChap >= 6 && present > nChap * 0.85) continue;                                  // everywhere: not a theme, just language
    const { cls, nounShare, isAction } = classifyWord(w); const hasDet = L.determiners.size > 0;
    if (hasDet && !isAction && nounShare < 0.3) continue;                                // not a noun, not an action: language, not an element
    // a theme is CONCENTRATED: its mentions cluster in some chapters. Language spread evenly everywhere has maximum entropy.
    const tot = perCh.reduce((a, b) => a + b, 0); let H = 0; for (const v of perCh) if (v) H -= (v / tot) * Math.log(v / tot);
    const concentration = nChap > 1 ? 1 - H / Math.log(nChap) : 1;
    if (present < 2 && nChap >= 6) continue;
    if (isAction && concentration < 0.5) continue;                                        // an action only counts when it is a moment of the book, not everyday language
    elWords.push({ w, occ, cls, chaps: perCh, conc: concentration, present, score: isAction ? occ.length * concentration : concentration * Math.log(1 + occ.length) });
  }
  elWords.sort((a, b) => b.score - a.score);
  // what is worth a tree: the 3 motifs that run through most of the book (its setting, its body, its weather…), the most CONCENTRATED
  // elements (specific to some chapters), and the actions that mark a moment. Ordinary everyday nouns do not get one.
  const motifsAll = elWords.filter(e => e.cls !== 'action' && e.present >= nChap * 0.6).sort((a, b) => b.occ.length - a.occ.length).slice(0, 10);
  const themesAll = elWords.filter(e => e.cls !== 'action' && e.present < nChap * 0.6 && e.occ.length >= 6).sort((a, b) => b.score - a.score).slice(0, 60);
  const actsAll = elWords.filter(e => e.cls === 'action').sort((a, b) => b.score - a.score).slice(0, 14);
  const elCand = [...new Set([...motifsAll, ...themesAll, ...actsAll, ...elWords.filter(e => e.cls !== 'action').slice(0, 60)])], elIdx = new Map(elCand.map((e, i) => [e.w, i]));
  // which candidate elements share a sentence
  const perSent = new Map<number, number[]>();
  for (let i = 0; i < elCand.length; i++) for (const o of elCand[i].occ) { const si = sentOf[o.k]; if (si < 0) continue; const arr = perSent.get(si) ?? perSent.set(si, []).get(si)!; if (!arr.includes(i)) arr.push(i); }
  const co = new Map<number, number>(); const key = (a: number, b: number) => a < b ? a * 1000 + b : b * 1000 + a;
  for (const arr of perSent.values()) { const a = arr.slice(0, 14); for (let x = 0; x < a.length; x++) for (let y = x + 1; y < a.length; y++) co.set(key(a[x], a[y]), (co.get(key(a[x], a[y])) ?? 0) + 1); }
  // who moves with each tree: characters and places seen in the same sentences
  const entSent = new Map<number, Set<string>>();
  for (const e of ents) if (e.kind === 'character' || e.kind === 'place') for (const o of e.occ) { const si = sentOf[o.k]; if (si >= 0) (entSent.get(si) ?? entSent.set(si, new Set()).get(si)!).add(e.name); }
  const pearson = (a: number[], b: number[]) => { const n = a.length, ma = a.reduce((x, y) => x + y, 0) / n, mb = b.reduce((x, y) => x + y, 0) / n; let d = 0, sa = 0, sb = 0; for (let i = 0; i < n; i++) { d += (a[i] - ma) * (b[i] - mb); sa += (a[i] - ma) ** 2; sb += (b[i] - mb) ** 2; } return d / Math.sqrt(sa * sb || 1); };
  // a tree has ONE root: skip a candidate that is already a branch of an accepted root (it lives in the same sentences) or flows exactly like it
  const rootsT: El[] = [];
  const accept = (list: El[], k: number) => {
    let taken = 0;
    for (const e of list) {
      if (taken >= k) break;
      const ei = elIdx.get(e.w)!;
      const dup = rootsT.some(r => { const ri = elIdx.get(r.w)!; const c = co.get(key(ri, ei)) ?? 0; return c / Math.sqrt(r.occ.length * e.occ.length) >= 0.2 || pearson(r.chaps, e.chaps) >= 0.9; });
      if (!dup) { rootsT.push(e); taken++; }
    }
  };
  accept(motifsAll, 3); accept(themesAll, 9); accept(actsAll, 4);
  const themeForest: ThemeTree[] = rootsT.map(R => {
    const ri = elIdx.get(R.w)!;
    const rootChaps = R.chaps.map(v => v > 0);
    const branches = elCand.map((X, xi) => ({ X, c: co.get(key(ri, xi)) ?? 0 })).filter(b => b.X !== R && b.c >= 2).map(b => ({ ...b, strength: b.c / Math.sqrt(R.occ.length * b.X.occ.length) }))
      .sort((a, b) => b.strength - a.strength).slice(0, 6).map(b => {
        const fx = b.X.chaps.findIndex(v => v > 0), fr = R.chaps.findIndex(v => v > 0);
        return { word: b.X.w, class: b.X.cls, strength: Math.round(b.strength * 100) / 100, born: fx >= fr && rootChaps[fx] === true };
      });
    const presentIdx = R.chaps.map((v, i) => v > 0 ? i + 1 : 0).filter(Boolean);
    const total = R.chaps.reduce((a, b) => a + b, 0) || 1;
    const centroid = R.chaps.reduce((a, v, i) => a + v * (i + 0.5), 0) / total / nChap;
    const share = presentIdx.length / nChap;
    const flow: ThemeTree['flow'] = presentIdx.length <= 3 ? 'burst' : share >= 0.6 ? 'constant motif' : centroid < 0.35 ? 'fades' : centroid > 0.65 ? 'builds' : (presentIdx[presentIdx.length - 1] - presentIdx[0] + 1) > presentIdx.length * 1.8 ? 'recurring' : 'mid-book arc';
    const mx = Math.max(...R.chaps); const peaks = R.chaps.map((v, i) => v === mx && mx > 0 ? i + 1 : 0).filter(Boolean).slice(0, 3);
    const carry = new Map<string, number>();
    for (const o of R.occ) for (const n of entSent.get(sentOf[o.k]) ?? []) carry.set(n, (carry.get(n) ?? 0) + 1);
    return { root: R.w, class: R.cls, mentions: R.occ.length, chapters: presentIdx, share: Math.round(share * 100) / 100, flow, peaks, branches, orbit: emb.neighbors(R.w, 6).map(n => n.word), rank: (motifsAll.includes(R) || themesAll.indexOf(R) < 5 ? 'primary' : 'secondary') as 'primary' | 'secondary', generates: [] as string[], carriers: [...carry].sort((a, b) => b[1] - a[1]).slice(0, 3).map(x => x[0]) };
  });
  { const rn = new Set(themeForest.map(t => t.root)); for (const t of themeForest) t.generates = t.branches.filter(b => b.born && rn.has(b.word)).map(b => b.word); }
  const themeRelations: ThemeRelation[] = [];
  for (let i = 0; i < rootsT.length; i++) for (let j = i + 1; j < rootsT.length; j++) {
    const r = Math.round(pearson(rootsT[i].chaps, rootsT[j].chaps) * 100) / 100;
    const A = themeForest[i], B = themeForest[j];
    const shared = A.branches.map(b => b.word).filter(w => B.branches.some(x => x.word === w));
    themeRelations.push({ a: A.root, b: B.root, sharedBranches: shared, coFlow: r, relation: r >= 0.45 ? 'flow together' : r <= -0.2 ? 'alternate' : 'independent' });
  }
  themeRelations.sort((a, b) => Math.abs(b.coFlow) - Math.abs(a.coFlow));
  for (const c of chapters) c.themes = rootsT.map(R => ({ w: R.w, v: R.chaps[c.index - 1] ?? 0 })).filter(x => x.v > 0).sort((a, b) => b.v - a.v).slice(0, 3).map(x => x.w);
  // Injectivity: every mention belongs to exactly one entity; when two claim the same token the more specific (longer) name keeps it
  const claimed = new Map<number, string>(); let collisions = 0;
  for (const e of [...ents, ...live.filter(x => x.lex)].sort((a, b) => b.name.length - a.name.length)) {
    if (e.kind !== 'character' && e.kind !== 'place' && !e.lex) continue;
    for (const o of e.occ) { const had = claimed.get(o.k); if (had !== undefined && had !== e.name) collisions++; else claimed.set(o.k, e.name); }
  }
  lap('a chain for every word of the work function word');
  // ── a chain for every word of the work (function words included) ──
  let wordIndex: Record<string, WordEntry> = {};
  if (opts.wordIndex !== false) {
    const cw: string[] = [], cp: number[] = [], cc: number[] = [], origK: number[] = [];
    for (let k = 0; k < toks.length; k++) {
      if (!inBody(k) || titleTok[k]) continue;
      cw.push(toks[k].w.toLowerCase()); cp.push(page(k)); cc.push(chapterOfPage(page(k))); origK.push(k);
    }
    wordIndex = buildWordIndex({
      words: cw, pages: cp, chapters: cc, NP, nChapters: nCh,
      isFunction: w => stopSet.has(w) || wl(w) < 3,
      classOf: w => occL.has(w) ? classifyWord(w).cls : 'element',
      rarity: w => (pgset.has(w) ? idf(w) : 1),
      nodeAt: i => claimed.get(origK[i]) ?? null,
    });
  }

  // each top sentence read at three scales: its most exotic word within the page, within the chapter, within the whole work
  for (const t of sentences.top) {
    const ws = [...new Set((t.text.toLowerCase().match(/[\p{L}]{4,}/gu) ?? []).filter(w => !stopSet.has(w) && occL.has(w)))];
    if (!ws.length) continue;
    const bestBy = (f: (w: string) => number) => ws.reduce((a, b) => (f(b) > f(a) ? b : a), ws[0]);
    t.scales = { page: bestBy(w => idf(w)), chapter: bestBy(w => chapterRar(w)), book: bestBy(w => -(occL.get(w)?.length ?? 0)) };
  }
  const wordNodes: WordNode[] = lexEnts.slice(0, 30).map(e => {
    const pages = new Set(e.occ.map(o => o.pg));
    return { word: e.name, mentions: e.occ.length, pages: pages.size, first: Math.min(...pages), last: Math.max(...pages), weight: Math.round(weightOf(e)), scales: { page: Math.round(idf(e.name) * 100) / 100, chapter: Math.round(chapterRar(e.name) * 100) / 100, book: Math.round(Math.log(Math.max(2, toks.length) / e.occ.length) * 100) / 100 }, density: density(e.occ) };
  });
  lap('ROUTES & PROXIMITY');
  // ── ROUTES & PROXIMITY. The identity of each entity is fixed (injective), so how close two of them come can be MEASURED without ever
  //    confusing them: like aircraft that are known to be distinct, what matters is where each one is and how the gap between them moves. ──
  const entityCount = new Set([...claimed.values()]).size;
  const SLn = Math.min(Math.max(NP, 1), BINS_MAX);
  const sliceOfPg = (pg: number) => Math.min(SLn - 1, Math.floor((pg - 1) / Math.max(NP, 1) * SLn));
  const pgOfSlice = (sl: number): [number, number] => [Math.round(sl * NP / SLn) + 1, Math.max(Math.round((sl + 1) * NP / SLn), Math.round(sl * NP / SLn) + 1)];
  // where the story stands at each sentence: the last place named in the chapter so far
  const curPlace: (string | null)[] = new Array(sentRows.length).fill(null);
  { let last: string | null = null, lastCh = -1; sentRows.forEach((r, si) => { const c = chapterOfPage(page(r.s)); if (c !== lastCh) { last = null; lastCh = c; } for (const n of entSentE.get(si) ?? []) if (placeNameSet.has(n)) last = n; curPlace[si] = last; }); }
  type Track = { name: string; kind: 'character' | 'place'; mentions: number; ks: number[][]; vec: (Float32Array | null)[]; places: Map<string, number>[]; present: boolean[] };
  const mkTrack = (name: string, kind: 'character' | 'place', occs: Occ[]): Track => {
    const ks = Array.from({ length: SLn }, () => [] as number[]), vec: (Float32Array | null)[] = new Array(SLn).fill(null), places = Array.from({ length: SLn }, () => new Map<string, number>());
    for (const o of occs) {
      const sl = sliceOfPg(o.pg); ks[sl].push(o.k);
      if (emb.vec.size) {
        let v = vec[sl]; if (!v) { v = new Float32Array(emb.dim); vec[sl] = v; }
        for (let d = -8; d <= 8; d++) { const t = toks[o.k + d]; if (!t || d === 0 || titleTok[o.k + d] || sentOf[o.k + d] !== sentOf[o.k]) continue; const x = emb.vec.get(t.w.toLowerCase()); if (x) for (let q = 0; q < emb.dim; q++) v[q] += x[q]; }
      }
      const si = sentOf[o.k]; if (si >= 0 && kind === 'character' && curPlace[si]) places[sl].set(curPlace[si]!, (places[sl].get(curPlace[si]!) ?? 0) + 1);
    }
    ks.forEach(a => a.sort((x, y) => x - y));
    return { name, kind, mentions: occs.length, ks, vec, places, present: ks.map(a => a.length > 0) };
  };
  const minGap = (a: number[], b: number[]) => { let i = 0, j = 0, best = Infinity; while (i < a.length && j < b.length) { best = Math.min(best, Math.abs(a[i] - b[j])); if (a[i] < b[j]) i++; else j++; } return best; };
  const cosV = (a: Float32Array | null, b: Float32Array | null) => { if (!a || !b) return null; let d = 0, na = 0, nb = 0; for (let q = 0; q < a.length; q++) { d += a[q] * b[q]; na += a[q] * a[q]; nb += b[q] * b[q]; } return d / Math.sqrt(na * nb || 1); };
  const topPlaces = (t: Track) => { const c = new Map<string, number>(); t.places.forEach(m => m.forEach((v, k) => c.set(k, (c.get(k) ?? 0) + v))); return [...c].sort((a, b) => b[1] - a[1]).slice(0, 2).map(x => x[0]); };
  const SCENE = 80;                                              // two mentions this many words apart stand in the same scene
  const pairOf = (kind: RoutePair['kind'], A: Track, B: Track): RoutePair | null => {
    const together: number[] = []; for (let sl = 0; sl < SLn; sl++) if (A.present[sl] && B.present[sl]) together.push(sl);
    const pa = A.present.filter(Boolean).length, pb = B.present.filter(Boolean).length;
    if (!together.length) return null;
    const close = together.filter(sl => minGap(A.ks[sl], B.ks[sl]) <= SCENE);
    const enc: [number, number][] = []; let st = -1, pv = -1000;
    for (const sl of close) { if (sl - pv > 2) { if (st >= 0) enc.push([pgOfSlice(st)[0], pgOfSlice(pv)[1]]); st = sl; } pv = sl; }
    if (st >= 0) enc.push([pgOfSlice(st)[0], pgOfSlice(pv)[1]]);
    let best: { sl: number; w: number } | null = null;
    for (const sl of together) { const w = minGap(A.ks[sl], B.ks[sl]); if (!best || w < best.w) best = { sl, w }; }
    const sol = (sl: number) => { const c = cosV(A.vec[sl], B.vec[sl]); return c === null ? null : 1 - c; };
    const series = together.map(sl => sol(sl)).filter((x): x is number => x !== null);
    const half = Math.floor(series.length / 2), mean = (a: number[]) => a.reduce((x, y) => x + y, 0) / (a.length || 1);
    const trend: RoutePair['trend'] = series.length >= 4 ? (mean(series.slice(half)) - mean(series.slice(0, half)) < -0.05 ? 'converging' : mean(series.slice(half)) - mean(series.slice(0, half)) > 0.05 ? 'diverging' : 'steady') : 'steady';
    const share = together.length / Math.max(1, Math.min(pa, pb));
    const relation: RoutePair['relation'] = share >= 0.85 && Math.max(pa, pb) >= 1.5 * Math.min(pa, pb) ? 'contained' : share >= 0.6 && enc.length >= 2 ? 'companions' : enc.length >= 1 ? 'crossing' : 'apart';
    const pl = topPlaces(A).filter(x => topPlaces(B).includes(x));
    return { kind, a: A.name, b: B.name, together: together.length, encounters: enc.slice(0, 6), closest: best ? { pages: pgOfSlice(best.sl), words: best.w, solar: round2(sol(best.sl) ?? 1) } : null, trend, relation, sharedPlaces: pl };
  };
  // nodes: the most mentioned characters and places
  const tracked = live.filter(e => !e.lex || e.aliases.length > 0).filter(e => (e.kind === 'character' || e.kind === 'place') && e.occ.length >= 2).sort((a, b) => b.occ.length - a.occ.length).slice(0, 40);
  const trackOf = new Map<string, Track>(tracked.map(e => [e.name, mkTrack(e.name, e.kind === 'place' ? 'place' : 'character', e.occ)]));
  const routes: Route[] = [...trackOf.values()].filter(t => t.kind === 'character').slice(0, 14).map(t => {
    const legs: RouteLeg[] = []; let cur: RouteLeg | null = null;
    for (let sl = 0; sl < SLn; sl++) {
      const pl = [...t.places[sl]].sort((a, b) => b[1] - a[1])[0]?.[0] ?? null; if (!t.present[sl] || !pl) { continue; }
      const [a, b] = pgOfSlice(sl);
      if (cur && cur.place === pl && a - cur.pages[1] <= 3 * Math.ceil(NP / SLn)) cur.pages[1] = b; else { cur = { pages: [a, b], place: pl }; legs.push(cur); }
    }
    return { name: t.name, kind: 'character' as const, mentions: t.mentions, legs: legs.slice(0, 14) };
  });
  const routePairs: RoutePair[] = [];
  const nodeTracks = [...trackOf.values()];
  for (let i = 0; i < nodeTracks.length; i++) for (let j = i + 1; j < nodeTracks.length; j++) { const p = pairOf('node-node', nodeTracks[i], nodeTracks[j]); if (p) routePairs.push(p); }
  const rank = (x: RoutePair) => x.encounters.length * 3 + x.together;
  const nodePairs = routePairs.splice(0).sort((a, b) => rank(b) - rank(a)).slice(0, 24);
  // trees: the root and its branches walk together
  const entByName = new Map<string, Ent>([...live, ...ents].map(e => [e.name, e]));
  const memberCache = new Map<string, Track | null>();
  const memberTrack = (n: string): Track | null => { if (!memberCache.has(n)) { const e = entByName.get(n); memberCache.set(n, e && !e.lex ? mkTrack(n, e.kind === 'place' ? 'place' : 'character', e.occ) : null); } return memberCache.get(n)!; };
  const combine = (name: string, ts: Track[]): Track => {
    const ks = Array.from({ length: SLn }, (_, sl) => ts.flatMap(t => t.ks[sl]).sort((x, y) => x - y));
    const vec = Array.from({ length: SLn }, (_, sl) => { const parts = ts.map(t => t.vec[sl]).filter((x): x is Float32Array => !!x); if (!parts.length) return null; const v = new Float32Array(emb.dim); for (const p of parts) for (let q = 0; q < emb.dim; q++) v[q] += p[q]; return v; });
    const places = Array.from({ length: SLn }, (_, sl) => { const m = new Map<string, number>(); for (const t of ts) t.places[sl].forEach((v, k) => m.set(k, (m.get(k) ?? 0) + v)); return m; });
    return { name, kind: ts[0]?.kind ?? 'character', mentions: ts.reduce((a, t) => a + t.mentions, 0), ks, vec, places, present: ks.map(a => a.length > 0) };
  };
  const trees = forest.slice(0, 12).map(f => ({ f, members: new Set([f.root, ...f.branches.map(b => b.name)]) }));
  const treePairs: RoutePair[] = [];
  // two trees are compared by what is NOT common to both: their shared members are the same identity in both, and would make them look as close as one thing to itself
  for (let i = 0; i < trees.length; i++) for (let j = i + 1; j < trees.length; j++) {
    const A = [...trees[i].members].filter(n => !trees[j].members.has(n)).map(memberTrack).filter((t): t is Track => !!t);
    const B = [...trees[j].members].filter(n => !trees[i].members.has(n)).map(memberTrack).filter((t): t is Track => !!t);
    if (!A.length || !B.length) continue;
    const p = pairOf('tree-tree', combine(trees[i].f.root, A), combine(trees[j].f.root, B)); if (p) treePairs.push(p);
  }
  const nodeTree: RoutePair[] = [];
  for (const nt of nodeTracks) for (const tr of trees) {
    if (tr.members.has(nt.name)) continue;
    const ms = [...tr.members].map(memberTrack).filter((t): t is Track => !!t && t.name !== nt.name);
    if (!ms.length) continue;
    const p = pairOf('node-tree', nt, combine(tr.f.root, ms)); if (p) nodeTree.push(p);
  }
  routePairs.push(...nodePairs, ...treePairs.sort((a, b) => rank(b) - rank(a)).slice(0, 12), ...nodeTree.sort((a, b) => rank(b) - rank(a)).slice(0, 12));
  lap('WHO LIVES WHERE');
  // ── WHO LIVES WHERE. The engine knows every place and the stretches of the story that happen in it, so it knows which characters carry weight in the
  //    castle, which in the village, which elsewhere — and from that, why certain conversations happen between those who flow into the same place. ──
  const castEnts = live.filter(e => (!e.lex || e.aliases.length > 0) && e.kind === 'character' && e.occ.length >= 2);
  const atPlace = new Map<string, Map<string, number>>(), homeTot = new Map<string, number>();
  for (const e of castEnts) {
    const m = new Map<string, number>();
    for (const o of e.occ) { const si = sentOf[o.k]; const pl = si >= 0 ? curPlace[si] : null; if (pl) m.set(pl, (m.get(pl) ?? 0) + 1); }
    atPlace.set(e.name, m); homeTot.set(e.name, [...m.values()].reduce((a, b) => a + b, 0));
  }
  const homeOf = (name: string, place: string) => { const t = homeTot.get(name) ?? 0; return t ? (atPlace.get(name)?.get(place) ?? 0) / t : 0; };
  const roleOf = (h: number): PlaceCastMember['role'] => h >= 0.5 ? 'native' : h >= 0.2 ? 'regular' : 'visitor';
  const meet = new Map<string, { a: string; b: string; place: string; times: number; dialogue: number; charge: number }>();
  { const castNames = new Set(castEnts.map(e => e.name));
    for (let si = 0; si < sentRows.length; si++) {
      const here = [...new Set([...(entSentE.get(si) ?? []), ...(entSentE.get(si + 1) ?? [])])].filter(n => castNames.has(n)); const pl = curPlace[si];
      if (!pl || here.length < 2) continue;
      const r = sentRows[si]; let sp = 0, ch = 0, nTok = 0;
      for (let j = r.s; j <= r.e; j++) { nTok++; if (tmode[j] === 1) sp++; ch += extV.get(toks[j].w.toLowerCase()) ?? 0; }
      for (let i = 0; i < here.length; i++) for (let j = i + 1; j < here.length; j++) {
        const [a, b] = here[i] < here[j] ? [here[i], here[j]] : [here[j], here[i]], key = `${a}|${b}|${pl}`;
        const m = meet.get(key) ?? meet.set(key, { a, b, place: pl, times: 0, dialogue: 0, charge: 0 }).get(key)!;
        m.times++; if (nTok && sp / nTok >= 0.4) m.dialogue++; m.charge += nTok ? ch / nTok : 0;
      }
    }
  }
  const placeCasts: PlaceCast[] = [...placeNameSet].map(pl => {
    const members = castEnts.map(e => ({ name: e.name, n: atPlace.get(e.name)?.get(pl) ?? 0 })).filter(x => x.n > 0);
    const mass = members.reduce((a, b) => a + b.n, 0); if (!mass) return null;
    const cast = members.sort((a, b) => b.n - a.n).slice(0, 10).map(x => ({ name: x.name, weight: round2(x.n / mass), home: round2(homeOf(x.name, pl)), role: roleOf(homeOf(x.name, pl)) }));
    const meetings: PlaceMeeting[] = [...meet.values()].filter(m => m.place === pl && m.times >= 2).sort((a, b) => b.times - a.times).slice(0, 6).map(m => {
      const na = homeOf(m.a, pl) >= 0.5, nb = homeOf(m.b, pl) >= 0.5;
      return { a: m.a, b: m.b, times: m.times, dialogue: m.dialogue, charge: round2(m.charge / m.times * 10), kind: na && nb ? 'between natives' as const : na || nb ? 'host and guest' as const : 'between guests' as const };
    });
    const pe = ents.find(e => e.name === pl);
    return { place: pl, pages: (pe ? core80(pe.occ) : [0, 0]) as [number, number], mentions: mass, cast, meetings };
  }).filter((x): x is PlaceCast => !!x).sort((a, b) => b.mentions - a.mentions);

  lap('THE SOLAR SYSTEM OF EVERY NODE');
  // ── THE SOLAR SYSTEM OF EVERY NODE ───────────────────────────────────────────────────────────────────────────────────────────────────
  // Every character and place the engine has captured — however few its mentions — is read the same way: the words that stand in its own
  // sentences (between two full stops), placed on their page and in their chapter. Nothing is gated by a minimum count: a word is scored by
  // how much more it stands beside this node than it does in the whole work, with the evidence shrunk toward the work's own rate so that a
  // single sighting cannot shout and a repeated one is heard.
  const nodeList2 = [...new Set([...live.filter(e => !e.lex || e.aliases.length > 0 || bigRole(e)), ...ents])].filter(e => (e.kind === 'character' || e.kind === 'place') && e.occ.length >= 2);
  nodeList2.sort((a, b) => b.occ.length - a.occ.length);
  let Ntot = 0; for (const o of occL.values()) Ntot += o.length;
  const Vtot = occL.size, hasDet2 = L.determiners.size > 0;
  const profile = new Map<string, { counts: Map<string, number>; T: number }>();
  const acrossNodes = new Map<string, number>();
  const windowWords = (k0: number, R: number) => { const out: string[] = []; for (let d = -R; d <= R; d++) { const idx = k0 + d, tk = toks[idx]; if (!tk || d === 0 || !inBody(idx) || titleTok[idx] || sentOf[idx] !== sentOf[k0]) continue; const w = tk.w.toLowerCase(); if (wl(w) < 4 || stopSet.has(w) || charNameWords.has(w) || /\d/.test(w)) continue; out.push(w); } return out; };
  for (const e of nodeList2) {
    const counts = new Map<string, number>(); let T = 0;
    for (const o of e.occ) for (const w of windowWords(o.k, 15)) { counts.set(w, (counts.get(w) ?? 0) + 1); T++; acrossNodes.set(w, (acrossNodes.get(w) ?? 0) + 1); }
    profile.set(e.name, { counts, T });
  }
  const shrunk = (c: number, T: number, w: string) => {
    const n = occL.get(w)?.length ?? 1, a = 0.5;
    const pX = (c + a * (n / Ntot) * Vtot) / (T + a * Vtot), p0 = n / Ntot;     // evidence for this node, pulled toward the work's own rate
    return Math.log(pX / p0) * c;
  };
  const ranked2 = (name: string) => {
    const pr = profile.get(name)!;
    return [...pr.counts].map(([w, c]) => { const cl = classifyWord(w); return { word: w, count: c, score: shrunk(c, pr.T, w), lift: round2((c / (pr.T || 1)) / ((occL.get(w)?.length ?? 1) / Ntot)), exclusivity: round2(c / (acrossNodes.get(w) ?? c)), action: cl.isAction, noun: (!hasDet2 || cl.nounShare >= 0.4) && !L.verbish.test(w) }; })
      .filter(x => x.score > 0).sort((a, b) => b.score - a.score);
  };
  const affinity: Affinity[] = nodeList2.map(e => {
    const r = ranked2(e.name), strip = ({ word, count, lift, exclusivity }: (typeof r)[number]) => ({ word, count, lift, exclusivity });
    return { node: e.name, elements: r.filter(x => !x.action && x.noun).slice(0, 12).map(strip), actions: r.filter(x => x.action).slice(0, 5).map(strip) };
  });

  lap('CANONICAL INJECTION');
  // ── CANONICAL INJECTION: the circle A of each node (its own sentences) sits inside the universe U of its scenes (the sentences around each mention,
  //    on its pages and in its chapters); B = U \ A is what lies outside the circle, and other nodes can hold it as well ──
  const innerOf = new Map(affinity.map(a => [a.node, a.elements.map(x => x.word)]));
  const outerOf = new Map<string, string[]>();
  for (const e of nodeList2) {
    const inner = new Set(innerOf.get(e.name) ?? []), uni = new Map<string, number>();
    for (const o of e.occ) {
      const si = sentOf[o.k]; if (si < 0) continue;
      for (let q = Math.max(0, si - 3); q <= Math.min(sentRows.length - 1, si + 3); q++) {
        if (q === si) continue;
        const r = sentRows[q]; for (let j = r.s; j <= r.e; j++) { if (titleTok[j]) continue; const w = toks[j].w.toLowerCase(); if (wl(w) < 4 || stopSet.has(w) || charNameWords.has(w) || inner.has(w) || /\d/.test(w)) continue; uni.set(w, (uni.get(w) ?? 0) + 1); }
      }
    }
    const rows = [...uni].filter(([w]) => { const cl = classifyWord(w); return !cl.isAction && (!hasDet2 || cl.nounShare >= 0.4) && !L.verbish.test(w); })
      .map(([w, c]) => [w, shrunk(c, [...uni.values()].reduce((a, b) => a + b, 0), w)] as const).filter(x => x[1] > 0).sort((a, b) => b[1] - a[1]);
    outerOf.set(e.name, rows.slice(0, 14).map(x => x[0]));
  }
  const holders = new Map<string, string[]>();
  for (const e of nodeList2) for (const w of [...(innerOf.get(e.name) ?? []), ...(outerOf.get(e.name) ?? [])]) (holders.get(w) ?? holders.set(w, []).get(w)!).push(e.name);
  const circles: Circle[] = nodeList2.map(e => {
    const inner = innerOf.get(e.name) ?? [], outer = outerOf.get(e.name) ?? [];
    const withOf = (w: string) => (holders.get(w) ?? []).filter(n => n !== e.name);
    return { node: e.name, inner, outer, shared: [...inner, ...outer].map(w => ({ word: w, with: withOf(w).slice(0, 4) })).filter(x => x.with.length).slice(0, 10), proper: inner.filter(w => !withOf(w).length) };
  });

  lap('IDENTITY FUNCTION');
  // ── IDENTITY FUNCTION: what surrounds a node at the start against what surrounds it at the end. Equal = F(x)=x; different = transformation; the charge of
  //    what surrounds it says which way. Read in the embedding space, where words that never co-occur can still stand in the same neighbourhood, and
  //    measured against random splits of the SAME mentions (the null: time does not matter): 1 = as stable as that null. Early/late are the node's
  //    first and last chapters; a node inside one chapter is split by its own pages. Every node with two mentions gets an arc; `confidence` says how much it rests on. ──
  const rngS = (seed: number) => { let x = (seed ^ 0x9e3779b9) >>> 0 || 1; return () => { x ^= x << 13; x >>>= 0; x ^= x >>> 17; x ^= x << 5; x >>>= 0; return x / 4294967296; }; };
  const meanVec = new Float32Array(emb.dim); { let n = 0; for (const v of emb.vec.values()) { for (let q = 0; q < emb.dim; q++) meanVec[q] += v[q]; n++; } if (n) for (let q = 0; q < emb.dim; q++) meanVec[q] /= n; }
  const centredVec = (w: string) => { const v = emb.vec.get(w); if (!v) return null; const c = new Float32Array(emb.dim); for (let q = 0; q < emb.dim; q++) c[q] = v[q] - meanVec[q]; return c; };
  const mentionVec = (k0: number) => { const v = new Float32Array(emb.dim); let any = false; for (const w of windowWords(k0, 15)) { const c = centredVec(w); if (c) { for (let q = 0; q < emb.dim; q++) v[q] += c[q]; any = true; } } return any ? v : null; };
  const cosF = (a: Float32Array | null, b: Float32Array | null) => { if (!a || !b) return 0; let d = 0, na = 0, nb = 0; for (let q = 0; q < a.length; q++) { d += a[q] * b[q]; na += a[q] * a[q]; nb += b[q] * b[q]; } return d / Math.sqrt(na * nb || 1); };
  const sumV = (vs: (Float32Array | null)[]) => { const t = new Float32Array(emb.dim); let any = false; for (const v of vs) if (v) { for (let q = 0; q < emb.dim; q++) t[q] += v[q]; any = true; } return any ? t : null; };
  const stabilityV = (early: (Float32Array | null)[], late: (Float32Array | null)[], seed: number) => {
    const obs = cosF(sumV(early), sumV(late)), pool = [...early, ...late], g = rngS(seed), reps = 40; let below = 0, acc = 0;
    for (let r = 0; r < reps; r++) { const sh = [...pool]; for (let i = sh.length - 1; i > 0; i--) { const j = Math.floor(g() * (i + 1)); [sh[i], sh[j]] = [sh[j], sh[i]]; } const c = cosF(sumV(sh.slice(0, early.length)), sumV(sh.slice(early.length))); acc += c; if (c <= obs) below++; }
    // `rank`: the share of random splits that resemble each other LESS than early and late do. High = early and late are as alike as any mixture of the
    // same mentions (nothing changed with time); near 0 = they are more different than almost any random mixture (a real change).
    return { obs, base: acc / reps, rank: below / reps };
  };
  const chargeOf = (ks: number[]) => { let c = 0, n = 0; for (const k0 of ks) for (let d = -15; d <= 15; d++) { const idx = k0 + d, tk = toks[idx]; if (!tk || d === 0 || !inBody(idx) || titleTok[idx] || sentOf[idx] !== sentOf[k0]) continue; c += extV.get(tk.w.toLowerCase()) ?? 0; n++; } return n ? c / n : 0; };
  const bagOfKs = (ks: number[]) => { const m = new Map<string, number>(); for (const k0 of ks) for (const w of windowWords(k0, 15)) m.set(w, (m.get(w) ?? 0) + 1); return m; };
  const arcs: Arc[] = [], arcObs: number[] = [];
  for (const e of nodeList2.slice(0, 60)) {
    const occs = [...e.occ].sort((a, b) => a.k - b.k), chs = [...new Set(occs.map(o => chapterOfPage(o.pg)))].sort((a, b) => a - b);
    let earlyO: Occ[], lateO: Occ[];
    if (chs.length >= 2) { const cut = Math.ceil(chs.length / 2), eSet = new Set(chs.slice(0, cut)); earlyO = occs.filter(o => eSet.has(chapterOfPage(o.pg))); lateO = occs.filter(o => !eSet.has(chapterOfPage(o.pg))); }
    else { const h = Math.floor(occs.length / 2); earlyO = occs.slice(0, h); lateO = occs.slice(occs.length - h); }
    if (!earlyO.length || !lateO.length) continue;
    const st = stabilityV(earlyO.map(o => mentionVec(o.k)), lateO.map(o => mentionVec(o.k)), occs.length * 31 + 7);
    const fe = bagOfKs(earlyO.map(o => o.k)), fl = bagOfKs(lateO.map(o => o.k));
    const te = [...fe.values()].reduce((a, b) => a + b, 0) || 1, tl = [...fl.values()].reduce((a, b) => a + b, 0) || 1;
    const rows = [...new Set([...fe.keys(), ...fl.keys()])].filter(w => { const cl = classifyWord(w); return !cl.isAction && (!hasDet2 || cl.nounShare >= 0.4) && !L.verbish.test(w); })
      .map(w => ({ w, ce: fe.get(w) ?? 0, cl: fl.get(w) ?? 0, e: (fe.get(w) ?? 0) / te, l: (fl.get(w) ?? 0) / tl }));
    const kept = rows.filter(r => r.ce >= 1 && r.cl >= 1).sort((a, b) => Math.min(b.e, b.l) - Math.min(a.e, a.l)).slice(0, 6).map(r => r.w);
    const lost = rows.filter(r => r.ce >= 1 && r.cl === 0).sort((a, b) => b.e - a.e).slice(0, 6).map(r => r.w);
    const gained = rows.filter(r => r.cl >= 1 && r.ce === 0).sort((a, b) => b.l - a.l).slice(0, 6).map(r => r.w);
    const chE = chargeOf(earlyO.map(o => o.k)), chL = chargeOf(lateO.map(o => o.k)), dC = chL - chE;
    arcObs.push(st.obs);
    arcs.push({
      node: e.name, mentions: occs.length, identity: round2(st.rank), kept, lost, gained,
      chargeEarly: round2(chE * 10), chargeLate: round2(chL * 10),
      direction: dC > 0.004 ? 'rises' : dC < -0.004 ? 'falls' : 'steady',
      verdict: st.rank >= 0.2 ? 'identity' : st.rank <= 0.05 ? 'transforms' : 'partial',
      relative: 0, confidence: round2(Math.min(1, Math.min(earlyO.length, lateO.length) / 10)),
      basis: chs.length >= 2 ? `chapters ${chs[0] + 1}–${chs[chs.length - 1] + 1}` : 'pages within one chapter',
    });
  }
  { const sorted = [...arcObs].sort((a, b) => a - b); arcs.forEach((a, i) => { a.relative = round2(sorted.length > 1 ? sorted.filter(x => x < arcObs[i]).length / (sorted.length - 1) : 1); }); }
  // the world: which words keep the same solar system from the first third of the work to the last, and which move most (same embedding, same null)
  const worldIdentity: WorldIdentity = (() => {
    const loPg = body ? body[0] : 1, hiPg = body ? body[1] : NP, span = Math.max(1, hiPg - loPg + 1);
    const freq = [...occL].filter(([w, o]) => o.length >= 8 && !charNameWords.has(w) && wl(w) >= 4 && emb.vec.has(w) && (!hasDet2 || classifyWord(w).nounShare >= 0.3 || classifyWord(w).isAction)).sort((a, b) => b[1].length - a[1].length).slice(0, 300);
    const rows: { word: string; mentions: number; stability: number; obs: number }[] = [];
    for (const [w, occs] of freq) {
      const eV: (Float32Array | null)[] = [], lV: (Float32Array | null)[] = [];
      for (const o of occs) { if (!inBody(o.k) || titleTok[o.k]) continue; const rel = (o.pg - loPg) / span; if (rel < 1 / 3) eV.push(mentionVec(o.k)); else if (rel >= 2 / 3) lV.push(mentionVec(o.k)); }
      if (eV.length < 2 || lV.length < 2) continue;
      const st = stabilityV(eV, lV, w.length * 97 + occs.length); rows.push({ word: w, mentions: occs.length, stability: round2(st.rank), obs: st.obs });
    }
    const invariant = [...rows].sort((a, b) => b.obs - a.obs).slice(0, 10).map(({ word, mentions, stability }) => ({ word, mentions, stability }));
    const drift = [...rows].sort((a, b) => a.obs - b.obs).slice(0, 10).map(({ word, mentions, stability }) => ({ word, mentions, stability }));
    const f = chapters[0], l = chapters[chapters.length - 1];
    const setOf = (c?: ChapterReading) => new Set((c ? [...c.signature, ...c.events.flatMap(e => e.words)] : []));
    const A = setOf(f), B = setOf(l); let inter = 0; for (const w of A) if (B.has(w)) inter++;
    const sim = A.size + B.size ? inter / (A.size + B.size - inter) : 0;
    const placeOf = (c?: ChapterReading) => c?.events.find(e => e.place)?.place ?? null;
    const samePlace = !!placeOf(f) && placeOf(f) === placeOf(l);
    return { invariant, drift, circularity: { similarity: round2(sim), samePlace, verdict: sim >= 0.2 || (samePlace && sim >= 0.1) ? 'circular' : 'open' } };
  })();
  lap('TONE');
  // ── TONE OF CHARACTERS AND BETWEEN THEM → TENSION. Every sentence has a charge from the extended lexicon; a character's tone is the tone of its solar systems, the tone between two is
  //    the tone of the solar systems where they stand together; tension is arousal darkened by what is charged. ──
  const nS = sentRows.length, sVal = new Float64Array(nS), sCh = new Int32Array(nS), sAro = new Float64Array(nS), sW = new Int32Array(nS), sSp = new Float64Array(nS);
  for (let si = 0; si < nS; si++) { const r = sentRows[si]; let net = 0, charged = 0, ar = 0, w0 = 0, sp = 0, len = 0;
    for (let j = r.s; j <= r.e; j++) { len++; if (tmode[j] === 1) sp++; if (titleTok[j] || !inBody(j)) continue; const w = toks[j].w.toLowerCase(); if (stopSet.has(w) || wl(w) < 3) continue; w0++; const v = extV.get(w) ?? 0; if (v) { net += v; charged++; } ar += extA.get(w) ?? 0; }
    sVal[si] = charged ? net / charged : 0; sCh[si] = charged; sW[si] = w0; sAro[si] = w0 >= 3 ? ar / Math.sqrt(w0) : 0; sSp[si] = len ? sp / len : 0; }
  const aSorted = [...sAro].filter((_, i) => sW[i] >= 3).sort((a, b) => a - b), pct = (a: number) => { if (!aSorted.length || a <= 0) return 0; let lo = 0, hi = aSorted.length; while (lo < hi) { const m = (lo + hi) >> 1; if (aSorted[m] < a) lo = m + 1; else hi = m; } return lo / aSorted.length * 100; };
  const sAroN = Float64Array.from(sAro, pct), sTen = Float64Array.from(sAroN, (a, i) => a * (0.5 + 0.5 * (sCh[i] ? (1 - sVal[i]) / 2 : 0.5)));
  const pageOfS = (si: number) => page(sentRows[si].s);
  const nodeSent = new Map<string, number[]>(); for (const e of nodeList2) nodeSent.set(e.name, [...new Set(e.occ.map(o => sentOf[o.k]).filter(x => x >= 0))].sort((a, b) => a - b));
  const toneOfSet = (ss: number[]) => { let net = 0, charged = 0, ar = 0, tn = 0, sp = 0; for (const si of ss) { net += sVal[si] * sCh[si]; charged += sCh[si]; ar += sAroN[si]; tn += sTen[si]; sp += sSp[si] >= 0.3 ? 1 : 0; } const n = Math.max(1, ss.length); return { valence: charged ? Math.round(net / charged * 100) : 0, arousal: Math.round(ar / n), tension: Math.round(tn / n), spoken: round2(sp / n) }; };
  const peakOf = (ss: number[]) => { if (!ss.length) return null; let best = ss[0]; for (const si of ss) if (sTen[si] > sTen[best]) best = si; return pageOfS(best); };
  const trendOf = (ss: number[], f: (si: number) => number): number => { if (ss.length < 6) return 0; const t = Math.floor(ss.length / 3), m = (a: number[]) => a.reduce((x, y) => x + f(y), 0) / (a.length || 1); return m(ss.slice(-t)) - m(ss.slice(0, t)); };
  const tension: ToneMap = { nodes: [], pairs: [], curve: [], peaks: [], chapters: [] };
  for (const e of nodeList2.slice(0, 60)) { const ss = nodeSent.get(e.name) ?? []; if (ss.length < 2) continue; const t = toneOfSet(ss), d = trendOf(ss, si => sVal[si]);
    const byCh = new Map<number, number[]>(); for (const si of ss) { const c = chapterOfPage(pageOfS(si)) + 1; (byCh.get(c) ?? byCh.set(c, []).get(c)!).push(si); }
    tension.nodes.push({ node: e.name, kind: e.kind as NodeKind, sentences: ss.length, ...t, trend: d < -0.08 ? 'darkens' : d > 0.08 ? 'brightens' : 'steady', peak: peakOf(ss), byChapter: [...byCh].filter(([, v]) => v.length >= 2).sort((a, b) => a[0] - b[0]).map(([chapter, v]) => { const x = toneOfSet(v); return { chapter, valence: x.valence, tension: x.tension, sentences: v.length }; }) }); }
  { const names = tension.nodes.slice().sort((a, b) => b.sentences - a.sentences).slice(0, 30).map(x => x.node), pairS = new Map<string, Set<number>>();
    for (let si = 0; si < nS; si++) { const here = (entSentE.get(si) ?? []).filter(n => names.includes(n)); if (!here.length) continue; const next = (entSentE.get(si + 1) ?? []).filter(n => names.includes(n));
      for (const a of here) for (const b of [...here, ...next]) if (a < b) { const k = a + '\u0000' + b; (pairS.get(k) ?? pairS.set(k, new Set()).get(k)!).add(si); } else if (b < a && !here.includes(b)) { const k = b + '\u0000' + a; (pairS.get(k) ?? pairS.set(k, new Set()).get(k)!).add(si); } }
    for (const [k, set] of pairS) { if (set.size < 3) continue; const [a, b] = k.split('\u0000'), ss = [...set].sort((x, y) => x - y), t = toneOfSet(ss), d = trendOf(ss, si => sTen[si]);
      tension.pairs.push({ a, b, sentences: ss.length, pages: [pageOfS(ss[0]), pageOfS(ss[ss.length - 1])], ...t, trend: d > 6 ? 'escalates' : d < -6 ? 'eases' : 'steady', peak: peakOf(ss), bond: t.tension >= 45 && t.valence <= -5 ? 'hostile' : t.tension >= 40 ? 'strained' : t.valence >= 5 ? 'warm' : 'calm' }); }
    tension.pairs.sort((x, y) => y.sentences - x.sentences); tension.pairs = tension.pairs.slice(0, 80); }
  { const perPage = new Map<number, { s: number; n: number }>(); for (let si = 0; si < nS; si++) { if (sW[si] < 3) continue; const pg = pageOfS(si), c = perPage.get(pg) ?? { s: 0, n: 0 }; c.s += sTen[si]; c.n++; perPage.set(pg, c); }
    const pgs = [...perPage.keys()].sort((a, b) => a - b), raw = pgs.map(pg => perPage.get(pg)!.s / perPage.get(pg)!.n), sm = raw.map((_, i) => ((raw[i - 1] ?? raw[i]) + raw[i] + (raw[i + 1] ?? raw[i])) / 3);
    pgs.forEach((pg, i) => tension.curve.push({ page: pg, tension: Math.round(((raw[i - 1] ?? raw[i]) + raw[i] + (raw[i + 1] ?? raw[i])) / 3) }));
    const mu = sm.reduce((a, b) => a + b, 0) / (sm.length || 1), sdv = Math.sqrt(sm.reduce((a, b) => a + (b - mu) ** 2, 0) / (sm.length || 1)) || 1;
    tension.peaks = pgs.filter((_, i) => i > 0 && i < sm.length - 1 && sm[i] >= sm[i - 1] && sm[i] >= sm[i + 1] && sm[i] > mu + sdv).sort((a, b) => sm[pgs.indexOf(b)] - sm[pgs.indexOf(a)]).slice(0, 6).sort((a, b) => a - b);
    const chT = chapters.map(c => { const v = tension.curve.filter(x => x.page >= c.pages[0] && x.page <= c.pages[1]).map(x => x.tension); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : 0; });
    const srt = [...chT].sort((a, b) => a - b); chapters.forEach((c, i) => { c.tension = chT.length > 1 ? Math.round(srt.filter(x => x < chT[i]).length / (srt.length - 1) * 100) : 50; tension.chapters.push({ chapter: c.index, tension: c.tension }); }); }
  lap('LAYERS');
  // ── THE LAYER MAP (4D without projection). Each page is a layer of time. For every sentence (a solar system) the nodes in it are chained: with whom, around which words, touching which
  //    elements of the theme forest. The chain of layers per node is its trajectory; nothing is reduced to fewer dimensions. ──
  const map4d: LayerMap = { layers: [], interactions: [], trajectories: [] };
  { type Cell = { n: number; with: Map<string, number>; around: Map<string, number>; elements: Map<string, number>; v: number; t: number };
    const cells = new Map<number, Map<string, Cell>>();            // page → node → cell
    const rootSet = new Map(themeForest.map(t => [t.root.toLowerCase(), t])), inter = new Map<string, { sent: number; pages: Set<number>; t: ThemeTree }>();
    const kindOfName = new Map(nodeList2.map(e => [e.name, e.kind as NodeKind]));
    const placeAtPage = (name: string, pg: number) => routes.find(r => r.name === name)?.legs.find(l => pg >= l.pages[0] && pg <= l.pages[1])?.place ?? null;
    for (let si = 0; si < sentRows.length; si++) {
      const names = (entSentE.get(si) ?? []).filter(n => kindOfName.has(n)); if (!names.length) continue;
      const r = sentRows[si], pg = page(r.s);
      const els = new Set<string>(); for (let j = r.s; j <= r.e; j++) { const t = rootSet.get(toks[j].w.toLowerCase()); if (t && !titleTok[j]) els.add(t.root.toLowerCase()); }
      const ws = new Set<string>(); for (let j = r.s; j <= r.e; j++) { const w = toks[j].w.toLowerCase(); if (!titleTok[j] && wl(w) >= 3 && !stopSet.has(w) && !/\d/.test(w) && !charNameWords.has(w) && !kindOfName.has(toks[j].w)) ws.add(w); }
      const around = [...ws].sort((x, y) => idf(y) - idf(x)).slice(0, 5);       // what stands in the solar system, the rarest first (common words too: «pistola» on every page is still beside the hand that holds it)
      const row = cells.get(pg) ?? cells.set(pg, new Map()).get(pg)!;
      for (const nm of names) {
        const c = row.get(nm) ?? row.set(nm, { n: 0, with: new Map(), around: new Map(), elements: new Map(), v: 0, t: 0 }).get(nm)!;
        c.n++; c.v += sVal[si]; c.t += sTen[si]; for (const o of names) if (o !== nm) c.with.set(o, (c.with.get(o) ?? 0) + 1);
        for (const w of around) c.around.set(w, (c.around.get(w) ?? 0) + 1);
        for (const el of els) if (el !== nm.toLowerCase()) { c.elements.set(el, (c.elements.get(el) ?? 0) + 1); const key = nm + '\u0000' + el; const it = inter.get(key) ?? inter.set(key, { sent: 0, pages: new Set(), t: rootSet.get(el)! }).get(key)!; it.sent++; it.pages.add(pg); }
      }
    }
    const top = (m: Map<string, number>, k: number) => [...m].sort((a, b) => b[1] - a[1]).slice(0, k).map(x => x[0]);
    for (const pg of [...cells.keys()].sort((a, b) => a - b)) { const row = cells.get(pg)!;
      map4d.layers.push({ page: pg, chapter: chapterOfPage(pg) + 1, nodes: [...row].sort((a, b) => b[1].n - a[1].n).slice(0, 10).map(([name, c]) => ({ name, kind: kindOfName.get(name)!, n: c.n, place: placeAtPage(name, pg), with: top(c.with, 4), around: top(c.around, 5), elements: top(c.elements, 4), tone: { valence: Math.round(c.v / c.n * 100), tension: Math.round(c.t / c.n) } })) }); }
    const perNode = new Map<string, { pg: number; c: Cell }[]>(); for (const [pg, row] of cells) for (const [nm, c] of row) (perNode.get(nm) ?? perNode.set(nm, []).get(nm)!).push({ pg, c });
    for (const [nm, list] of perNode) { list.sort((a, b) => a.pg - b.pg); if (list.length < 2) continue;
      const runs: Trajectory['runs'] = []; for (const x of list) { const l = runs[runs.length - 1]; if (l && x.pg - l.to <= 1) l.to = x.pg; else runs.push({ from: x.pg, to: x.pg, place: placeAtPage(nm, x.pg) }); }
      let el = 0, ne = 0; for (let i = 1; i < list.length; i++) { const A = new Set([...list[i - 1].c.with.keys(), ...list[i - 1].c.elements.keys()]), B = new Set([...list[i].c.with.keys(), ...list[i].c.elements.keys()]); const u = new Set([...A, ...B]); if (!u.size) continue; let sh = 0; for (const w of A) if (B.has(w)) sh++; el += 1 - sh / u.size; ne++; }
      const wm = new Map<string, number>(); for (const x of list) for (const o of x.c.with.keys()) wm.set(o, (wm.get(o) ?? 0) + 1);
      map4d.trajectories.push({ node: nm, kind: kindOfName.get(nm)!, layers: list.length, first: list[0].pg, last: list[list.length - 1].pg, runs: runs.slice(0, 40), elasticity: ne ? round2(el / ne) : 0, mostWith: [...wm].sort((a, b) => b[1] - a[1]).slice(0, 5).map(([name, layers]) => ({ name, layers })) }); }
    map4d.trajectories.sort((a, b) => b.layers - a.layers);
    const byNode = new Map<string, Interaction[]>(); for (const [key, v] of inter) { const [node, element] = key.split('\u0000'); const pgs = [...v.pages].sort((a, b) => a - b); (byNode.get(node) ?? byNode.set(node, []).get(node)!).push({ node, element, class: v.t.class, sentences: v.sent, pages: pgs.slice(0, 12), first: pgs[0], last: pgs[pgs.length - 1] }); }
    for (const list of byNode.values()) map4d.interactions.push(...list.sort((a, b) => b.sentences - a.sentences).slice(0, 8));
  }
  lap('MORPHISMS');
  // ── MORPHISMS. A morphism carries one structure onto another WITHOUT breaking the relations inside it. Three uses here: (1) two chapters whose cast
  //    is different but whose skeleton of relations is the same; (2) the order that the relations impose (who defers to whom, which place holds which,
  //    which element belongs to whom); (3) whether the structure around a theme survives from the first half of the book to the second. ──
  const parallels: SkeletonParallel[] = [];
  { type Sk = { chapter: number; title: string; nodes: string[]; W: number[][] };
    const sks: Sk[] = [];
    for (let ci = 0; ci < nCh; ci++) {
      const cnt = new Map<string, number>();
      for (const si of chSents[ci]) for (const n of entSentE.get(si) ?? []) cnt.set(n, (cnt.get(n) ?? 0) + 1);
      const nodes = [...cnt].sort((a, b) => b[1] - a[1]).slice(0, 5).map(x => x[0]); if (nodes.length < 3) continue;
      const W = nodes.map(() => nodes.map(() => 0));
      for (const si of chSents[ci]) {
        const here = new Set([...(entSentE.get(si) ?? []), ...(entSentE.get(si + 1) ?? [])]);
        for (let a = 0; a < nodes.length; a++) for (let b = a + 1; b < nodes.length; b++) if (here.has(nodes[a]) && here.has(nodes[b])) { W[a][b]++; W[b][a]++; }
      }
      let mx = 0; for (const row of W) for (const v of row) mx = Math.max(mx, v); if (!mx) continue;
      for (const row of W) for (let q = 0; q < row.length; q++) row[q] = row[q] / mx;
      if (W.flat().filter(v => v > 0).length < 4) continue;                               // at least two relations
      sks.push({ chapter: ci, title: chapters[ci].title, nodes, W });
    }
    const perms = (n: number): number[][] => { if (n <= 1) return [[0]]; const out: number[][] = []; const rec = (cur: number[], rest: number[]) => { if (!rest.length) { out.push(cur); return; } for (let i = 0; i < rest.length; i++) rec([...cur, rest[i]], rest.filter((_, j) => j !== i)); }; rec([], Array.from({ length: n }, (_, i) => i)); return out; };
    const permCache = new Map<number, number[][]>();
    for (let i = 0; i < sks.length; i++) for (let j = i + 1; j < sks.length; j++) {
      const A = sks[i], B = sks[j], m = Math.min(A.nodes.length, B.nodes.length);
      if (m < 3) continue;
      const ps = permCache.get(m) ?? permCache.set(m, perms(m)).get(m)!;
      let best = -1, bestMap: number[] = [];
      for (const p of ps) {                                                              // the map of the cast of A onto the cast of B — it must keep the sort of each node (a place goes to a place)
        if (p.some((q, a) => placeNameSet.has(A.nodes[a]) !== placeNameSet.has(B.nodes[q]))) continue;
        let diff = 0, tot = 0;
        for (let a = 0; a < m; a++) for (let b = a + 1; b < m; b++) { const x = A.W[a][b], y = B.W[p[a]][p[b]]; diff += Math.abs(x - y); tot += Math.max(x, y); }
        const sim = tot ? 1 - diff / tot : 0; if (sim > best) { best = sim; bestMap = p; }
      }
      const sa = new Set(A.nodes), sb = new Set(B.nodes); let inter = 0; for (const n of sa) if (sb.has(n)) inter++;
      const overlap = inter / (sa.size + sb.size - inter);
      if (best >= 0.8 && Math.abs(j - i) >= 2) parallels.push({ a: { chapter: A.chapter + 1, title: A.title }, b: { chapter: B.chapter + 1, title: B.title }, similarity: round2(best), castOverlap: round2(overlap), mapping: bestMap.map((q, a) => [A.nodes[a], B.nodes[q]] as [string, string]), kind: overlap <= 0.34 ? 'hidden parallel' : 'echo' });
    }
    parallels.sort((x, y) => (y.similarity * (y.kind === 'hidden parallel' ? 1.2 : 1) * (1 - y.castOverlap * 0.3)) - (x.similarity * (x.kind === 'hidden parallel' ? 1.2 : 1) * (1 - x.castOverlap * 0.3)));
  }
  const canonOf = new Map<string, string>(); for (const c of equivalence) for (const mem of c.members) canonOf.set(mem, c.representative);
  const canon = (n: string) => canonOf.get(n) ?? n;
  // (2a) deference: a form of address (mi señor, your majesty, Dios) goes from the one who speaks to the one it refers to
  // (2a-0) FORMS OF ADDRESS, LEARNED FROM THE BOOK. In dialogue, a chain of words that turns again and again towards the same node, whoever is speaking,
  // is a form of address towards it (a title, a respect form, a nickname). No list of any language is needed: the book shows it by who is always there.
  const learnedForms: Hierarchy['forms'] = [];
  const learnedEdges: { from: string; to: string; w: number }[] = [];
  { const castNames = new Set(castEnts.map(e => e.name));
    type Occ2 = { names: string[]; speaker: string | null };
    const grams = new Map<string, Occ2[]>(); const base = new Map<string, number>(); const narr = new Map<string, number>(); const edged = new Map<string, number>(); const tagCount = new Map<string, number>(); let dlg = 0;
    const cut = /[,;:¡!¿?—–"«»“”()]/;
    const isNameWord = (w: string) => charNameWords.has(w);
    for (let si = 0; si < sentRows.length; si++) {
      const r = sentRows[si]; let sp = 0, len = 0; for (let j = r.s; j <= r.e; j++) { len++; if (tmode[j] === 1) sp++; }
      if (!len) continue;
      const spoken = sp >= 3 || sp / len >= 0.3;
      let speaker: string | null = null;            // the name that follows the last spoken word in its own sentence is the one who says it; the others are spoken to
      if (spoken) { let lastSp = -1; for (let j = r.e; j >= r.s; j--) if (tmode[j] === 1) { lastSp = j; break; } for (let j = lastSp + 1; j <= r.e && speaker === null; j++) { const c = claimed.get(j); if (c && castNames.has(c)) speaker = c; } }
      const names = spoken ? [...new Set([-3, -2, -1, 0, 1, 2, 3].flatMap(d => entSentE.get(si + d) ?? []))].filter(n => castNames.has(n) && n !== speaker) : [];       // the scene around the line, without the speaker
      if (spoken) {            // the word that hugs the edge of the quotation (said, recalled, dijo…) is a speech tag, learned from how the book frames its speech
        let fs = -1, ls = -1; for (let j = r.s; j <= r.e; j++) if (tmode[j] === 1) { if (fs < 0) fs = j; ls = j; }
        for (const j of [fs - 1, ls + 1]) if (j >= r.s && j <= r.e && tmode[j] !== 1 && !claimed.has(j)) { const w = toks[j].w.toLowerCase(); tagCount.set(w, (tagCount.get(w) ?? 0) + 1); }
      }
      if (spoken) { dlg++; for (const n of names) base.set(n, (base.get(n) ?? 0) + 1); }
      const ws: string[] = []; for (let j = r.s; j <= r.e; j++) ws.push(toks[j].w.toLowerCase());
      const seen = new Set<string>();
      for (let n = 2; n <= 3; n++) for (let q = 0; q + n <= ws.length; q++) {
        const g = ws.slice(q, q + n); if (g.some(isNameWord) || g.some(w => /\d/.test(w)) || g.every(w => stopSet.has(w) || wl(w) < 3)) continue;
        const key = g.join(' '); if (seen.has(key)) continue; seen.add(key);
        let inside = true; for (let t = 0; t < n; t++) if (tmode[r.s + q + t] !== 1) { inside = false; break; }       // only what stands inside the quotation is speech
        if (!spoken || !inside) { narr.set(key, (narr.get(key) ?? 0) + 1); continue; }
        const a = r.s + q, b = a + n - 1;
        if ((a > 0 && cut.test(raw.slice(toks[a - 1].end, toks[a].idx))) || (b + 1 < toks.length && cut.test(raw.slice(toks[b].end, toks[b + 1].idx)))) edged.set(key, (edged.get(key) ?? 0) + 1);       // flanked by a comma or a mark: set apart like a vocative
        (grams.get(key) ?? grams.set(key, []).get(key)!).push({ names, speaker });
      }
    }
    const minN = Math.max(5, Math.round(dlg / 500));
    const cands: { form: string; toward: string; n: number; lift: number; occ: Occ2[] }[] = [];
    for (const [form, occ] of grams) {
      if (occ.length < minN || occ.length < 0.8 * (occ.length + (narr.get(form) ?? 0))) continue;       // a form of address lives in speech, not in the narration
      if ((edged.get(form) ?? 0) < 0.6 * occ.length || form.split(' ').some(w => !stopSet.has(w) && (tagCount.get(w) ?? 0) >= Math.max(8, dlg / 200))) continue;
      const presence = new Map<string, number>(); for (const o of occ) for (const nm of o.names) presence.set(nm, (presence.get(nm) ?? 0) + 1);
      const top = [...presence].sort((a, b) => b[1] - a[1])[0]; if (!top) continue;
      const pA = top[1] / occ.length, baseA = (base.get(top[0]) ?? 0) / Math.max(1, dlg), lift = baseA > 0 ? pA / baseA : 0;
      const others = new Set<string>(); for (const o of occ) { if (o.speaker && o.speaker !== top[0]) others.add(o.speaker); for (const nm of o.names) if (nm !== top[0]) others.add(nm); }
      const z = baseA > 0 && baseA < 0.99 ? (pA - baseA) / Math.sqrt(baseA * (1 - baseA) / occ.length) : baseA >= 0.99 && occ.length >= 12 ? 99 : 0;       // when the addressee is in every scene, only a steady chain says anything           // is the addressee there far more often than chance says?
      if (z >= 1.5 && pA >= 0.4 && (others.size >= 2 || occ.length >= 12)) cands.push({ form, toward: top[0], n: occ.length, lift: z, occ });
    }
    // keep the strongest chain of overlapping ones ("mi señor" over "señor ya")
    cands.sort((a, b) => b.n * b.lift - a.n * a.lift);
    const chosen: typeof cands = [];
    for (const c of cands) { if (chosen.length >= 12) break; if (chosen.some(x => x.toward === c.toward && (x.form.includes(c.form) || c.form.includes(x.form)))) continue; chosen.push(c); }
    for (const c of chosen) {
      const speakers = new Map<string, number>();
      for (const o of c.occ) { const others = o.speaker && o.speaker !== c.toward ? [o.speaker] : o.names.filter(nm => nm !== c.toward); for (const x of others) { speakers.set(x, (speakers.get(x) ?? 0) + 1 / others.length); learnedEdges.push({ from: x, to: c.toward, w: 1 / others.length }); } }
      learnedForms.push({ form: c.form, toward: c.toward, times: c.n, speakers: [...speakers].sort((a, b) => b[1] - a[1]).slice(0, 5).map(x => x[0]) });
    }
  }
  const defer = new Map<string, number>();
  for (const e of learnedEdges) { const f = canon(e.from), t = canon(e.to); if (f !== t) defer.set(`${f}>${t}`, (defer.get(`${f}>${t}`) ?? 0) + e.w); }
  for (const a of address) {
    const ref = a.to[0]; if (!ref || ref.score <= 0) continue;
    const refN = canon(ref.node);
    const ci = chapterOfPage(a.page); if (ci < 0 || ci >= nCh) continue;
    const seg = chapters[ci].events.find(ev => a.page >= ev.pages[0] && a.page <= ev.pages[1] && ev.actors.some(x => canon(x) !== refN));
    const speaker = a.speaker ? canon(a.speaker) : seg?.actors.map(canon).find(x => x !== refN); if (!speaker || speaker === refN) continue;      // nobody defers to itself, and an alias is the same node
    const key = `${speaker}>${refN}`; defer.set(key, (defer.get(key) ?? 0) + 1);
  }
  // (2b) precedence: who is named first when two stand in the same sentence (the one who acts, the one the sentence is about)
  const prec = new Map<string, number>();
  { const firstIn = new Map<number, Map<string, number>>();                          // sentence → name → position of its first mention (one pass over all mentions)
    for (const e of castEnts) for (const o of e.occ) { const si = sentOf[o.k]; if (si < 0) continue; const m = firstIn.get(si) ?? firstIn.set(si, new Map()).get(si)!; const had = m.get(e.name); if (had === undefined || o.k < had) m.set(e.name, o.k); }
    for (const m of firstIn.values()) {
      const names = [...m].sort((a, b) => a[1] - b[1]).map(x => x[0]);
      for (let a = 0; a < names.length; a++) for (let b = a + 1; b < names.length; b++) { const k = `${names[a]}>${names[b]}`; prec.set(k, (prec.get(k) ?? 0) + 1); }
    }
  }
  const deferTo = new Map<string, number>(), deferFrom = new Map<string, number>(), precAsym = new Map<string, number>();
  for (const [k, n] of defer) { const [f, t] = k.split('>'); deferTo.set(t, (deferTo.get(t) ?? 0) + n); deferFrom.set(f, (deferFrom.get(f) ?? 0) + n); }
  for (const [k, n] of prec) { const [a, b] = k.split('>'); const back = prec.get(`${b}>${a}`) ?? 0; if (n + back >= 4) precAsym.set(a, (precAsym.get(a) ?? 0) + (n - back) / (n + back) / 2); }
  // rank by pairs, not by totals: A stands above B when B defers to A more than A defers to B (so being addressed often does not cancel against addressing others)
  const above = new Map<string, number>(), notes = new Map<string, string[]>();
  { const names = new Set<string>(); for (const k of defer.keys()) { const [f, t] = k.split('>'); names.add(f); names.add(t); }
    const list = [...names];
    for (let i = 0; i < list.length; i++) for (let j = i + 1; j < list.length; j++) {
      const A = list[i], B = list[j], ab = defer.get(`${A}>${B}`) ?? 0, ba = defer.get(`${B}>${A}`) ?? 0, tot = ab + ba; if (tot < 2) continue;
      const asym = (ba - ab) / tot, w = Math.log(1 + tot);                       // positive: B defers to A, so A is above B
      above.set(A, (above.get(A) ?? 0) + asym * w); above.set(B, (above.get(B) ?? 0) - asym * w);
      if (asym !== 0) { const hi = asym > 0 ? A : B, lo = asym > 0 ? B : A; (notes.get(hi) ?? notes.set(hi, []).get(hi)!).push(`above ${lo} (${Math.max(ab, ba)}:${Math.min(ab, ba)})`); }
    }
  }
  const rankChars = castEnts.map(e => {
    const sc = above.get(e.name) ?? 0, pa = precAsym.get(e.name) ?? 0, dt = deferTo.get(e.name) ?? 0;
    const score = sc + 0.8 * pa;
    const evidence: string[] = [...(notes.get(e.name) ?? []).slice(0, 3)]; if (dt) evidence.push(`addressed with deference ×${dt}`); if (Math.abs(pa) >= 0.3) evidence.push(`${pa > 0 ? 'named before' : 'named after'} the others it shares sentences with`);
    return { node: e.name, kind: 'character' as const, score: round2(score), evidence };
  }).sort((a, b) => b.score - a.score);
  // levels: the top of the hierarchy is whoever the evidence puts clearly above the others; nobody is placed without evidence
  const topScore = Math.max(0, ...rankChars.map(r => r.score));
  const characters: Rank[] = rankChars.slice(0, 30).map(r => ({ ...r, level: r.score > 0 && r.score >= topScore * 0.6 ? 0 : r.score > 0 ? 1 : 2 }));
  const levelOf = (i: number, n: number) => (i < n * 0.2 ? 0 : i < n * 0.5 ? 1 : 2);
  const placeRank = placeCasts.map(pc => ({ node: pc.place, kind: 'place' as const, score: round2(pc.mentions * Math.log(1 + pc.cast.length)), evidence: [`${pc.mentions} character mentions`, `${pc.cast.length} characters`] })).sort((a, b) => b.score - a.score);
  const placeRanks: Rank[] = placeRank.map((r, i, a) => ({ ...r, level: levelOf(i, a.length) }));
  const containment = routePairs.filter(p => p.kind === 'node-node' && p.relation === 'contained' && placeNameSet.has(p.a) && placeNameSet.has(p.b)).map(p => {
    const ta = trackOf.get(p.a)!, tb = trackOf.get(p.b)!, big = ta.mentions >= tb.mentions ? ta : tb, small = big === ta ? tb : ta;
    return { outer: big.name, inner: small.name, share: round2(p.together / Math.max(1, small.present.filter(Boolean).length)) };
  });
  const ownership = affinity.flatMap(a => a.elements.filter(x => x.exclusivity >= 0.6 && x.lift >= 3 && x.count >= 3).map(x => ({ element: x.word, owner: a.node, exclusivity: x.exclusivity, lift: x.lift }))).sort((a, b) => b.exclusivity - a.exclusivity || b.lift - a.lift)
    .filter((x, i, arr) => arr.findIndex(y => y.element === x.element) === i).slice(0, 40);
  const hierarchy: Hierarchy = { forms: learnedForms, deference: [...defer].map(([k, times]) => { const [from, to] = k.split('>'); return { from, to, times }; }).sort((a, b) => b.times - a.times).slice(0, 20), characters, places: placeRanks, containment, ownership };
  // (3) thematic consistency: the relations among a theme's words in the first half of its life against the second (the identity map must preserve them)
  const thematic: ThematicConsistency[] = [];
  for (const t of themeForest) {
    if (t.branches.length < 2 || t.chapters.length < 4) continue;
    const words = [t.root, ...t.branches.map(b => b.word)], ids = words.map(w => elIdx.get(w)).filter((x): x is number => x !== undefined);
    if (ids.length < 3) continue;
    const mid = t.chapters[Math.floor(t.chapters.length / 2)];
    const co = (inHalf: (ci: number) => boolean) => { const m = new Map<string, number>(); for (let ci = 0; ci < nCh; ci++) { if (!inHalf(ci + 1)) continue; for (const si of chSents[ci]) { const here = (perSent.get(si) ?? []).filter(x => ids.includes(x)); for (let a = 0; a < here.length; a++) for (let b = a + 1; b < here.length; b++) { const k = here[a] < here[b] ? `${here[a]}|${here[b]}` : `${here[b]}|${here[a]}`; m.set(k, (m.get(k) ?? 0) + 1); } } } return m; };
    const E = co(c => c <= mid), Lt = co(c => c > mid);
    const keys = new Set([...E.keys(), ...Lt.keys()]); if (keys.size < 2) continue;
    const sumE = [...E.values()].reduce((a, b) => a + b, 0) || 1, sumL = [...Lt.values()].reduce((a, b) => a + b, 0) || 1;
    let mn = 0, mxv = 0; const kept: string[] = [], broken: string[] = [];
    for (const k of keys) { const x = (E.get(k) ?? 0) / sumE, y = (Lt.get(k) ?? 0) / sumL; mn += Math.min(x, y); mxv += Math.max(x, y); const [a, b] = k.split('|').map(Number); const pair = `${elCand[a].w}~${elCand[b].w}`; if (x > 0 && y > 0) kept.push(pair); else broken.push(pair); }
    const pres = mxv ? mn / mxv : 0;
    thematic.push({ root: t.root, early: [t.chapters[0], mid], late: [mid + 1, t.chapters[t.chapters.length - 1]], preservation: round2(pres), kept: kept.slice(0, 5), broken: broken.slice(0, 5), verdict: pres >= 0.35 ? 'coherent' : 'shifts' });
  }
  thematic.sort((a, b) => b.preservation - a.preservation);
  const morphisms: Morphisms = { parallels: parallels.slice(0, 12), hierarchy, thematic };

  lap('DOSSIERS');
  // ── DOSSIERS: for each important character and place, everything the engine knows, gathered in one place ──
  const lineAt = (k0: number) => { const si = sentOf[k0]; if (si < 0) return ''; const r = sentRows[si]; return raw.slice(toks[r.s].idx, toks[r.e].end).replace(/[¶\f]/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 220); };
  const dossiers: Dossier[] = [];
  { const roots = forest.map(f => f.root);
    const pool = nodeList2.filter(e => e.kind === 'character' || e.kind === 'place');
    // how many sheets there are is the work's decision: every forest root, plus the nodes that carry 80% of the mentions of their kind
    const knee = (kind: 'character' | 'place') => { const list = pool.filter(e => e.kind === kind).sort((x, y) => y.occ.length - x.occ.length), tot = list.reduce((a, e) => a + e.occ.length, 0); let acc = 0; const keep: string[] = []; for (const e of list) { if (acc >= 0.8 * tot && keep.length >= 3) break; if (e.occ.length < 4) break; keep.push(e.name); acc += e.occ.length; } return keep; };
    const chosen = [...new Set([...roots, ...knee('character'), ...knee('place')])].map(n => pool.find(e => e.name === n)).filter((e): e is Ent => !!e);
    const momentOf = (ci: number, ev: EventSegment): Moment => ({ chapter: ci + 1, title: chapters[ci].title, pages: ev.pages, actors: ev.actors, place: ev.place, words: ev.words, charge: ev.charge });
    for (const e of chosen) {
      const occs = [...e.occ].sort((a, b) => a.k - b.k), pg = occs.map(o => o.pg);
      const chs = [...new Set(occs.map(o => chapterOfPage(o.pg)))].sort((a, b) => a - b);
      const f = forest.find(x => x.root === e.name), aff = affinity.find(a => a.node === e.name), cir = circles.find(c => c.node === e.name);
      const arc = arcs.find(a => a.node === e.name) ?? null, rt = routes.find(r => r.name === e.name);
      const relations = routePairs.filter(p => p.kind === 'node-node' && (p.a === e.name || p.b === e.name)).sort((a, b) => rank(b) - rank(a)).slice(0, 6)
        .map(p => { const w = p.a === e.name ? p.b : p.a, pt = tension.pairs.find(x => (x.a === e.name && x.b === w) || (x.b === e.name && x.a === w)); return { with: w, relation: p.relation, together: p.together, encounters: p.encounters.length, closest: p.closest ? p.closest.pages : null, trend: p.trend, sharedPlaces: p.sharedPlaces, tone: pt ? { valence: pt.valence, tension: pt.tension, bond: pt.bond, trend: pt.trend, peak: pt.peak } : null }; });
      // scenes where it is on stage (or is the place); the strongest by charge and by how many rare words happen in them
      const scenes: Moment[] = [];
      chapters.forEach((c, ci) => c.events.forEach(ev => { if (ev.actors.includes(e.name) || ev.place === e.name) scenes.push(momentOf(ci, ev)); }));
      const keyMoments = [...scenes].sort((a, b) => (Math.abs(b.charge) + 0.4 * b.words.length) - (Math.abs(a.charge) + 0.4 * a.words.length)).slice(0, 5).sort((a, b) => a.pages[0] - b.pages[0]);
      const hot = [...new Set(scenes.map(m => m.chapter))].sort((a, b) => chapters[b - 1].tone.arousal - chapters[a - 1].tone.arousal)[0];
      const climax = hot !== undefined ? scenes.filter(m => m.chapter === hot).sort((a, b) => Math.abs(b.charge) - Math.abs(a.charge))[0] ?? null : null;
      const n = nodeList.find(x => x.name === e.name);
      const dos: Dossier = {
        name: e.name, kind: e.kind === 'place' ? 'place' : 'character', aliases: [...new Set(e.aliases)], rank: f?.rank ?? (chs.length >= nCh * 0.4 ? 'primary' : 'secondary'),
        presence: { mentions: occs.length, first: Math.min(...pg), last: Math.max(...pg), chapters: chs.map(c => c + 1), share: round2(chs.length / Math.max(1, nCh)), density: density(e.occ) },
        voice: n?.voice ?? voiceOf(e),
        introduced: (() => { const o = occs.find(x => lineAt(x.k)) ?? occs[0]; return { page: o.pg, chapter: chapterOfPage(o.pg) + 1, line: lineAt(o.k) }; })(),
        lastSeen: (() => { const o = [...occs].reverse().find(x => lineAt(x.k)) ?? occs[occs.length - 1]; return { page: o.pg, chapter: chapterOfPage(o.pg) + 1, line: lineAt(o.k) }; })(),
        route: rt?.legs ?? [],
        home: (() => { const m = atPlace.get(e.name); if (!m) return null; const b = [...m].sort((x, y) => y[1] - x[1])[0]; return b && homeOf(e.name, b[0]) >= 0.3 ? b[0] : null; })(),
        places: [...(atPlace.get(e.name) ?? [])].sort((x, y) => y[1] - x[1]).slice(0, 4).map(([pl]) => { const pc = placeCasts.find(c => c.place === pl); return { place: pl, home: round2(homeOf(e.name, pl)), weight: pc?.cast.find(c => c.name === e.name)?.weight ?? 0, role: roleOf(homeOf(e.name, pl)) }; }),
        circle: { inner: cir?.inner ?? [], outer: cir?.outer ?? [], proper: cir?.proper ?? [] },
        traits: { elements: (aff?.elements ?? []).slice(0, 8).map(x => x.word), actions: (aff?.actions ?? []).slice(0, 5).map(x => x.word) },
        relations, tone: tension.nodes.find(x => x.node === e.name) ?? null, generates: f?.generates ?? [], standing: (() => { const r = hierarchy.characters.find(x => x.node === e.name); return r ? { level: r.level, score: r.score, evidence: r.evidence } : null; })(), owns: hierarchy.ownership.filter(o => o.owner === e.name).map(o => o.element).slice(0, 8), arc, keyMoments, climax,
        parallels: morphisms.parallels.filter(pp => pp.mapping.some(([x, y]) => x === e.name || y === e.name)).slice(0, 4)
          .map(pp => ({ chapters: [pp.a.chapter, pp.b.chapter] as [number, number], kind: pp.kind, similarity: pp.similarity, becomes: pp.mapping.find(([x]) => x === e.name)?.[1] ?? pp.mapping.find(([, y]) => y === e.name)?.[0] ?? null })),
        themes: themeForest.filter(t => t.chapters.filter(c => chs.includes(c - 1)).length >= Math.max(1, chs.length / 3)).sort((a, b) => b.share - a.share).slice(0, 6).map(t => ({ root: t.root, flow: t.flow, share: t.share })),
        sections: [],
      };
      dos.sections = buildSections(dos); dossiers.push(dos);
    }
  }
  const injectivity: Injectivity = { entities: entityCount, mentions: claimed.size, collisions, keptApart: keptApart.sort((a, b) => b.similarity - a.similarity).slice(0, 8), refused: injRefused };

  const result: NodesResult = {
    reportPlan: undefined as unknown as ReportPlan, completion: undefined as unknown as CompletionBrief, restructure: undefined as unknown as Restructure, timings: {}, map4d, tension,
    injectivity, routes, routePairs, placeCasts, affinity, circles, arcs, worldIdentity, morphisms, dossiers,
    language: lang, words: toks.length, layers: NP, pageMode: realPages ? 'real-pages' : 'words-per-page',
    elapsedMs: Date.now() - t0, catalogued: occL.size,
    locations: slugs.map(s => ({ heading: `${s.ie} ${s.place}`, place: s.place, time: s.time, scene: s.id })),
    structuralWords, notNames, wordIndex, equivalenceClasses: equivalence, fields: semFields.map((f, i) => ({ id: f.id, label: f.label, size: f.members.length, valence: round2(fieldValence[i]) })), structure, sentences, forest, treeRelations: treeRelations.slice(0, 20), chapters, themeForest, themeRelations: themeRelations.slice(0, 20), knots, paratext, nodes: nodeList, wordNodes, places, links: links.slice(0, 60), fusions: fusions.slice(0, 60), address,
    timeAxis: { months: monthEvents, yearFirstPage },
  };
  lap('end');
  result.timings = timings;
  if (opts.keepPages) {
    const first = new Array<number>(NP + 2).fill(-1); for (let k = 0; k < toks.length; k++) { const pg = page(k); if (first[pg] < 0) first[pg] = toks[k].idx; }
    result.pageText = Array.from({ length: NP }, (_, i) => { const a = first[i + 1] < 0 ? raw.length : first[i + 1]; let b = raw.length; for (let q = i + 2; q <= NP; q++) if (first[q] >= 0) { b = first[q]; break; } return raw.slice(a, Math.max(a, b)).replace(/ ¶ /g, '\n').replace(/[¶\f]/g, ' ').replace(/ +/g, ' ').trim(); });
  }
  result.reportPlan = buildReportPlan(result);
  result.completion = buildCompletionBrief(result);
  result.restructure = proposeRestructure(result);
  return result;
}
