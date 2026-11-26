/**
 * scene-splitter.ts — cut a screenplay into its scenes, by its own sluglines.
 *
 * WHY THIS REPLACED BLIND CHUNKING
 * The extractor used to slice the script every 16 000 characters with an
 * overlap, which had two costs: a scene could be split across two requests and
 * analysed with half its context missing, and a scene sitting on a seam was
 * handed to the model twice and came back duplicated.
 *
 * A screenplay already declares its own boundaries. Cutting on the slugline
 * gives every scene to the model whole, exactly once — which is both cheaper
 * and the only way an analysis of "how much tension does this scene carry"
 * means anything, since that judgement needs the entire scene.
 *
 * MULTILINGUAL BY NECESSITY
 * Sluglines are one of the few parts of a screenplay that stay in the author's
 * language. INT./EXT. is near-universal, but Italian writes EST., German uses
 * INNEN/AUSSEN, and plenty of writers spell INTERIOR/EXTERIOR out in full.
 */

export interface RawScene {
  /** 1-based position in the script. */
  index: number;
  /** The slugline as written, e.g. "INT. COCINA - DÍA". */
  heading: string;
  /** Everything under the slugline, up to the next one. */
  body: string;
  /** Characters from the start of the script — used to place the scene. */
  offset: number;
}

/**
 * A slugline: an interior/exterior marker at the start of a line.
 *
 * The abbreviations are matched with an optional period because plenty of
 * scripts write "INT " or "EXT-", and the full words are matched too because
 * they are common outside English-language practice.
 */
const SLUG_RE = new RegExp(
  '^[ \\t]*' +
  // Optional scene label before the marker. Plenty of scripts number scenes
  // ("12. INT. …") and Spanish/French/German practice often spells it out
  // ("ESCENA 12 — INT. …"), which is a heading we would otherwise walk past.
  '(?:(?:ESCENA|SCENE|SCÈNE|SCENA|SZENE|CENA)\\s*)?' +
  '(?:\\d{1,4}\\s*[.):\\-–—]?[ \\t]*)?' +
  // Longest forms FIRST. Alternation is ordered, so listing EXT before
  // EXTÉRIEUR would match the abbreviation and leave "ÉRIEUR…" as the rest,
  // which then fails the heading check.
  '(' +
    '(?:INTERIOR|EXTERIOR|INTERIEUR|INTÉRIEUR|EXTERIEUR|EXTÉRIEUR|INTERNO|ESTERNO)\\b' +
    '|(?:INNEN|AUSSEN|AUSS)\\b' +                 // de
    '|(?:INT\\.?\\s*\\/\\s*EXT|EXT\\.?\\s*\\/\\s*INT|I\\s*\\/\\s*E)\\b' +
    '|(?:INT|EXT)\\b' +                           // en/es/fr/pt
    '|EST\\b' +                                   // it: esterno
  ')' +
  '([^\\n]*)',
  'im',
);

/**
 * Is what follows the marker a heading, or a sentence that merely begins with
 * the word? A slugline is either punctuated (INT. / EXT- / I/E:) or continues
 * in capitals (EXT PARQUE - DIA); "Interior designers arrived at noon…" is
 * neither, and was being swallowed as a scene.
 *
 * This is checked in code rather than in the pattern because the pattern is
 * case-insensitive — inside it, a negated [a-z] would reject capitals too.
 */
function looksLikeHeading(rest: string): boolean {
  if (/^[.\-–—:/]/.test(rest)) return true;
  return /^\s/.test(rest) && !/\p{Ll}/u.test(rest);
}

/** The same, global, so every slugline in the script can be found. */
const SLUG_RE_G = new RegExp(SLUG_RE.source, 'gim');

/** Is this line a slugline? Exported so the analyser can sanity-check a heading. */
export function isSlugline(line: string): boolean {
  const m = SLUG_RE.exec(line);
  return m !== null && looksLikeHeading(m[2] ?? '');
}

/**
 * Split a script into scenes.
 *
 * When no slugline is found at all — prose treatments, a novel, a badly
 * formatted export — the whole text comes back as a single scene rather than
 * nothing, so the caller can still fall back to a paragraph-based breakdown
 * instead of failing on a document the customer legitimately uploaded.
 */
export function splitScenes(script: string): RawScene[] {
  const text = script.replace(/\r\n?/g, '\n');
  const marks: { heading: string; start: number }[] = [];

  for (const m of text.matchAll(SLUG_RE_G)) {
    if (!looksLikeHeading(m[2] ?? '')) continue;
    const heading = m[0].trim();
    if (heading.length > 120) continue;   // a heading, not a paragraph
    marks.push({ heading, start: m.index ?? 0 });
  }

  if (marks.length === 0) {
    return [{ index: 1, heading: '', body: text.trim(), offset: 0 }];
  }

  return marks.map((mk, i) => {
    const end = i + 1 < marks.length ? marks[i + 1].start : text.length;
    const block = text.slice(mk.start, end);
    const body = block.slice(mk.heading.length).trim();
    return { index: i + 1, heading: mk.heading, body, offset: mk.start };
  }).filter(s => s.body.length > 0 || s.heading.length > 0);
}

/**
 * Split a scene that is too large for one request into ordered parts.
 *
 * Rare — a scene over ~12 000 characters is unusual — but a single unbroken
 * action sequence can reach it, and silently truncating one would be exactly
 * the "it skipped part of my script" failure this tool exists to avoid. Parts
 * break on blank lines so a paragraph is never cut mid-sentence.
 */
export function splitLongScene(body: string, maxChars = 12000): string[] {
  if (body.length <= maxChars) return [body];
  // Prefer blank lines, but a single unbroken block can exceed the budget on
  // its own (an action sequence written without paragraph breaks), so oversized
  // pieces are broken again on sentence ends. Truncating instead would be the
  // exact "it skipped part of my script" failure this tool exists to avoid.
  const hardBreak = new RegExp(`[\\s\\S]{1,${maxChars}}(?=[.!?…]\\s|$)`, 'g');
  const pieces = body.split(/\n\s*\n/).flatMap(p =>
    p.length <= maxChars ? [p] : (p.match(hardBreak) ?? [p]));

  const parts: string[] = [];
  let cur = '';
  for (const p of pieces) {
    if (cur && cur.length + p.length + 2 > maxChars) { parts.push(cur); cur = ''; }
    cur += (cur ? '\n\n' : '') + p;
  }
  if (cur) parts.push(cur);
  return parts;
}
