/**
 * dossier-spec.ts — the structure of the whole report (≈40 pages) and of every sheet inside it, section by section.
 *
 *   Report plan  : 10 blocks (technical sheet, synopsis, principal characters, secondary characters, relations map,
 *                  world, themes, strengths, weaknesses, conclusions). Pages are allocated from what the engine found:
 *                  3 pages per principal character, 2 per secondary, 1 per key location, the rest as annexes up to 40.
 *   Sheets       : principal character (3 pages) · secondary character (2 pages) · location (1 page).
 *
 * Every section declares WHICH engine mechanisms feed it (rows of IDEAS.md, field of NodesResult, function, what it
 * gives) and, once built for a given work, its status:
 *   filled          code produced everything the section needs
 *   evidence-ready  the section is interpretive prose (model); the engine already holds the evidence it will write from
 *   thin            the engine gave part of what is needed
 *   to-complete     the engine has no data for it yet (says what is missing)
 * Nothing here calls a model.
 */
import type { Dossier, NodesResult } from './engine';
import { detectThemes, detectStrengths, detectWeaknesses, type Finding } from './report-detect';

export interface FeedsFrom {
  /** rows of IDEAS.md */
  ideas:  number[];
  /** field of NodesResult the data comes from */
  source: string;
  /** function / stage that computes it */
  fn:     string;
  /** what it gives to the section */
  gives:  string;
}

export type PageRange = [number, number];
export type SectionStatus = 'filled' | 'evidence-ready' | 'thin' | 'to-complete';

interface Need<T> { field: string; has: (x: T) => boolean }
interface Spec<T> {
  id: string; title: string;
  /** page of the sheet (1-based) the section sits on */
  page: number;
  writtenBy: 'code' | 'model';
  purpose: string;
  feeds: FeedsFrom[];
  needs: Need<T>[];
  /** what the engine cannot see on its own, said plainly */
  limit?: string;
}

export interface BuiltSection {
  id: string; title: string; page: number; purpose: string;
  writtenBy: 'code' | 'model';
  status: SectionStatus;
  filled: string[]; missing: string[];
  feeds: FeedsFrom[];
  limit?: string;
  /** the pages a model must read to write this section — catalogued by the engine, so nothing has to be searched for */
  readPages: PageRange[];
  /** for themes, strengths and weaknesses: what the engine detected, with the word chains it rests on */
  finding?: Finding;
}

const has = (v: unknown) => Array.isArray(v) ? v.length > 0 : !!v;

function build<T>(specs: Spec<T>[], x: T): BuiltSection[] {
  return specs.map(s => {
    const filled = s.needs.filter(n => n.has(x)).map(n => n.field), missing = s.needs.filter(n => !n.has(x)).map(n => n.field);
    const all = s.needs.length > 0 && missing.length === 0;
    const status: SectionStatus = s.writtenBy === 'model'
      ? (all ? 'evidence-ready' : filled.length ? 'thin' : 'to-complete')
      : (all ? 'filled' : filled.length ? 'thin' : 'to-complete');
    return { id: s.id, title: s.title, page: s.page, purpose: s.purpose, writtenBy: s.writtenBy, status, filled, missing, feeds: s.feeds, limit: s.limit, readPages: [] };
  });
}

