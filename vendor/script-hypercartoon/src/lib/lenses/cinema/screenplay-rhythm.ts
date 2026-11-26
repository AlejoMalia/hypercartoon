/**
 * screenplay-rhythm.ts — the MATHS of screenplay↔novel adaptation.
 *
 * A screenplay is an architectural plan bound to time & space: 1 page ≈ 1 minute
 * of screen (~150-180 words standard). Reading that maths lets us decide how much
 * to EXPAND each scene into prose (action expands massively; dialogue ~1:1) and,
 * inversely, how much to COMPRESS a novel to fit a strict page budget.
 *
 * Deterministic parsing + maths; the AI then receives dynamic per-scene directives.
 */

export interface SceneStats {
  index: number;
  heading: string;
  location: string;
  timeOfDay: string;
  actionLines: number;
  dialogueLines: number;
  estMinutes: number;     // ~1 page (50 lines) = 1 minute
  estNovelWords: number;  // expansion-formula target for prose
  weight: number;         // 0-100 dramatic/temporal weight
  text: string;           // the raw scene text
}

const HEADING_RE = /^\s*(INT\.|EXT\.|INT\/EXT|EXT\/INT|ESC\.|ESCENA|SCENE)\b.*$/i;
const CUE_RE     = /^\s*[A-ZÁÉÍÓÚÑ0-9][A-ZÁÉÍÓÚÑ0-9 .'()\-]{1,30}\s*$/; // ALLCAPS character cue
const TRANSITION_RE = /\b(CORTE A|CORTE RÁPIDO A|SMASH CUT|CUT TO|FADE (IN|OUT)|DISOLVENCIA|MATCH CUT)\b/i;

// Expansion factors (W_novela = action·α + dialogue·β + introspection).
const ALPHA = 14;  // words per action line (sensory description blows up)
const BETA  = 7;   // words per dialogue line (near 1:1, only beats added)
const INTROSPECTION = 40; // free base for interior monologue per scene

/** Split a screenplay into scenes by scene headings. */
export function parseScenes(text: string): SceneStats[] {
  const lines = text.split('\n');
  const scenes: { heading: string; body: string[] }[] = [];
  let cur: { heading: string; body: string[] } | null = null;

  for (const line of lines) {
    if (HEADING_RE.test(line.trim())) {
      if (cur) scenes.push(cur);
      cur = { heading: line.trim(), body: [] };
    } else if (cur) {
      cur.body.push(line);
    } else {
      // preamble before first heading → its own pseudo-scene
      cur = { heading: '', body: [line] };
    }
  }
  if (cur) scenes.push(cur);

  return scenes.map((s, i) => statsFor(s.heading, s.body, i));
}

function statsFor(heading: string, body: string[], index: number): SceneStats {
  let location = '', timeOfDay = '';
  const h = heading.replace(HEADING_RE, m => m).trim();
  if (heading.includes(' - ') || heading.includes(' – ')) {
    const parts = heading.split(/\s[–-]\s/);
    location = (parts[0] || '').replace(/^(INT\.|EXT\.|INT\/EXT|EXT\/INT|ESC\.|ESCENA|SCENE)\s*/i, '').trim();
    timeOfDay = (parts[1] || '').trim();
  } else {
    location = h.replace(/^(INT\.|EXT\.|INT\/EXT|EXT\/INT|ESC\.|ESCENA|SCENE)\s*/i, '').trim();
  }

  let actionLines = 0, dialogueLines = 0;
  let inDialogue = false;
  for (const raw of body) {
    const t = raw.trim();
    if (!t) { inDialogue = false; continue; }
    if (CUE_RE.test(t) && t.split(/\s+/).length <= 5 && t === t.toUpperCase()) { inDialogue = true; continue; }
    if (inDialogue) dialogueLines++;
    else actionLines++;
  }

  const totalLines = actionLines + dialogueLines;
  const estMinutes = totalLines / 50;
  const estNovelWords = Math.round(actionLines * ALPHA + dialogueLines * BETA + INTROSPECTION);
  // weight: longer + more balanced scenes carry more; cap 100
  const weight = Math.min(100, Math.round(totalLines * 1.6));

  return { index, heading, location, timeOfDay, actionLines, dialogueLines, estMinutes, estNovelWords, weight, text: [heading, ...body].join('\n') };
}

/** Dynamic prose directives for ONE scene, derived from its maths. */
export function novelDirectivesFor(s: SceneStats, language: string): string[] {
  const d: string[] = [];
  if (s.actionLines > s.dialogueLines * 2) {
    d.push('Escena de ACCIÓN visual: expande masivamente entorno, cinemática del movimiento y sensaciones físicas. Descripciones largas, ralentiza el tiempo narrativo.');
  } else if (s.dialogueLines > s.actionLines * 2) {
    d.push('Escena de DIÁLOGO: ritmo rápido. Enfócate en el subtexto — lenguaje corporal, pausas y pensamientos entre líneas, no en describir el entorno.');
  } else {
    d.push('Escena MIXTA: equilibra descripción y diálogo, alternando acción sensorial con subtexto.');
  }
  if (s.estMinutes < 0.3) {
    d.push('Dura pocos segundos en pantalla: trátala como transición rápida, un solo párrafo fluido que conecte con lo siguiente.');
  } else if (s.estMinutes > 2.5) {
    d.push('Es una secuencia larga y de peso: desarróllala como un capítulo/escena completa con profundidad.');
  }
  if (s.location || s.timeOfDay) {
    d.push(`Ambienta al inicio: ${s.location}${s.timeOfDay ? ` durante ${s.timeOfDay}` : ''} — describe cómo se siente la luz y la atmósfera de ese lugar/momento.`);
  }
  d.push(`Objetivo orientativo: ~${s.estNovelWords} palabras de prosa para esta escena (no es un límite rígido).`);
  void language;
  return d;
}

/** Aggregate target word count for a block of scenes. */
export function targetWordsForScenes(scenes: SceneStats[]): number {
  return scenes.reduce((sum, s) => sum + s.estNovelWords, 0);
}

/** Compact rhythm brief for a block of scenes (for the generation prompt). */
export function rhythmBriefForBlock(scenes: SceneStats[], language: string): string {
  return scenes.map(s =>
    `· Escena ${s.index + 1} [${s.location}${s.timeOfDay ? '/' + s.timeOfDay : ''}] acción:${s.actionLines} diálogo:${s.dialogueLines} ~${s.estMinutes.toFixed(1)}min → ${novelDirectivesFor(s, language).join(' ')}`,
  ).join('\n');
}

// ── Inverse: novel → screenplay page budgeting ────────────────────────────────

export interface PageBudget {
  sourceWords: number;
  maxPages: number;
  targetScreenMinutes: number;
  compressionRatio: number;   // <1 = must compress
  guidance: string;
}

/** Compute the page budget when adapting a novel to a screenplay (max 120 pp). */
export function pageBudget(novelText: string, maxPages = 120): PageBudget {
  const sourceWords = novelText.trim().split(/\s+/).filter(Boolean).length;
  // a screenplay page ≈ 165 words of script; a novel page ≈ 300 words.
  const novelPages = sourceWords / 300;
  const targetPages = Math.min(maxPages, Math.max(20, Math.round(novelPages * 0.55)));
  const compressionRatio = Math.min(1, targetPages / Math.max(1, novelPages));
  const guidance = compressionRatio < 0.6
    ? 'COMPRESIÓN FUERTE: corta subtramas menores, fusiona escenas, convierte introspección larga en acción visible y diálogo con subtexto. Mantén solo lo que hace avanzar la trama.'
    : 'COMPRESIÓN MODERADA: condensa descripción en acotaciones breves; conserva las escenas clave y los giros.';
  return {
    sourceWords,
    maxPages: targetPages,
    targetScreenMinutes: targetPages,         // 1 page ≈ 1 minute
    compressionRatio: Math.round(compressionRatio * 100) / 100,
    guidance,
  };
}
