/**
 * screenplay.ts — the node engine read as a screenplay.
 *
 * A script is the same thing the engine already reads — a text whose pages are layers of time, whose nodes are the names that come back — but
 * with a typed layout: scene headings that carry data (interior / exterior, place, time of day), character cues with the speech under them,
 * parentheticals that describe the action of the speaker, transitions, and the technical vocabulary of the camera (shots, angles, movements).
 * Nothing here calls a model: the layout and a closed list of film terms say what each line is.
 *
 * It builds on `parseScript` (line classification), adds what it does not read — heading data, camera terms, learned marked terms, per-scene
 * counts, per-character speech — and runs the node engine over the same text so the scenes carry the layers, the tone and the tension.
 */
import { parseScript, type ScriptElement } from '@/lib/storyboard/script-parser';
import { isSlugline } from '@/lib/storyboard/scene-splitter';
import { analyzeNodes, type NodesResult } from './engine';

export interface SceneHeading {
  raw:    string;
  number: string | null;
  intExt: 'INT' | 'EXT' | 'INT/EXT' | null;
  /** the main place: «RESTAURANTE» in «INT. RESTAURANTE — MESA · NOCHE» */
  place:  string;
  /** what lies inside it: «MESA» */
  subPlace: string | null;
  /** the time as written */
  time:   string | null;
  timeClass: 'day' | 'night' | 'dawn' | 'dusk' | 'continuous' | 'other' | null;
  flags:  string[];
}
export interface CameraTerm { term: string; kind: 'shot' | 'angle' | 'movement' | 'transition' | 'sound' | 'effect' | 'learned'; count: number; scenes: number[]; sample: string }
export interface ScriptScene {
  index: number; heading: SceneHeading;
  /** first and last line (0-based) of the scene in the text */
  lines: [number, number];
  /** page of the script where it starts and ends */
  pages: [number, number];
  cast: string[];
  actionBlocks: number; dialogueLines: number; parentheticals: number;
  /** words of speech and of action */
  speechWords: number; actionWords: number;
  dialogueShare: number;
  camera: string[]; transitions: string[];
  /** 0–100, the tension of the pages the scene covers (from the engine's tension curve) */
  tension: number | null;
}
export interface ScriptCharacter {
  name: string; cues: number; dialogueLines: number; words: number;
  /** share of all the speech of the script */
  share: number;
  /** what is written under the speech between brackets: how it is said, what the speaker does */
  parentheticals: { text: string; scene: number }[];
  /** (V.O.), (O.S.), (CONT'D)… counted */
  extensions: Record<string, number>;
  firstScene: number; lastScene: number; scenes: number;
}
export interface ScriptPlace { place: string; scenes: number[]; intExt: string[]; times: Record<string, number>; subPlaces: string[] }
export interface ScreenplayReading {
  isScreenplay: boolean;
  /** share of the scenes that opened with a proper heading and of the lines that were classified */
  confidence: number;
  scenes: ScriptScene[];
  characters: ScriptCharacter[];
  places: ScriptPlace[];
  timeOfDay: Record<string, number>;
  camera: CameraTerm[];
  /** marked terms the script itself repeats in capitals inside the action and that no list names */
  learnedTerms: { term: string; count: number; sample: string }[];
  transitions: { text: string; count: number }[];
  stats: { pages: number; minutes: number; scenes: number; dialogueShare: number; speakers: number; avgSceneLines: number };
  /** four parts by weight in pages (25 / 25 / 25 / 25) with the scenes that fall in each and the most tense scene */
  acts: { part: string; scenes: [number, number]; peakScene: number | null }[];
  /** the node engine over the same text: layers, nodes, tone, tension */
  engine: NodesResult;
}