// ───────────────────────────── shared feed descriptions ─────────────────────────────
const F = {
  identity: { ideas: [1, 6, 15, 21, 34, 44, 50], source: 'nodes · equivalenceClasses · injectivity', fn: 'capital runs → typeOf → identity stage (containment, glued appositives, adaptive nearest solar system, claimed map)', gives: 'one entity per name, aliases folded, kind' } as FeedsFrom,
  rank:     { ideas: [17, 18], source: 'forest', fn: 'forest roots, primary / secondary', gives: 'rank in the cast' } as FeedsFrom,
  standing: { ideas: [48], source: 'morphisms.hierarchy', fn: 'learned forms of address + precedence → ranks, ownership, containment', gives: 'standing, who it defers to, what it owns' } as FeedsFrom,
  presence: { ideas: [2, 13, 27, 32], source: 'layers · chapters · wordIndex', fn: 'page(); chapter detection; buildWordIndex', gives: 'where and how much it is on the page' } as FeedsFrom,
  sentences:{ ideas: [9, 12, 33, 43, 46], source: 'sentences · structure', fn: 'sentence rows (solar system between two full stops); front/back matter and titles masked', gives: 'its first and last real sentences' } as FeedsFrom,
  voice:    { ideas: [11], source: 'nodes.voice', fn: 'tmode (dash, quotes, guillemets, screenplay cues)', gives: 'dialogue / action / narration mix' } as FeedsFrom,
  orbit:    { ideas: [8, 37, 38], source: 'affinity · circles · orbit', fn: 'shrunk log-likelihood lift; canonical injection (circle A / outside B)', gives: 'what is proper to it: body words, objects, actions' } as FeedsFrom,
  events:   { ideas: [23, 25], source: 'chapters.events · chapters.tone', fn: 'beats → scenes (actors, place, ordered words); charge from the extended lexicon', gives: 'its scenes with charge' } as FeedsFrom,
  arc:      { ideas: [22, 39, 40], source: 'arcs · embedding · worldIdentity', fn: 'identity function in the embedding, permutation-test rank', gives: 'what stays, is lost, is gained; direction of charge' } as FeedsFrom,
  relations:{ ideas: [20, 36, 17], source: 'routePairs · knots · treeRelations', fn: 'proximity node–node (together, encounters, closest, trend); strand crossings', gives: 'who it relates to, how, and where it tightens or breaks' } as FeedsFrom,
  world:    { ideas: [16, 35, 45], source: 'places · routes · placeCasts', fn: 'place casts (native / regular / visitor, meetings, tension); routes', gives: 'home, places, route, meetings' } as FeedsFrom,
  parallels:{ ideas: [47], source: 'morphisms.parallels', fn: 'type-preserving matching of chapter skeletons', gives: 'echoes of its situation with another cast' } as FeedsFrom,
  themes:   { ideas: [19, 24, 49], source: 'themeForest · chapters.symbols · morphisms.thematic', fn: 'theme trees; semantic fields; thematic consistency', gives: 'motifs and symbols it carries' } as FeedsFrom,
  tone:     { ideas: [57], source: 'tension', fn: 'charge of every sentence (extended lexicon) → tone of each character, tone of each pair, tension per page / chapter', gives: 'its tone, the tone of each bond and the tension levels' } as FeedsFrom,
  prose:    { ideas: [41], source: 'this sheet (all sections)', fn: 'one model call over the structured evidence — the only paid step', gives: 'the prose' } as FeedsFrom,
};

