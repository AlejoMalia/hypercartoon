/**
 * script-parser.ts — classify every line of a screenplay by what it IS.
 *
 * WHY THIS EXISTS TWICE OVER
 * A screenplay is not prose: it is a typed document that happens to be stored
 * as text. Action, dialogue, a character cue and a transition look identical to
 * a plain-text reader, and that flattening costs twice.
 *
 *   1. THE MODEL reads an undifferentiated wall and has to re-derive the
 *      structure the format already encoded. Handing it a tagged script means
 *      it spends its attention on the drama instead of on parsing.
 *   2. WE cannot audit what we cannot count. Knowing a scene contains nine
 *      action blocks is what makes it possible to say "this scene got two
 *      frames and it needed more" — the coverage check is impossible without
 *      this classification.
 *
 * Everything here is deterministic: no AI, no cost, no variance between runs.
 *
 * The colours are the industry's own reading conventions, and are used both for
 * the colour-coded script we deliver and as the legend in the storyboard.
 */

export type ElementType =
  | 'scene_heading'
  | 'sub_heading'
  | 'action'
  | 'character'
  | 'dialogue'
  | 'parenthetical'
  | 'transition'
  | 'sfx'
  | 'music'
  | 'insert'
  | 'blank';

export interface ScriptElement {
  type: ElementType;
  text: string;
  /** 0-based line number in the source. */
  line: number;
  /** For dialogue and parentheticals: who is speaking. */
  speaker?: string;
}

/** Reading colours, one per element type. */
export const ELEMENT_COLOR: Record<ElementType, string> = {
  scene_heading: '#006400',   // dark green  — the spine of the script
  sub_heading:   '#00C853',   // light green — FLASHBACK, MONTAGE
  action:        '#B58900',   // gold        — what is seen (readable on white)
  character:     '#0D47A1',   // navy        — who speaks
  dialogue:      '#E91E63',   // pink        — what is said
  parenthetical: '#546E7A',   // grey        — how it is said
  transition:    '#FF9800',   // orange      — technical instruction
  sfx:           '#F44336',   // red         — sound
  music:         '#9C27B0',   // purple      — score
  insert:        '#00BCD4',   // cyan        — a specific visual
  blank:         '#000000',
};

export const ELEMENT_LABEL: Record<ElementType, string> = {
  scene_heading: 'Scene heading',
  sub_heading:   'Sub-heading',
  action:        'Action',
  character:     'Character',
  dialogue:      'Dialogue',
  parenthetical: 'Parenthetical',
  transition:    'Transition',
  sfx:           'Sound',
  music:         'Music',
  insert:        'Insert',
  blank:         '',
};

// ── Patterns ──────────────────────────────────────────────────────────────────
// Multilingual, because these markers stay in the author's language.

const SUB_HEADING_RE = /^\s*(FLASHBACK|FLASH-?BACK|FLASHFORWARD|MONTAJE|MONTAGE|SUEÑO|DREAM|SERIE DE|SERIES OF|INTERCUT|MÁS TARDE|LATER|CONTINUA|CONTINUOUS)\b/i;

const TRANSITION_RE = /^\s*(CUT TO|CORTE A|SMASH CUT|MATCH CUT|FADE (IN|OUT|TO)|FUNDIDO|ENCADENADO|DISSOLVE TO|WIPE TO|IRIS (IN|OUT)|BLACK|NEGRO|FIN|THE END|CONTINUARÁ|TO BE CONTINUED)\b.*:?\s*$/i;

const SFX_RE = /^\s*(SFX|FX|SOUND|SONIDO|EFECTO|EFFET|GERÄUSCH)\s*[:.\-]/i;
const MUSIC_RE = /^\s*(MUSIC|MÚSICA|MUSICA|MUSIQUE|MUSIK|SCORE|CANCIÓN|SONG)\s*[:.\-]/i;
const INSERT_RE = /^\s*(INSERT|INSERTO|PRIMER PLANO DE|CLOSE ON|CLOSE-?UP ON|ANGLE ON|DETALLE)\b/i;

const PARENTHETICAL_RE = /^\s*\(.*\)[.!?…]*\s*$/;       // writers close it with a full stop: «(Tras soltar la copa).»

/**
 * A character cue: a short, all-caps line introducing dialogue.
 *
 * The trailing extensions are matched explicitly because "ANA (V.O.)" must
 * still read as a cue, and the length ceiling keeps a shouted line of action
 * ("LA PUERTA SE ABRE DE GOLPE Y ENTRA CORRIENDO") from being mistaken for one.
 */
const CHARACTER_RE = /^\s{0,30}([\p{Lu}\p{N}][\p{Lu}\p{N} .'’\-]{0,38})\s*(\((?:V\.?O\.?|O\.?S\.?|O\.?C\.?|CONT'?D|CONT|OFF|SUPER|FILTRO|FILTER)[^)]*\))?\s*$/u;

/** Words that look like a cue but never are. */
const NOT_A_CHARACTER = new Set([
  'FADE IN', 'FADE OUT', 'CUT TO', 'THE END', 'FIN', 'CONTINUARÁ',
  'INT', 'EXT', 'FLASHBACK', 'MONTAJE', 'MONTAGE', 'INSERT', 'INSERTO',
]);