// ── heading ────────────────────────────────────────────────────────────────
const TIMES: [RegExp, SceneHeading['timeClass']][] = [
  [/\b(NOCHE|NIGHT|NACHT|NUIT)\b/i, 'night'], [/\b(D[IÍ]A|DAY|TAG|JOUR|MA[ÑN]ANA|MORNING|TARDE|AFTERNOON|MEDIOD[IÍ]A|NOON)\b/i, 'day'],
  [/\b(AMANECER|MADRUGADA|DAWN|SUNRISE|ALBA)\b/i, 'dawn'], [/\b(ATARDECER|ANOCHECER|DUSK|SUNSET|EVENING|CREP[ÚU]SCULO)\b/i, 'dusk'],
  [/\b(CONTINUO|CONTINUOUS|CONT'?D|SAME|MOMENTS? LATER|M[ÁA]S TARDE|LATER)\b/i, 'continuous'],
];
const HEAD_RE = /^\s*(?:(\d+[A-Z]?)\s*[.\-–—)]?\s+)?(INT\.?\s*[\/\-]\s*EXT\.?|EXT\.?\s*[\/\-]\s*INT\.?|I\s*\/\s*E|INTERIOR\s*\/\s*EXTERIOR|INT|EXT|INTERIOR|EXTERIOR)\b\.?[\s.\-–—:]*(.*)$/i;
export function parseHeading(line: string): SceneHeading {
  const raw = line.trim(), m = HEAD_RE.exec(raw);
  if (!m) return { raw, number: null, intExt: null, place: raw, subPlace: null, time: null, timeClass: null, flags: [] };
  const ie = m[2].toUpperCase().replace(/\s|\./g, ''), intExt: SceneHeading['intExt'] = /\/|-|IE|I\/E/.test(ie) && /INT/.test(ie) && /EXT/.test(ie) || ie === 'IE' ? 'INT/EXT' : /^EXT/.test(ie) ? 'EXT' : 'INT';
  let rest = m[3].trim(), time: string | null = null, timeClass: SceneHeading['timeClass'] = null;
  const parts = rest.split(/\s*(?:[—–·|]|\s-\s|\s\/\s|\.\s+)\s*/).map(x => x.trim().replace(/[.\s]+$/, '')).filter(Boolean);
  const kept: string[] = [];
  for (const p of parts) { const t = TIMES.find(([re]) => re.test(p)); if (t && p.length <= 28 && !time) { time = p; timeClass = t[1]; } else kept.push(p); }
  const flags: string[] = []; for (const f of ['FLASHBACK', 'SUE[ÑN]O', 'DREAM', 'MONTAGE', 'MONTAJE', 'CONTINUO', 'CONTINUOUS']) if (new RegExp(`\\b${f}\\b`, 'i').test(rest)) flags.push(f.replace('[ÑN]', 'Ñ'));
  rest = kept.join(' — ');
  return { raw, number: m[1] ?? null, intExt, place: kept[0] ?? rest, subPlace: kept.length > 1 ? kept.slice(1).join(' — ') : null, time, timeClass, flags };
}

// ── camera and film vocabulary (a closed list; the script’s own capitals add what it does not name) ─────────
const LEX: { kind: CameraTerm['kind']; terms: string[]; acronym?: boolean }[] = [
  { kind: 'shot', terms: ['EXTREME CLOSE-?UP', 'EXTREME CLOSE UP', 'CLOSE-?UP', 'CLOSE UP', 'CLOSE ON', 'MEDIUM SHOT', 'MEDIUM CLOSE', 'WIDE SHOT', 'WIDE ON', 'ESTABLISHING SHOT', 'ESTABLISHING', 'TWO[- ]SHOT', 'FULL SHOT', 'LONG SHOT', 'MASTER SHOT', 'INSERT', 'PRIMER PLANO', 'PRIMERÍSIMO PRIMER PLANO', 'PLANO DETALLE', 'PLANO MEDIO', 'PLANO GENERAL', 'PLANO AMERICANO', 'PLANO CONJUNTO', 'PLANO ENTERO', 'GRAN PLANO GENERAL', 'PLANO SECUENCIA', 'DETALLE', 'INSERTO'] },
  { kind: 'angle', terms: ['OVER THE SHOULDER', 'OVER-THE-SHOULDER', 'SOBRE EL HOMBRO', 'POV', 'P\\.O\\.V\\.', 'PUNTO DE VISTA', 'ANGLE ON', 'ÁNGULO', 'LOW ANGLE', 'HIGH ANGLE', 'DUTCH ANGLE', 'BIRD.?S EYE', 'AERIAL', 'PLANO ZENITAL', 'PICADO', 'CONTRAPICADO', 'PLANO NADIR', 'CÁMARA SUBJETIVA', 'SUBJECTIVE'] },
  { kind: 'movement', terms: ['PAN', 'PANNING', 'WHIP PAN', 'PANORÁMICA', 'TILT UP', 'TILT DOWN', 'TILT', 'ZOOM IN', 'ZOOM OUT', 'ZOOM', 'DOLLY', 'TRACKING', 'TRAVELLING', 'TRAVELING', 'STEADICAM', 'HANDHELD', 'CÁMARA EN MANO', 'CRANE', 'GRÚA', 'RACK FOCUS', 'PULL BACK', 'PUSH IN', 'PUSHES IN', 'CÁMARA LENTA', 'SLOW MOTION', 'TIME-?LAPSE', 'FOLLOWS', 'SIGUE A', 'TRAVELLING DE'] },
  { kind: 'transition', terms: ['CUT TO', 'CORTE A', 'SMASH CUT', 'MATCH CUT', 'JUMP CUT', 'TIME CUT', 'FADE IN', 'FADE OUT', 'FADE TO', 'FUNDIDO A NEGRO', 'FUNDIDO', 'ENCADENADO', 'DISSOLVE TO', 'DISSOLVE', 'WIPE TO', 'IRIS', 'INTERCUT', 'SPLIT SCREEN', 'FREEZE FRAME', 'CONTINUOUS', 'LATER', 'MÁS TARDE'] },
  { kind: 'sound', terms: ['V\\.?O\\.?', 'O\\.?S\\.?', 'O\\.?C\\.?', 'VOZ EN OFF', 'EN OFF', 'OFF', 'SFX', 'FX', 'SONIDO', 'MUSIC', 'MÚSICA', 'SCORE', 'SOUND OF', 'SILENCE', 'SILENCIO', 'SUPER', 'TITLE', 'TÍTULO', 'SUBTITLES', 'SUBTÍTULOS'], acronym: true },
  { kind: 'effect', terms: ['FLASHBACK', 'FLASH-?FORWARD', 'MONTAGE', 'MONTAJE', 'SERIES OF SHOTS', 'DREAM SEQUENCE', 'SECUENCIA DE SUEÑO', 'BLACK', 'NEGRO', 'FILTRO', 'FILTER', 'SPLIT', 'DESENFOCADO', 'OUT OF FOCUS'] },
];
const ACRONYMS = new Set(['V.O', 'VO', 'O.S', 'OS', 'O.C', 'OC', 'FX', 'POV', 'SFX']);
const lexRes = LEX.map(g => ({ kind: g.kind, items: g.terms.map(t => ({ label: t.replace(/\\\./g, '.').replace(/\.\?/g, '').replace(/[-.]?\?/g, ' ').replace(/\\/g, ''), re: new RegExp(`(?<![\\p{L}\\p{N}])(${t})(?![\\p{L}\\p{N}])`, ACRONYMS.has(t.replace(/\\\.|\.\?/g, '').toUpperCase()) || t.length <= 3 ? 'u' : 'iu') })) }));

const wordsOf = (t: string) => (t.match(/[\p{L}\p{N}'’]+/gu) ?? []).length;
const EXT_RE = /\(\s*(V\.?O\.?|O\.?S\.?|O\.?C\.?|CONT'?D|CONT|OFF|SUPER|FILTRO|FILTER)[^)]*\)/i;

export function analyzeScreenplay(text: string, opts: { language?: 'es' | 'en' | 'auto' } = {}): ScreenplayReading {
  const lines = text.replace(/\r\n?/g, '\n').split('\n');
  const pageOfLine: number[] = []; { let p = 1; for (const l of lines) { p += (l.match(/\f/g) ?? []).length; pageOfLine.push(p); } }
  const hasFF = pageOfLine[pageOfLine.length - 1] > 1;
  // «CHICO (Cont)» is a cue with an extension whatever the case of the extension
  const clean = lines.map(l => l.replace(/\f/g, '').replace(/^(\s*\p{Lu}[\p{Lu}\p{N} .'’\-]*?\s*)\(\s*(v\.?o\.?|o\.?s\.?|o\.?c\.?|cont'?d?|off|super|filtro|filter)([^)]*)\)\s*$/iu, (_m, a, b, c) => `${a}(${String(b).toUpperCase()}${c})`));
  const els = parseScript(clean.join('\n'), isSlugline);
  const pageAt = (ln: number) => hasFF ? pageOfLine[ln] : Math.floor(ln / 55) + 1;

  // scenes: from each heading to the next
  const heads = els.filter(e => e.type === 'scene_heading');
  const scenes: ScriptScene[] = [];
  const bounds = heads.map(h => h.line);
  const termHits = new Map<string, CameraTerm>();
  const hit = (term: string, kind: CameraTerm['kind'], scene: number, sample: string) => { const k = kind + '|' + term.toUpperCase(); const c = termHits.get(k) ?? { term: term.toUpperCase(), kind, count: 0, scenes: [], sample: sample.trim().slice(0, 120) }; c.count++; if (!c.scenes.includes(scene)) c.scenes.push(scene); termHits.set(k, c); };
  const charMap = new Map<string, ScriptCharacter>();
  const chr = (n: string) => charMap.get(n) ?? charMap.set(n, { name: n, cues: 0, dialogueLines: 0, words: 0, share: 0, parentheticals: [], extensions: {}, firstScene: 0, lastScene: 0, scenes: 0 }).get(n)!;
  const sceneSeen = new Map<string, Set<number>>();
  const transitionsAll = new Map<string, number>();
  const capsInAction = new Map<string, { n: number; sample: string }>();

  const sliceFor = (si: number) => { const from = bounds[si], to = si + 1 < bounds.length ? bounds[si + 1] - 1 : lines.length - 1; return [from, to] as [number, number]; };
  heads.forEach((h, si) => {
    const [from, to] = sliceFor(si), inScene = els.filter(e => e.line >= from && e.line <= to);
    const sc: ScriptScene = { index: si + 1, heading: parseHeading(h.text), lines: [from, to], pages: [pageAt(from), pageAt(to)], cast: [], actionBlocks: 0, dialogueLines: 0, parentheticals: 0, speechWords: 0, actionWords: 0, dialogueShare: 0, camera: [], transitions: [], tension: null };
    let prevAction = false; const cast = new Set<string>();
    for (const e of inScene) {
      if (e.type === 'action') { if (!prevAction) sc.actionBlocks++; sc.actionWords += wordsOf(e.text); }
      if (e.type === 'dialogue') { sc.dialogueLines++; const w = wordsOf(e.text); sc.speechWords += w; if (e.speaker) { const c = chr(e.speaker); c.dialogueLines++; c.words += w; } }
      if (e.type === 'character' && e.speaker) { const base = e.speaker.replace(EXT_RE, '').trim(), c = chr(base); c.cues++; cast.add(base); const x = EXT_RE.exec(e.text); if (x) { const k = x[1].toUpperCase().replace(/\./g, ''); c.extensions[k] = (c.extensions[k] ?? 0) + 1; } if (!(sceneSeen.get(base) ?? sceneSeen.set(base, new Set()).get(base)!).has(si + 1)) { sceneSeen.get(base)!.add(si + 1); } }
      if (e.type === 'parenthetical') { sc.parentheticals++; if (e.speaker) chr(e.speaker.replace(EXT_RE, '').trim()).parentheticals.push({ text: e.text.replace(/^\(|\)$/g, '').trim(), scene: si + 1 }); }
      if (e.type === 'transition') sc.transitions.push(e.text);
      prevAction = e.type === 'action';
      // camera / film vocabulary: in everything that is not speech
      if (e.type !== 'dialogue' && e.type !== 'character' && e.type !== 'scene_heading') {
        const found: { term: string; kind: CameraTerm['kind']; a: number; b: number }[] = [];
        for (const g of lexRes) for (const it of g.items) { const m = it.re.exec(e.text); if (m) found.push({ term: m[1], kind: g.kind, a: m.index + m[0].indexOf(m[1]), b: m.index + m[0].indexOf(m[1]) + m[1].length }); }
        for (const f of found) if (!found.some(o => o !== f && o.a <= f.a && o.b >= f.b && (o.b - o.a) > (f.b - f.a))) { hit(f.term, f.kind, si + 1, e.text); if (!sc.camera.includes(f.term.toUpperCase())) sc.camera.push(f.term.toUpperCase()); }      // the longest term wins: «PLANO DETALLE» is not also «DETALLE»
      }
      // capitals inside action, outside the list: marked terms
      if (e.type === 'action' || e.type === 'insert') for (const m of e.text.matchAll(/(?<![\p{L}])(\p{Lu}[\p{Lu}'’-]{2,}(?:\s+\p{Lu}[\p{Lu}'’-]{2,}){0,3})(?![\p{L}])/gu)) { const t = m[1].trim(); const c = capsInAction.get(t) ?? { n: 0, sample: e.text.trim().slice(0, 120) }; c.n++; capsInAction.set(t, c); }
    }
    sc.cast = [...cast]; sc.dialogueShare = sc.speechWords + sc.actionWords ? Math.round(sc.speechWords / (sc.speechWords + sc.actionWords) * 100) / 100 : 0;
    scenes.push(sc);
  });
  for (const e of els) if (e.type === 'transition') { const k = e.text.toUpperCase().replace(/[:.]+$/, ''); transitionsAll.set(k, (transitionsAll.get(k) ?? 0) + 1); }
  // character spans
  const totalWords = [...charMap.values()].reduce((a, c) => a + c.words, 0) || 1;
  for (const c of charMap.values()) { const sc = [...(sceneSeen.get(c.name) ?? [])].sort((a, b) => a - b); c.scenes = sc.length; c.firstScene = sc[0] ?? 0; c.lastScene = sc[sc.length - 1] ?? 0; c.share = Math.round(c.words / totalWords * 100) / 100; }
  // a cue made of digits or punctuation is a page number or a stray mark, not a character
  const characters = [...charMap.values()].filter(c => c.cues >= 1 && /\p{L}{2}/u.test(c.name)).sort((a, b) => b.words - a.words);

  // places and times
  const placeMap = new Map<string, ScriptPlace>(); const timeOfDay: Record<string, number> = {};
  for (const sc of scenes) { const k = sc.heading.place.toUpperCase(); const p = placeMap.get(k) ?? placeMap.set(k, { place: sc.heading.place, scenes: [], intExt: [], times: {}, subPlaces: [] }).get(k)!; p.scenes.push(sc.index); if (sc.heading.intExt && !p.intExt.includes(sc.heading.intExt)) p.intExt.push(sc.heading.intExt); if (sc.heading.timeClass) { p.times[sc.heading.timeClass] = (p.times[sc.heading.timeClass] ?? 0) + 1; timeOfDay[sc.heading.timeClass] = (timeOfDay[sc.heading.timeClass] ?? 0) + 1; } if (sc.heading.subPlace && !p.subPlaces.includes(sc.heading.subPlace)) p.subPlaces.push(sc.heading.subPlace); }

  // marked terms the lists do not name and that are not characters
  const known = new Set([...termHits.values()].map(t => t.term)), names = new Set(characters.map(c => c.name.toUpperCase()));
  const learnedTerms = [...capsInAction].filter(([t, c]) => c.n >= 2 && !known.has(t) && !names.has(t) && !/^(INT|EXT|THE|AND|DE|LA|EL)$/.test(t) && !t.split(' ').every(w => names.has(w))).sort((a, b) => b[1].n - a[1].n).slice(0, 20).map(([term, c]) => ({ term, count: c.n, sample: c.sample }));

  // the engine over the same text
  const engine = analyzeNodes(text, { language: opts.language });
  const NPe = Math.max(1, engine.layers), totalLines = Math.max(1, lines.length);
  for (const sc of scenes) { const a = Math.max(1, Math.min(NPe, Math.ceil(sc.lines[0] / totalLines * NPe))), b = Math.max(a, Math.min(NPe, Math.ceil(sc.lines[1] / totalLines * NPe))), v = engine.tension.curve.filter(x => x.page >= a && x.page <= b).map(x => x.tension); sc.tension = v.length ? Math.round(v.reduce((x, y) => x + y, 0) / v.length) : null; }

  // four parts by weight in lines
  const acts: ScreenplayReading['acts'] = []; { const tot = scenes.reduce((a, s) => a + (s.lines[1] - s.lines[0] + 1), 0) || 1; let acc = 0, start = 1; const cuts = [0.25, 0.5, 0.75, 1], names2 = ['I', 'IIa', 'IIb', 'III'];
    scenes.forEach((s, i) => { acc += s.lines[1] - s.lines[0] + 1; const ci = acts.length; if (ci < 4 && (acc / tot >= cuts[ci] - 1e-9 || i === scenes.length - 1)) { const seg = scenes.slice(start - 1, i + 1), peak = seg.filter(x => x.tension !== null).sort((a, b) => (b.tension ?? 0) - (a.tension ?? 0))[0]; acts.push({ part: names2[ci], scenes: [start, i + 1], peakScene: peak?.index ?? null }); start = i + 2; } }); }

  const speech = scenes.reduce((a, s) => a + s.speechWords, 0), action = scenes.reduce((a, s) => a + s.actionWords, 0), pages = hasFF ? pageOfLine[pageOfLine.length - 1] : Math.max(1, Math.round(totalLines / 55));
  const classified = els.filter(e => e.type !== 'blank' && e.type !== 'action').length / Math.max(1, els.filter(e => e.type !== 'blank').length);
  const confidence = Math.round(Math.min(1, (scenes.length >= 1 ? 0.5 : 0) + Math.min(0.3, characters.length * 0.05) + Math.min(0.2, classified)) * 100) / 100;
  return {
    isScreenplay: scenes.length >= 1 && characters.length >= 1, confidence,
    scenes, characters, places: [...placeMap.values()].sort((a, b) => b.scenes.length - a.scenes.length), timeOfDay,
    camera: [...termHits.values()].sort((a, b) => b.count - a.count), learnedTerms,
    transitions: [...transitionsAll].map(([text, count]) => ({ text, count })).sort((a, b) => b.count - a.count),
    stats: { pages, minutes: pages, scenes: scenes.length, dialogueShare: speech + action ? Math.round(speech / (speech + action) * 100) / 100 : 0, speakers: characters.length, avgSceneLines: scenes.length ? Math.round(scenes.reduce((a, s) => a + (s.lines[1] - s.lines[0] + 1), 0) / scenes.length) : 0 },
    acts, engine,
  };
}