// ───────────────────────────── PRINCIPAL CHARACTER · 3 pages ─────────────────────────────
export const PRINCIPAL: Spec<Dossier>[] = [
  { id: 'anatomy', title: 'Sociodemographic sheet and physical aspect', page: 1, writtenBy: 'model', purpose: 'name, aliases, role, how it looks and where it comes from',
    feeds: [F.identity, F.rank, F.orbit, F.sentences],
    needs: [{ field: 'identity', has: d => !!d.name }, { field: 'introduced', has: d => has(d.introduced.line) }, { field: 'traits.elements', has: d => has(d.traits.elements) }, { field: 'standing', has: d => has(d.standing) }],
    limit: 'age, profession and looks come only from the words that orbit it; if the book never states them, they stay empty' },
  { id: 'mannerisms', title: 'Mannerisms and voice register', page: 1, writtenBy: 'code', purpose: 'how it speaks, what it does habitually, its register',
    feeds: [F.voice, F.orbit, F.events, F.tone],
    needs: [{ field: 'voice', has: d => d.voice.dialogue + d.voice.action + d.voice.narration > 0 }, { field: 'traits.actions', has: d => has(d.traits.actions) }, { field: 'keyMoments', has: d => has(d.keyMoments) }, { field: 'tone', has: d => !!d.tone }] },
  { id: 'wound', title: 'Original wound (ghost)', page: 1, writtenBy: 'model', purpose: 'the past event that conditions its view of the world',
    feeds: [F.arc, F.events, F.sentences, F.themes],
    needs: [{ field: 'arc.lost', has: d => !!d.arc && has(d.arc.lost) }, { field: 'keyMoments', has: d => has(d.keyMoments) }, { field: 'introduced', has: d => has(d.introduced.line) }],
    limit: 'a wound told only as backstory is read from the dark-charged scenes around its first appearance; if it is never narrated, it is inferred, not found' },
  { id: 'lie', title: 'The lie', page: 1, writtenBy: 'model', purpose: 'the false belief about itself or the world that the story puts to the test',
    feeds: [F.arc, F.standing, F.themes],
    needs: [{ field: 'arc', has: d => has(d.arc) }, { field: 'standing', has: d => has(d.standing) }, { field: 'themes', has: d => has(d.themes) }],
    limit: 'interpretive: the engine supplies what holds and what breaks around the character, not the belief itself' },
  { id: 'want', title: 'Want (conscious desire)', page: 2, writtenBy: 'model', purpose: 'what it believes it wants across the novel',
    feeds: [F.orbit, F.relations, F.world, F.standing],
    needs: [{ field: 'traits.actions', has: d => has(d.traits.actions) }, { field: 'route', has: d => has(d.route) }, { field: 'relations', has: d => has(d.relations) }] },
  { id: 'need', title: 'Need (unconscious necessity)', page: 2, writtenBy: 'model', purpose: 'what it must learn or accept in order to mature',
    feeds: [F.arc, F.events],
    needs: [{ field: 'arc.gained', has: d => !!d.arc && has(d.arc.gained) }, { field: 'climax', has: d => has(d.climax) }] },
  { id: 'obstacles', title: 'Internal and external obstacles', page: 2, writtenBy: 'code', purpose: 'who and what stands against it: pulling-apart relations, tensions, rank above it',
    feeds: [F.relations, F.standing, F.world, F.tone],
    needs: [{ field: 'relations', has: d => has(d.relations) }, { field: 'relations.tone', has: d => d.relations.some(r => !!r.tone) }, { field: 'standing', has: d => has(d.standing) }, { field: 'places', has: d => has(d.places) }] },
  { id: 'steps', title: 'Transformation, step by step', page: 3, writtenBy: 'model', purpose: 'starting point, catalyst, second-act crisis, dark night, climax, final state',
    feeds: [F.arc, F.events, F.presence, F.tone],
    needs: [{ field: 'arc', has: d => has(d.arc) }, { field: 'keyMoments', has: d => has(d.keyMoments) }, { field: 'climax', has: d => has(d.climax) }, { field: 'presence.density', has: d => has(d.presence.density) }, { field: 'tone.byChapter', has: d => !!d.tone && has(d.tone.byChapter) }] },
  { id: 'agency', title: 'Key moral decisions and weight in the plot', page: 3, writtenBy: 'model', purpose: 'the choices that define its agency and how much the plot rests on it',
    feeds: [F.voice, F.events, F.standing, F.relations],
    needs: [{ field: 'keyMoments', has: d => has(d.keyMoments) }, { field: 'presence.share', has: d => d.presence.share > 0 }, { field: 'generates', has: d => has(d.generates) }],
    limit: 'the engine ranks the scenes where it acts; calling a choice "moral" is the reading step' },
  { id: 'echoes', title: 'Echoes, motifs and territory', page: 3, writtenBy: 'code', purpose: 'chapters that repeat its situation with another cast, motifs it carries, what it owns',
    feeds: [F.parallels, F.themes, F.standing],
    needs: [{ field: 'parallels', has: d => has(d.parallels) }, { field: 'themes', has: d => has(d.themes) }, { field: 'owns', has: d => has(d.owns) }] },
];

// ───────────────────────────── SECONDARY CHARACTER · 2 pages ─────────────────────────────
export const SECONDARY: Spec<Dossier>[] = [
  { id: 'function', title: 'Dramatic function (mirror, catalyst, obstacle, mentor, antagonist)', page: 1, writtenBy: 'model', purpose: 'its role in the structure',
    feeds: [F.relations, F.standing, F.rank],
    needs: [{ field: 'relations', has: d => has(d.relations) }, { field: 'standing', has: d => has(d.standing) }, { field: 'generates', has: d => has(d.generates) }],
    limit: 'the role label is the reading step; the engine shows whom it stands against, beside or above' },
  { id: 'profile', title: 'Link to the main plot and basic profile', page: 1, writtenBy: 'code', purpose: 'identity, first and last sighting, voice, what is proper to it',
    feeds: [F.identity, F.sentences, F.voice, F.orbit],
    needs: [{ field: 'identity', has: d => !!d.name }, { field: 'introduced', has: d => has(d.introduced.line) }, { field: 'voice', has: d => d.voice.dialogue + d.voice.action + d.voice.narration > 0 }, { field: 'traits.elements', has: d => has(d.traits.elements) }] },
  { id: 'dynamics', title: 'How it affects and is affected by the protagonists', page: 2, writtenBy: 'code', purpose: 'relations, shared places, trend of each tie',
    feeds: [F.relations, F.world, F.tone],
    needs: [{ field: 'relations', has: d => has(d.relations) }, { field: 'relations.tone', has: d => d.relations.some(r => !!r.tone) }, { field: 'places', has: d => has(d.places) }] },
  { id: 'subplot', title: 'Subplot and evolution', page: 2, writtenBy: 'model', purpose: 'its own line from the first to the last page',
    feeds: [F.arc, F.events, F.presence, F.parallels],
    needs: [{ field: 'arc', has: d => has(d.arc) }, { field: 'keyMoments', has: d => has(d.keyMoments) }, { field: 'route', has: d => has(d.route) }] },
];