function isCharacterCue(line: string, nextLine: string): boolean {
  const m = CHARACTER_RE.exec(line);
  if (!m) return false;
  const name = m[1].trim();
  if (name.length < 2) return false;
  if (NOT_A_CHARACTER.has(name.replace(/[.:]/g, '').trim())) return false;
  // A cue exists to introduce speech. With nothing under it, it is a shouted
  // action line or a stray heading, not a character.
  return nextLine.trim().length > 0;
}

/**
 * Classify a script into typed elements.
 *
 * `isSceneHeading` is injected rather than re-implemented so the parser and the
 * scene splitter can never disagree about where a scene begins.
 */
export function parseScript(script: string, isSceneHeading: (line: string) => boolean): ScriptElement[] {
  const lines = script.replace(/\r\n?/g, '\n').split('\n');
  const out: ScriptElement[] = [];
  let speaker: string | undefined;
  let inDialogue = false;

  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    const text = raw.trim();

    if (!text) {
      out.push({ type: 'blank', text: '', line: i });
      inDialogue = false;                    // a blank line ends a speech
      continue;
    }

    // Order matters: the most specific patterns are tested first, because an
    // insert or a transition would otherwise be swallowed as action.
    if (isSceneHeading(raw))            { out.push({ type: 'scene_heading', text, line: i }); speaker = undefined; inDialogue = false; continue; }
    if (SUB_HEADING_RE.test(text))      { out.push({ type: 'sub_heading',   text, line: i }); inDialogue = false; continue; }
    if (TRANSITION_RE.test(text))       { out.push({ type: 'transition',    text, line: i }); inDialogue = false; continue; }
    if (SFX_RE.test(text))              { out.push({ type: 'sfx',           text, line: i }); inDialogue = false; continue; }
    if (MUSIC_RE.test(text))            { out.push({ type: 'music',         text, line: i }); inDialogue = false; continue; }
    if (INSERT_RE.test(text))           { out.push({ type: 'insert',        text, line: i }); inDialogue = false; continue; }

    if (inDialogue && PARENTHETICAL_RE.test(text)) {
      out.push({ type: 'parenthetical', text, line: i, speaker });
      continue;
    }

    if (isCharacterCue(raw, lines[i + 1] ?? '')) {
      speaker = CHARACTER_RE.exec(raw)![1].trim();
      out.push({ type: 'character', text, line: i, speaker });
      inDialogue = true;
      continue;
    }

    if (inDialogue) { out.push({ type: 'dialogue', text, line: i, speaker }); continue; }

    out.push({ type: 'action', text, line: i });
  }

  return out;
}

export interface ScriptStats {
  actionBlocks: number;
  /** Printed-line equivalents of the speech (words said ÷ 9): it does not depend on where a PDF wrapped a line, and an ellipsis alone is not a line. */
  dialogueLines: number;
  /** How many times a character begins to speak. */
  speeches: number;
  speakers: string[];
  transitions: number;
  sfx: number;
  music: number;
  inserts: number;
  /** Share of the scene's substantive lines that are dialogue, 0-1. */
  dialogueRatio: number;
}

/**
 * Count what a stretch of script contains.
 *
 * Action BLOCKS rather than lines: a paragraph of description is one thing to
 * stage, however many lines it wraps to, and the coverage audit compares frames
 * against things to stage.
 */
export function statsFor(elements: ScriptElement[]): ScriptStats {
  let actionBlocks = 0, dialogueWords = 0, speeches = 0, transitions = 0, sfx = 0, music = 0, inserts = 0;
  const speakers = new Set<string>();
  let prevWasAction = false;

  for (const el of elements) {
    switch (el.type) {
      case 'action':     if (!prevWasAction) actionBlocks++; break;
      case 'dialogue':   dialogueWords += (el.text.match(/\p{L}+/gu) ?? []).length; if (el.speaker) speakers.add(el.speaker); break;
      case 'character':  speeches++; if (el.speaker) speakers.add(el.speaker); break;
      case 'transition': transitions++; break;
      case 'sfx':        sfx++; break;
      case 'music':      music++; break;
      case 'insert':     inserts++; break;
    }
    prevWasAction = el.type === 'action';
  }

  const dialogueLines = Math.ceil(dialogueWords / 9), substantive = actionBlocks + dialogueLines;
  return {
    actionBlocks, dialogueLines, speeches, transitions, sfx, music, inserts,
    speakers: [...speakers],
    dialogueRatio: substantive ? dialogueLines / substantive : 0,
  };
}

/** Re-render a stretch of script with its elements tagged, for the model. */
export function taggedText(elements: ScriptElement[]): string {
  return elements
    .filter(e => e.type !== 'blank')
    .map(e => `[${ELEMENT_LABEL[e.type].toUpperCase()}]${e.speaker && e.type !== 'character' ? ` (${e.speaker})` : ''} ${e.text}`)
    .join('\n');
}