// ───────────────────────────── LOCATION · 1 page ─────────────────────────────
export const LOCATION: Spec<Dossier>[] = [
  { id: 'sensory', title: 'Sensory description, architecture and symbolism', page: 1, writtenBy: 'model', purpose: 'what the place is made of in the words around it',
    feeds: [F.orbit, F.themes],
    needs: [{ field: 'traits.elements', has: d => has(d.traits.elements) }, { field: 'circle.inner', has: d => has(d.circle.inner) }, { field: 'themes', has: d => has(d.themes) }] },
  { id: 'inhabitants', title: 'Who lives or passes through', page: 1, writtenBy: 'code', purpose: 'natives, regulars, visitors and their weight; meetings and tension',
    feeds: [F.world, F.relations],
    needs: [{ field: 'relations', has: d => has(d.relations) }, { field: 'places', has: d => has(d.places) }] },
  { id: 'events', title: 'Critical dramatic events here', page: 1, writtenBy: 'code', purpose: 'the scenes of greatest charge that happen in it',
    feeds: [F.events, F.presence],
    needs: [{ field: 'keyMoments', has: d => has(d.keyMoments) }, { field: 'climax', has: d => has(d.climax) }] },
];

export const SHEET_PAGES = { principal: 3, secondary: 2, location: 1 } as const;
export type SheetKind = keyof typeof SHEET_PAGES;

export function sheetKind(d: Dossier): SheetKind { return d.kind === 'place' ? 'location' : d.rank === 'primary' ? 'principal' : 'secondary'; }
export function buildSections(d: Dossier): BuiltSection[] { const k = sheetKind(d); return build(k === 'principal' ? PRINCIPAL : k === 'secondary' ? SECONDARY : LOCATION, d); }

// ───────────────────────────── THE WHOLE REPORT ─────────────────────────────
export interface PlanBlock {
  id: string; title: string;
  /** pages this block takes in this work */
  pages: number;
  /** first and last page of the block in the finished report */
  span: [number, number];
  sections: BuiltSection[];
  /** for the character / location blocks: the sheets, one per subject */
  sheets?: { name: string; kind: SheetKind; pages: number; sections: BuiltSection[] }[];
}
/** What a model has to read to write the whole report: only the pages the engine points at, plus the structured evidence of each section */
export interface AiBudget { sections: number; pointedPages: number; inputTokens: number; outputTokens: number; wordsPerPage: number; bookPages: number }
export interface ReportPlan { ai: AiBudget; target: number; themes: number; strengths: number; weaknesses: number; allocated: number; annexPages: number; principals: string[]; secondaries: string[]; locations: string[]; blocks: PlanBlock[] }


export function buildReportPlan(r: NodesResult, target = 40): ReportPlan {
  const chars = r.dossiers.filter(d => d.kind === 'character');
  // no fixed counts: the work decides who is principal (forest rank) and how many secondaries and locations matter (see the engine's dossier selection)
  const principals = chars.filter(d => d.rank === 'primary');
  const secondaries = chars.filter(d => d.rank !== 'primary');
  const locations = r.dossiers.filter(d => d.kind === 'place');
  const themes = detectThemes(r), strengths = detectStrengths(r), weaknesses = detectWeaknesses(r);
  const chaptersWithEvents = r.chapters.filter(c => c.events.length).length;

  const R = (field: string, ok: boolean) => ({ field, has: () => ok });
  const glob = (id: string, title: string, writtenBy: 'code' | 'model', purpose: string, feeds: FeedsFrom[], needs: { field: string; ok: boolean }[], limit?: string, page = 1): BuiltSection =>
    build<null>([{ id, title, page, writtenBy, purpose, feeds, needs: needs.map(n => R(n.field, n.ok)), limit }], null)[0];

  const blocks: PlanBlock[] = [];
  const add = (id: string, title: string, pages: number, sections: BuiltSection[], sheets?: PlanBlock['sheets']) => blocks.push({ id, title, pages, span: [0, 0], sections, sheets });

  add('technical', '1. Technical sheet and executive summary', 1, [
    glob('facts', 'Hard data, tone, logline, premise, structural metrics', 'model', 'words, pages, chapters, cast size, tone of the whole, premise', [
      { ideas: [2, 13, 12, 43], source: 'words · layers · structure', fn: 'page(); chapter detection; front/back matter', gives: 'hard data and structural metrics' },
      { ideas: [25, 57], source: 'chapters.tone · tension', fn: 'extended-lexicon tone, sentence = one event; tension per page', gives: 'general tone and tension curve' },
      F.rank,
    ], [{ field: 'tension curve', ok: r.tension.curve.length > 0 }, { field: 'metrics', ok: r.words > 0 && r.layers > 0 }, { field: 'chapters', ok: r.chapters.length > 0 }, { field: 'tone', ok: r.chapters.some(c => !!c.tone) }, { field: 'cast', ok: chars.length > 0 }], 'logline and premise are written from the cast, the first scenes and the climax; the engine only holds the evidence'),
  ]);

  add('synopsis', '2. Extended synopsis and dramatic outline', 5, [
    glob('synopsis', 'Global synopsis with full ending', 'model', 'what happens, in order, to the end', [
      F.events, { ideas: [13, 23], source: 'chapters', fn: 'chapters as islands; event chains per chapter', gives: 'ordered chapters with their scenes' },
    ], [{ field: 'events', ok: chaptersWithEvents > 0 }, { field: 'chapters', ok: r.chapters.length > 0 }, { field: 'last chapter', ok: r.chapters.length > 1 }], undefined),
    glob('outline', 'Outline chapter by chapter: turning points, tension peaks, rhythm', 'code', 'for every chapter: cast, place, scenes, charge, rarity signature, gaps', [
      { ideas: [13, 23, 25], source: 'chapters · events · tone · signature', fn: 'chapter loop', gives: 'per-chapter outline with charge' },
      { ideas: [13], source: 'structure.chapterSource · inferred', fn: 'rhythm gap recovery', gives: 'missing chapters flagged' },
      { ideas: [47], source: 'morphisms.parallels', fn: 'skeleton matching', gives: 'echoing chapters' },
    ], [{ field: 'chapters', ok: r.chapters.length > 0 }, { field: 'events', ok: chaptersWithEvents === r.chapters.length && r.chapters.length > 0 }, { field: 'tone', ok: r.chapters.every(c => !!c.tone) }, { field: 'parallels', ok: r.morphisms.parallels.length > 0 }], undefined, 2),
  ]);

  add('principals', '3. Principal characters (3 pages each)', principals.length * SHEET_PAGES.principal, [], principals.map(d => ({ name: d.name, kind: 'principal' as const, pages: SHEET_PAGES.principal, sections: buildSections(d) })));
  add('secondaries', '4. Secondary characters (2 pages each)', secondaries.length * SHEET_PAGES.secondary, [], secondaries.map(d => ({ name: d.name, kind: 'secondary' as const, pages: SHEET_PAGES.secondary, sections: buildSections(d) })));

  add('network', '5. Relationship map and network mechanics', 3, [
    glob('taxonomy', 'Taxonomy of bonds', 'code', 'alliances, dependence, power hierarchies, latent enmities — classified', [F.relations, F.standing, F.tone], [{ field: 'routePairs', ok: r.routePairs.some(p => p.kind === 'node-node') }, { field: 'deference', ok: r.morphisms.hierarchy.deference.length > 0 }, { field: 'hierarchy', ok: r.morphisms.hierarchy.characters.length > 0 }, { field: 'bond tone', ok: r.tension.pairs.length > 0 }], 'bonds are classified by proximity, trend, deference and the tone of the sentences the two share (hostile / strained / warm / calm); the lexicon behind the tone covers Spanish and English only'),
    glob('sociogram', 'Sociogram and faction dynamics', 'code', 'groups of nodes, how they cluster, how things flow between them', [
      { ideas: [17, 20], source: 'forest · treeRelations · knots', fn: 'tree–tree relations; strand crossings', gives: 'clusters and hand-overs' },
      { ideas: [38], source: 'circles', fn: 'shared elements between circles', gives: 'what groups share' },
    ], [{ field: 'treeRelations', ok: r.treeRelations.length > 0 }, { field: 'knots', ok: r.knots.pairs.length > 0 }, { field: 'circles', ok: r.circles.length > 0 }], undefined, 2),
    glob('power', 'Power mechanics and catalysts', 'model', 'friction points, shared secrets, how the balance shifts', [
      F.standing, { ideas: [45], source: 'placeCasts.meetings', fn: 'meetings with tension', gives: 'friction points' }, F.relations, F.tone,
    ], [{ field: 'hierarchy', ok: r.morphisms.hierarchy.characters.length > 0 }, { field: 'meetings', ok: r.placeCasts.some(p => p.meetings.length > 0) }, { field: 'trends', ok: r.routePairs.some(p => p.trend !== undefined) }, { field: 'tension of bonds', ok: r.tension.pairs.some(p => p.trend !== 'steady' || p.tension > 0) }], 'debts and secrets are not visible to letters alone; what is shown is where tension meets', 3),
  ]);

  add('world', '6. World, locations and human geography', 1 + locations.length, [
    glob('worldframe', 'Global frame and worldbuilding', 'model', 'physical, social, atmospheric and temporal rules of the setting', [
      F.world, { ideas: [26], source: 'timeAxis', fn: 'calendar nodes, year axis', gives: 'time frame' }, { ideas: [48], source: 'morphisms.hierarchy.containment', fn: 'containment between places', gives: 'nested geography' },
    ], [{ field: 'places', ok: r.places.length > 0 }, { field: 'placeCasts', ok: r.placeCasts.length > 0 }, { field: 'containment', ok: r.morphisms.hierarchy.containment.length > 0 }, { field: 'timeAxis', ok: r.timeAxis.months.length > 0 }], 'rules of a world are read from what is repeated about it'),
  ], locations.map(d => ({ name: d.name, kind: 'location' as const, pages: SHEET_PAGES.location, sections: buildSections(d) })));

  const FEEDS_BY_FAMILY: Record<string, FeedsFrom[]> = {
    theme: [F.themes, { ideas: [32], source: 'wordIndex', fn: 'chain of every word of the theme: positions, before / after, solar system', gives: 'where the theme\'s words stand and what surrounds them' }],
    transformation: [F.arc, { ideas: [32], source: 'wordIndex', fn: 'chain of the words gained and lost', gives: 'positions and solar systems of what changes' }],
    structure: [F.parallels, { ideas: [13], source: 'structure · chapters.inferred', fn: 'chapter detection and rhythm gap', gives: 'chapter skeletons and gaps' }],
    rhythm: [F.events, { ideas: [25], source: 'chapters.tone', fn: 'arousal per chapter', gives: 'swings of intensity' }],
    world: [F.arc, { ideas: [40], source: 'worldIdentity', fn: 'solar system of every word, first third against last third', gives: 'invariant and drifting words' }],
    place: [F.world, F.relations],
    voice: [F.voice, F.orbit, { ideas: [32], source: 'wordIndex', fn: 'chains of its distinctive words', gives: 'what only it says' }],
    repetition: [{ ideas: [32], source: 'wordIndex', fn: 'chain of EVERY word (basic ones too): count, positions, what comes right before and after, solar system', gives: 'stock phrases and words that crowd the page' }, { ideas: [3, 4], source: 'catalogue · scales', fn: 'rarity at page / chapter / work', gives: 'what is common vs. exotic' }],
    pace: [F.events, { ideas: [25], source: 'chapters.tone', fn: 'arousal per chapter', gives: 'flat stretches' }],
    presence: [F.presence, { ideas: [32], source: 'wordIndex / dossiers.presence.density', fn: 'density per slice', gives: 'silences in a character\'s chain' }],
    relations: [F.relations, F.presence],
    identity: [F.identity, { ideas: [34], source: 'injectivity.keptApart', fn: 'pairs kept apart because both are names', gives: 'confusable names' }],
  };
  const fromFinding = (f: Finding, kind: 'theme' | 'strength' | 'weakness', page: number): BuiltSection => {
    const feeds = FEEDS_BY_FAMILY[f.family] ?? [F.themes];
    return { id: f.id, title: f.title, page, writtenBy: 'model', purpose: kind === 'theme' ? 'thesis, antithesis and subtext of this theme' : kind === 'strength' ? 'a powerful element, analysed alone on its page' : 'a fault, its diagnosis and the fix',
      readPages: [], status: f.evidence.length ? 'evidence-ready' : 'thin', filled: ['evidence', ...(f.words.length ? ['word chains'] : [])], missing: f.words.length ? [] : ['word chains'], feeds, finding: f };
  };
  const findingBlock = (id: string, title: string, list: Finding[], kind: 'theme' | 'strength' | 'weakness', extra: BuiltSection[] = []) =>
    add(id, title, list.length + extra.length, [...list.map((f, i) => fromFinding(f, kind, i + 1)), ...extra.map((e, i) => ({ ...e, page: list.length + i + 1 }))]);

  findingBlock('themes', `7. Themes, symbols and deep subtext (${themes.length} detected, 1 page each)`, themes, 'theme',
    themes.length ? [glob('glossary', 'Symbols and motifs: glossary', 'code', 'recurring objects, images and metaphors with their flow through the book', [{ ideas: [19], source: 'themeForest', fn: 'theme trees with flow', gives: 'glossary of motifs' }, { ideas: [49], source: 'morphisms.thematic', fn: 'thematic consistency', gives: 'whether a motif holds or shifts' }], [{ field: 'themeForest', ok: r.themeForest.length > 0 }, { field: 'flow', ok: r.themeForest.some(t => !!t.flow) }])] : []);
  findingBlock('strengths', `8. Strengths and powerful elements (${strengths.length} detected, 1 page each)`, strengths, 'strength');
  findingBlock('weaknesses', `9. Weaknesses, diagnosis and improvement plan (${weaknesses.length} detected, 1 page each + plan)`, weaknesses, 'weakness',
    weaknesses.length ? [glob('plan', 'Optimisation plan and rewrite proposal', 'model', 'step-by-step fixes for each fault above', [{ ideas: [41], source: 'the faults above', fn: 'one model call over the detected faults', gives: 'the proposals' }], [{ field: 'faults', ok: true }])] : []);

  add('conclusion', '10. Conclusions and global assessment', 1, [
    glob('verdict', 'Definitive synthesis of literary and commercial value', 'model', 'what the work is worth and to whom', [F.themes, F.arc, F.rank], [{ field: 'worldIdentity', ok: !!r.worldIdentity }, { field: 'cast', ok: chars.length > 0 }, { field: 'themes', ok: r.themeForest.length > 0 }], 'commercial value needs the market, which is outside the text'),
  ]);

  // ── page pointers: for each section, the pages worth reading, taken from what the engine catalogued ──
  const merge = (rs: PageRange[], cap = 10): PageRange[] => {
    const v = rs.filter(x => x && x[0] > 0).map(x => [Math.min(x[0], x[1]), Math.min(Math.max(x[0], x[1]), Math.min(x[0], x[1]) + 2)] as PageRange)       // a pointer says where to look: three pages from its start at most
      .sort((a, b) => a[0] - b[0]);
    const out: PageRange[] = []; for (const x of v) { const l = out[out.length - 1]; if (l && x[0] <= l[1] + 1) l[1] = Math.max(l[1], x[1]); else out.push([x[0], x[1]]); }
    let n = 0; return out.filter(x => (n += x[1] - x[0] + 1) <= cap || n - (x[1] - x[0] + 1) === 0);
  };
  const chPages = (c: number): PageRange[] => r.chapters[c - 1] ? [r.chapters[c - 1].pages] : [];
  const topScene = (c: number): PageRange[] => { const ev = r.chapters[c - 1]?.events ?? []; const b = [...ev].sort((x, y) => Math.abs(y.charge) - Math.abs(x.charge))[0]; return b ? [b.pages] : chPages(c).map(x => [x[0], x[0]] as PageRange); };
  const atPages = (w: string): PageRange[] => (r.wordIndex[w.toLowerCase()]?.at ?? []).slice(0, 6).map(p => [p, p] as PageRange);
  const forDossier = (d: Dossier, id: string): PageRange[] => {
    const km = d.keyMoments.map(m => m.pages), intro: PageRange[] = d.introduced.page ? [[d.introduced.page, d.introduced.page]] : [], last: PageRange[] = d.lastSeen.page ? [[d.lastSeen.page, d.lastSeen.page]] : [];
    const climax: PageRange[] = d.climax ? [d.climax.pages] : [];
    switch (id) {
      case 'anatomy': case 'profile': case 'sensory': return intro;
      case 'mannerisms': case 'agency': case 'events': return km;
      case 'wound': return [...intro, ...km.slice(0, 1)];
      case 'lie': return [...km.slice(0, 1), ...km.slice(-1)];
      case 'want': return d.route.slice(0, 2).map(x => x.pages);
      case 'need': return [...climax, ...last];
      case 'obstacles': case 'dynamics': return [...d.relations.map(x => x.tone?.peak ? [x.tone.peak, x.tone.peak] as PageRange : x.closest).filter((x): x is PageRange => !!x).slice(0, 3)];
      case 'inhabitants': case 'function': return d.relations.map(x => x.closest).filter((x): x is [number, number] => !!x).slice(0, 3);
      case 'steps': return [...intro, ...km, ...climax, ...(d.tone?.peak ? [[d.tone.peak, d.tone.peak] as PageRange] : []), ...last];
      case 'subplot': return [...intro, ...km.slice(0, 2), ...last];
      case 'echoes': return d.parallels.flatMap(pp => pp.chapters.flatMap(c => topScene(c))).slice(0, 4);
      default: return [];
    }
  };
  const forFinding = (f: Finding): PageRange[] => {
    const [fam, key] = [f.id.split(':')[0], f.id.slice(f.id.indexOf(':') + 1)];
    if (fam === 'theme') { const t = r.themeForest.find(x => x.root === key); return t ? (t.peaks.length ? t.peaks : t.chapters.slice(0, 3)).flatMap(topScene) : []; }
    if (fam === 'arc' || fam === 'voice' || fam === 'absent') { const d = r.dossiers.find(x => x.name === key); return d ? [...(d.introduced.page ? [[d.introduced.page, d.introduced.page] as PageRange] : []), ...d.keyMoments.slice(0, 2).map(m => m.pages), ...(d.lastSeen.page ? [[d.lastSeen.page, d.lastSeen.page] as PageRange] : [])] : []; }
    if (fam === 'echo') { const [a, b] = key.split('-').map(Number); return [...topScene(a), ...topScene(b)]; }
    if (fam === 'place') { const d = r.dossiers.find(x => x.name === key); return d ? d.keyMoments.map(m => m.pages) : []; }
    if (fam === 'tic' || fam === 'crowd') return atPages(key);
    if (fam === 'flat') return topScene(Number(key));
    if (fam === 'rhythm') { return r.chapters.slice().sort((x, y) => y.tone.arousal - x.tone.arousal).slice(0, 3).flatMap(c => topScene(c.index)); }
    if (fam === 'gaps') return r.chapters.filter(c => c.inferred).slice(0, 4).flatMap(c => [[c.pages[0], c.pages[0]] as PageRange]);
    if (fam === 'dry') return r.chapters.filter(c => c.mix.dialogue < 0.02).slice(0, 3).flatMap(c => topScene(c.index));
    if (fam === 'confusable') return [key].flatMap(() => []);
    if (fam === 'world-return') return [[1, 1], [Math.max(1, r.layers), Math.max(1, r.layers)]];
    return [];
  };
  for (const b of blocks) {
    for (const sec of b.sections) {
      if (sec.finding) sec.readPages = merge(forFinding(sec.finding));
      else if (sec.id === 'synopsis') sec.readPages = merge(r.chapters.flatMap(c => topScene(c.index)), 60);
      else if (sec.id === 'facts') sec.readPages = merge([[1, 1], [r.layers, r.layers]]);
      else if (sec.id === 'verdict') sec.readPages = merge([...principals.flatMap(d => d.climax ? [d.climax.pages] : []), [r.layers, r.layers]]);
    }
    for (const sh of b.sheets ?? []) { const d = r.dossiers.find(x => x.name === sh.name); if (d) for (const sec of sh.sections) { sec.readPages = merge(forDossier(d, sec.id)); const mine = d.sections.find(x => x.id === sec.id); if (mine) mine.readPages = sec.readPages; } }
  }
  // what a model would read and write for the whole report
  const wpp = r.words / Math.max(1, r.layers), OUT_PER_PAGE = 900, EVIDENCE_TOKENS = 1500, TOK_PER_WORD = 1.4;
  let aiSections = 0, pointed = 0, inTok = 0, outTok = 0;
  const countModel = (secs: BuiltSection[], pages: number, total: number) => { for (const sec of secs) if (sec.writtenBy === 'model') { const pg = sec.readPages.reduce((a, x) => a + x[1] - x[0] + 1, 0); aiSections++; pointed += pg; inTok += EVIDENCE_TOKENS + pg * wpp * TOK_PER_WORD; outTok += OUT_PER_PAGE * pages / Math.max(1, total); } };
  for (const b of blocks) { if (b.sections.length) countModel(b.sections, b.pages, b.sections.length); for (const sh of b.sheets ?? []) countModel(sh.sections, sh.pages, sh.sections.length); }
  const ai: AiBudget = { sections: aiSections, pointedPages: pointed, inputTokens: Math.round(inTok), outputTokens: Math.round(outTok), wordsPerPage: Math.round(wpp), bookPages: r.layers };

  // pages: allocated from the blocks, the rest become annexes (tables and outlines) up to the target
  let cursor = 1;
  for (const b of blocks) { b.span = b.pages ? [cursor, cursor + b.pages - 1] : [cursor, cursor]; cursor += b.pages; }
  const allocated = blocks.reduce((a, b) => a + b.pages, 0);
  return { ai, target: Math.max(target, allocated), themes: themes.length, strengths: strengths.length, weaknesses: weaknesses.length, allocated, annexPages: Math.max(0, target - allocated), principals: principals.map(d => d.name), secondaries: secondaries.map(d => d.name), locations: locations.map(d => d.name), blocks };
}
