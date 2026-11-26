var __defProp = Object.defineProperty;
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};

// src/lib/nodes/screenplay.ts
var screenplay_exports = {};
__export(screenplay_exports, {
  analyzeScreenplay: () => analyzeScreenplay,
  parseHeading: () => parseHeading
});

// src/lib/storyboard/script-parser.ts
var script_parser_exports = {};
__export(script_parser_exports, {
  ELEMENT_COLOR: () => ELEMENT_COLOR,
  ELEMENT_LABEL: () => ELEMENT_LABEL,
  parseScript: () => parseScript,
  statsFor: () => statsFor,
  taggedText: () => taggedText
});
var ELEMENT_COLOR = {
  scene_heading: "#006400",
  // dark green  — the spine of the script
  sub_heading: "#00C853",
  // light green — FLASHBACK, MONTAGE
  action: "#B58900",
  // gold        — what is seen (readable on white)
  character: "#0D47A1",
  // navy        — who speaks
  dialogue: "#E91E63",
  // pink        — what is said
  parenthetical: "#546E7A",
  // grey        — how it is said
  transition: "#FF9800",
  // orange      — technical instruction
  sfx: "#F44336",
  // red         — sound
  music: "#9C27B0",
  // purple      — score
  insert: "#00BCD4",
  // cyan        — a specific visual
  blank: "#000000"
};
var ELEMENT_LABEL = {
  scene_heading: "Scene heading",
  sub_heading: "Sub-heading",
  action: "Action",
  character: "Character",
  dialogue: "Dialogue",
  parenthetical: "Parenthetical",
  transition: "Transition",
  sfx: "Sound",
  music: "Music",
  insert: "Insert",
  blank: ""
};
var SUB_HEADING_RE = /^\s*(FLASHBACK|FLASH-?BACK|FLASHFORWARD|MONTAJE|MONTAGE|SUEÑO|DREAM|SERIE DE|SERIES OF|INTERCUT|MÁS TARDE|LATER|CONTINUA|CONTINUOUS)\b/i;
var TRANSITION_RE = /^\s*(CUT TO|CORTE A|SMASH CUT|MATCH CUT|FADE (IN|OUT|TO)|FUNDIDO|ENCADENADO|DISSOLVE TO|WIPE TO|IRIS (IN|OUT)|BLACK|NEGRO|FIN|THE END|CONTINUARÁ|TO BE CONTINUED)\b.*:?\s*$/i;
var SFX_RE = /^\s*(SFX|FX|SOUND|SONIDO|EFECTO|EFFET|GERÄUSCH)\s*[:.\-]/i;
var MUSIC_RE = /^\s*(MUSIC|MÚSICA|MUSICA|MUSIQUE|MUSIK|SCORE|CANCIÓN|SONG)\s*[:.\-]/i;
var INSERT_RE = /^\s*(INSERT|INSERTO|PRIMER PLANO DE|CLOSE ON|CLOSE-?UP ON|ANGLE ON|DETALLE)\b/i;
var PARENTHETICAL_RE = /^\s*\(.*\)[.!?…]*\s*$/;
var CHARACTER_RE = /^\s{0,30}([\p{Lu}\p{N}][\p{Lu}\p{N} .'’\-]{0,38})\s*(\((?:V\.?O\.?|O\.?S\.?|O\.?C\.?|CONT'?D|CONT|OFF|SUPER|FILTRO|FILTER)[^)]*\))?\s*$/u;
var NOT_A_CHARACTER = /* @__PURE__ */ new Set([
  "FADE IN",
  "FADE OUT",
  "CUT TO",
  "THE END",
  "FIN",
  "CONTINUAR\xC1",
  "INT",
  "EXT",
  "FLASHBACK",
  "MONTAJE",
  "MONTAGE",
  "INSERT",
  "INSERTO"
]);
function isCharacterCue(line, nextLine) {
  const m = CHARACTER_RE.exec(line);
  if (!m) return false;
  const name = m[1].trim();
  if (name.length < 2) return false;
  if (NOT_A_CHARACTER.has(name.replace(/[.:]/g, "").trim())) return false;
  return nextLine.trim().length > 0;
}
function parseScript(script, isSceneHeading) {
  const lines = script.replace(/\r\n?/g, "\n").split("\n");
  const out = [];
  let speaker;
  let inDialogue = false;
  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    const text = raw.trim();
    if (!text) {
      out.push({ type: "blank", text: "", line: i });
      inDialogue = false;
      continue;
    }
    if (isSceneHeading(raw)) {
      out.push({ type: "scene_heading", text, line: i });
      speaker = void 0;
      inDialogue = false;
      continue;
    }
    if (SUB_HEADING_RE.test(text)) {
      out.push({ type: "sub_heading", text, line: i });
      inDialogue = false;
      continue;
    }
    if (TRANSITION_RE.test(text)) {
      out.push({ type: "transition", text, line: i });
      inDialogue = false;
      continue;
    }
    if (SFX_RE.test(text)) {
      out.push({ type: "sfx", text, line: i });
      inDialogue = false;
      continue;
    }
    if (MUSIC_RE.test(text)) {
      out.push({ type: "music", text, line: i });
      inDialogue = false;
      continue;
    }
    if (INSERT_RE.test(text)) {
      out.push({ type: "insert", text, line: i });
      inDialogue = false;
      continue;
    }
    if (inDialogue && PARENTHETICAL_RE.test(text)) {
      out.push({ type: "parenthetical", text, line: i, speaker });
      continue;
    }
    if (isCharacterCue(raw, lines[i + 1] ?? "")) {
      speaker = CHARACTER_RE.exec(raw)[1].trim();
      out.push({ type: "character", text, line: i, speaker });
      inDialogue = true;
      continue;
    }
    if (inDialogue) {
      out.push({ type: "dialogue", text, line: i, speaker });
      continue;
    }
    out.push({ type: "action", text, line: i });
  }
  return out;
}
function statsFor(elements) {
  let actionBlocks = 0, dialogueWords = 0, speeches = 0, transitions = 0, sfx = 0, music = 0, inserts = 0;
  const speakers = /* @__PURE__ */ new Set();
  let prevWasAction = false;
  for (const el of elements) {
    switch (el.type) {
      case "action":
        if (!prevWasAction) actionBlocks++;
        break;
      case "dialogue":
        dialogueWords += (el.text.match(/\p{L}+/gu) ?? []).length;
        if (el.speaker) speakers.add(el.speaker);
        break;
      case "character":
        speeches++;
        if (el.speaker) speakers.add(el.speaker);
        break;
      case "transition":
        transitions++;
        break;
      case "sfx":
        sfx++;
        break;
      case "music":
        music++;
        break;
      case "insert":
        inserts++;
        break;
    }
    prevWasAction = el.type === "action";
  }
  const dialogueLines = Math.ceil(dialogueWords / 9), substantive = actionBlocks + dialogueLines;
  return {
    actionBlocks,
    dialogueLines,
    speeches,
    transitions,
    sfx,
    music,
    inserts,
    speakers: [...speakers],
    dialogueRatio: substantive ? dialogueLines / substantive : 0
  };
}
function taggedText(elements) {
  return elements.filter((e) => e.type !== "blank").map((e) => `[${ELEMENT_LABEL[e.type].toUpperCase()}]${e.speaker && e.type !== "character" ? ` (${e.speaker})` : ""} ${e.text}`).join("\n");
}

// src/lib/storyboard/scene-splitter.ts
var scene_splitter_exports = {};
__export(scene_splitter_exports, {
  isSlugline: () => isSlugline,
  splitLongScene: () => splitLongScene,
  splitScenes: () => splitScenes
});
var SLUG_RE = new RegExp(
  "^[ \\t]*(?:(?:ESCENA|SCENE|SC\xC8NE|SCENA|SZENE|CENA)\\s*)?(?:\\d{1,4}\\s*[.):\\-\u2013\u2014]?[ \\t]*)?((?:INTERIOR|EXTERIOR|INTERIEUR|INT\xC9RIEUR|EXTERIEUR|EXT\xC9RIEUR|INTERNO|ESTERNO)\\b|(?:INNEN|AUSSEN|AUSS)\\b|(?:INT\\.?\\s*\\/\\s*EXT|EXT\\.?\\s*\\/\\s*INT|I\\s*\\/\\s*E)\\b|(?:INT|EXT)\\b|EST\\b)([^\\n]*)",
  "im"
);
function looksLikeHeading(rest) {
  if (/^[.\-–—:/]/.test(rest)) return true;
  return /^\s/.test(rest) && !/\p{Ll}/u.test(rest);
}
var SLUG_RE_G = new RegExp(SLUG_RE.source, "gim");
function isSlugline(line) {
  const m = SLUG_RE.exec(line);
  return m !== null && looksLikeHeading(m[2] ?? "");
}
function splitScenes(script) {
  const text = script.replace(/\r\n?/g, "\n");
  const marks = [];
  for (const m of text.matchAll(SLUG_RE_G)) {
    if (!looksLikeHeading(m[2] ?? "")) continue;
    const heading = m[0].trim();
    if (heading.length > 120) continue;
    marks.push({ heading, start: m.index ?? 0 });
  }
  if (marks.length === 0) {
    return [{ index: 1, heading: "", body: text.trim(), offset: 0 }];
  }
  return marks.map((mk, i) => {
    const end = i + 1 < marks.length ? marks[i + 1].start : text.length;
    const block = text.slice(mk.start, end);
    const body = block.slice(mk.heading.length).trim();
    return { index: i + 1, heading: mk.heading, body, offset: mk.start };
  }).filter((s) => s.body.length > 0 || s.heading.length > 0);
}
function splitLongScene(body, maxChars = 12e3) {
  if (body.length <= maxChars) return [body];
  const hardBreak = new RegExp(`[\\s\\S]{1,${maxChars}}(?=[.!?\u2026]\\s|$)`, "g");
  const pieces = body.split(/\n\s*\n/).flatMap((p) => p.length <= maxChars ? [p] : p.match(hardBreak) ?? [p]);
  const parts = [];
  let cur = "";
  for (const p of pieces) {
    if (cur && cur.length + p.length + 2 > maxChars) {
      parts.push(cur);
      cur = "";
    }
    cur += (cur ? "\n\n" : "") + p;
  }
  if (cur) parts.push(cur);
  return parts;
}

// src/lib/nodes/lexicon.ts
var lexicon_exports = {};
__export(lexicon_exports, {
  LEXICONS: () => LEXICONS,
  detectLang: () => detectLang
});
var ES_STOP = "el la los las un una unos unas de del al a en por con y o u e que se su sus lo le les me te mi tu nos os mis tus como m\xE1s muy no s\xED si ni sino pero mas para entre hasta desde hacia sobre tras ante bajo este esta esto estos estas ese esa eso esos esas aquel aquella aquello cuando donde quien quienes cual cuales cuyo todo toda todos todas otro otra otros otras mismo misma ya ahora entonces despu\xE9s antes siempre nunca tambi\xE9n as\xED aqu\xED all\xED all\xE1 era eran fue fueron ser es son est\xE1 est\xE1n estaba hab\xEDa han ha he hay hab\xEDan tiene ten\xEDa hace hac\xEDa puede pod\xEDa dijo digo dice ver vi vio yo \xE9l ella ellos ellas nosotros usted ustedes m\xED ti qu\xE9 c\xF3mo cu\xE1ndo d\xF3nde qui\xE9n tan tanto pues aun a\xFAn solo s\xF3lo cada algo nada alguien nadie uno dos tres ah\xED tal vez aunque porque mientras durante seg\xFAn cuyas sin hacer hizo van vamos voy vas".split(" ");
var EN_STOP = "the a an and or but of to in on at for from with by as is was were be been he she it they we you i his her its their our my your him them me us this that these those not no so if then than when while which who whom what where how there here had has have do did does would could should will can may might also just very more most some any all each other into out up down over under after before about against between through during again once only own same too said say says".split(" ");
var ES = {
  stop: new Set(ES_STOP),
  months: ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"],
  joiners: /* @__PURE__ */ new Set(["de", "del", "la", "las", "los", "el"]),
  possessive: /[’']s$/,
  placeCues: new Set("capital reino reinos pueblo poblado ciudad castillo aldea palacio muros alrededores frontera territorio tierra norte sur este oeste dirige dirigi\xF3 dirigieron dirig\xEDan viaje camino lleg\xF3 llegada llegaron march\xF3 parti\xF3 abandon\xF3 rumbo regi\xF3n provincia imperio condado puerto isla bosque monta\xF1a monta\xF1as r\xEDo mar planeta aterrizar habitantes ej\xE9rcito gobernantes gobernante corona trono era eras apogeo acuerdo".split(" ")),
  personCues: new Set("dijo pregunt\xF3 respondi\xF3 exclam\xF3 grit\xF3 susurr\xF3 contest\xF3 a\xF1adi\xF3 murmur\xF3 replic\xF3 coment\xF3 afirm\xF3 orden\xF3 pidi\xF3 secund\xF3 pens\xF3 sinti\xF3 mir\xF3 miraba sonri\xF3 asinti\xF3 ojos mirada brazo brazos mano manos rostro cabeza voz hombre mujer joven padre madre hijo hija hermano amigo herido soldado rey reina se\xF1or majestad".split(" ")),
  speech: new Set("dijo dijeron pregunt\xF3 preguntaron respondi\xF3 respondieron exclam\xF3 grit\xF3 susurr\xF3 contest\xF3 a\xF1adi\xF3 murmur\xF3 replic\xF3 coment\xF3 afirm\xF3 orden\xF3 pidi\xF3 secund\xF3".split(" ")),
  placePreps: /* @__PURE__ */ new Set(["en", "desde", "hacia", "hasta"]),
  toolPreps: /* @__PURE__ */ new Set(["con", "mediante", "sin"]),
  preVerb: new Set("se lo la le les me te nos no que y ya \xE9l ella ellos ellas".split(" ")),
  determiners: new Set("el la los las un una unos unas su sus mi mis tu tus del al este esta ese esa aquel aquella estos estas esos esas".split(" ")),
  verbish: /(?:ó|aron|ieron|ió|ando|iendo|ían|aba|aban|ado|ido|ar|er|ir)$/,
  titles: /* @__PURE__ */ new Set(["rey", "reina", "monarca", "presidente", "capit\xE1n", "doctor", "general", "pr\xEDncipe", "duque", "conde", "emperador"]),
  address: /* @__PURE__ */ new Set(["se\xF1or", "amo", "majestad", "maestro", "capit\xE1n", "dios"]),
  addressPoss: /* @__PURE__ */ new Set(["mi", "su", "nuestro", "vuestro", "oh"]),
  sections: { front: ["introduccion", "prologo", "prefacio", "prologodelautor", "prologodeledicion", "dedicatoria", "epigrafe", "notadelautor", "notaalolector", "advertencia", "presentacion", "indice", "contenido", "creditos", "derechos", "agradecimientos", "sobreelautor", "personajes"], back: ["agradecimientos", "notas", "bibliografia", "fuentes", "indiceanalitico", "glosario", "apendice", "sobreelautor", "posfacio", "entrevistas"] },
  roleWords: ["rey", "reina", "monarca", "majestad", "bestia", "monstruo", "presidente", "pr\xEDncipe", "asesor"],
  entityWords: new Set("rey monarca bestia monstruo asesor soldados soldado reina pr\xEDncipe guardias criado sirviente".split(" ")),
  sluglineWord: /\b(INT|EXT)\b/
};
var EN = {
  stop: new Set(EN_STOP),
  months: ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"],
  joiners: /* @__PURE__ */ new Set(["of"]),
  possessive: /[’']s$/,
  placeCues: new Set("capital kingdom kingdoms village town city castle palace walls outskirts border territory land north south east west headed traveled journey road arrived arrival left region province empire county port island forest mountain mountains river sea planet landed inhabitants army ruler crown throne era age headquarters campus office building".split(" ")),
  personCues: new Set("said asked replied answered shouted whispered added murmured told thought felt looked smiled nodded eyes gaze arm arms hand hands face head voice man woman young father mother son daughter brother friend wounded soldier king queen lord majesty".split(" ")),
  speech: new Set("said asked replied answered shouted whispered added murmured told exclaimed insisted explained recalled".split(" ")),
  placePreps: /* @__PURE__ */ new Set(["in", "at", "to", "from", "near", "into", "toward", "towards", "outside", "inside"]),
  toolPreps: /* @__PURE__ */ new Set(["with", "using", "without"]),
  preVerb: new Set("he she it they we i to not then and who".split(" ")),
  determiners: new Set("the a an his her its their my your our this that these those".split(" ")),
  verbish: /(?:ed|ing)$/,
  titles: /* @__PURE__ */ new Set(["king", "queen", "monarch", "president", "captain", "doctor", "general", "prince", "duke", "count", "emperor", "dr", "mr", "mrs"]),
  address: /* @__PURE__ */ new Set(["lord", "master", "majesty", "sir", "god"]),
  addressPoss: /* @__PURE__ */ new Set(["my", "your", "his", "our", "oh"]),
  sections: { front: ["introduction", "prologue", "foreword", "preface", "dedication", "epigraph", "authorsnote", "notetothereader", "acknowledgments", "acknowledgements", "contents", "tableofcontents", "copyright", "abouttheauthor", "characters", "cast", "fromtheauthor"], back: ["notes", "sources", "bibliography", "index", "appendix", "glossary", "afterword", "acknowledgments", "acknowledgements", "abouttheauthor", "interviews", "photocredits"] },
  roleWords: ["king", "queen", "monarch", "majesty", "beast", "monster", "president", "prince", "adviser"],
  entityWords: new Set("king monarch beast monster adviser soldiers soldier queen prince guards servant".split(" ")),
  sluglineWord: /\b(INT|EXT)\b/
};
var AUTO = {
  stop: /* @__PURE__ */ new Set(),
  months: [],
  joiners: /* @__PURE__ */ new Set(),
  possessive: /[’']s$/,
  placeCues: /* @__PURE__ */ new Set(),
  personCues: /* @__PURE__ */ new Set(),
  speech: /* @__PURE__ */ new Set(),
  placePreps: /* @__PURE__ */ new Set(),
  toolPreps: /* @__PURE__ */ new Set(),
  preVerb: /* @__PURE__ */ new Set(),
  determiners: /* @__PURE__ */ new Set(),
  verbish: /$^/,
  titles: /* @__PURE__ */ new Set(),
  address: /* @__PURE__ */ new Set(),
  addressPoss: /* @__PURE__ */ new Set(),
  roleWords: [],
  entityWords: /* @__PURE__ */ new Set(),
  sections: { front: [], back: [] },
  sluglineWord: /\b(INT|EXT)\b/
};
var LEXICONS = { es: ES, en: EN, auto: AUTO };
function detectLang(sample) {
  const words = sample.slice(0, 4e4).toLowerCase().match(/[\p{L}]+/gu) ?? [];
  let es = 0, en = 0;
  for (const w of words) {
    if (ES.stop.has(w)) es++;
    if (EN.stop.has(w)) en++;
  }
  if (Math.max(es, en) < words.length * 0.08) return "auto";
  return es > en ? "es" : "en";
}

// src/lib/utils/emotion-arc.ts
var emotion_arc_exports = {};
__export(emotion_arc_exports, {
  arcSparkline: () => arcSparkline,
  emotionArc: () => emotionArc,
  scoreSection: () => scoreSection,
  wordCharge: () => wordCharge
});
var NEGATIVE = [
  // es
  "muert",
  "matar",
  "mat\xF3",
  "matan",
  "asesin",
  "sangre",
  "sangri",
  "dolor",
  "duele",
  "herid",
  "herir",
  "miedo",
  "temor",
  "terror",
  "p\xE1nico",
  "horror",
  "espant",
  "aterr",
  "angusti",
  "ansied",
  "llor",
  "l\xE1grim",
  "triste",
  "tristez",
  "pena",
  "sufr",
  "agon\xED",
  "desesper",
  "soledad",
  "solo",
  "odio",
  "odiar",
  "rabia",
  "furi",
  "ira",
  "grit",
  "chill",
  "amenaz",
  "peligr",
  "oscur",
  "tinieb",
  "fr\xEDo",
  "helad",
  "vac\xEDo",
  "perdid",
  "romp",
  "destru",
  "ruina",
  "derrot",
  "fracas",
  "culpa",
  "traicion",
  "mentir",
  "enga\xF1",
  "cruel",
  "brutal",
  "violen",
  "guerra",
  "batalla",
  "enemig",
  "enferm",
  "veneno",
  "muri",
  "cad\xE1ver",
  "tumba",
  "infiern",
  "maldi",
  "castig",
  "prisi\xF3n",
  "encerr",
  // en
  "death",
  "died",
  "kill",
  "murder",
  "blood",
  "pain",
  "hurt",
  "wound",
  "fear",
  "terror",
  "horror",
  "panic",
  "dread",
  "anguish",
  "cry",
  "tear",
  "sad",
  "grief",
  "suffer",
  "despair",
  "lonely",
  "hate",
  "rage",
  "fury",
  "anger",
  "scream",
  "shout",
  "threat",
  "danger",
  "dark",
  "cold",
  "empty",
  "lost",
  "break",
  "destroy",
  "ruin",
  "defeat",
  "fail",
  "guilt",
  "betray",
  "lie",
  "deceive",
  "cruel",
  "brutal",
  "violen",
  "war",
  "battle",
  "enemy",
  "sick",
  "poison",
  "corpse",
  "grave",
  "hell"
];
var POSITIVE = [
  // es
  "amor",
  "amar",
  "ama",
  "quer",
  "beso",
  "abraz",
  "caric",
  "ternur",
  "dulce",
  "feliz",
  "felicid",
  "alegr",
  "r\xEDe",
  "re\xEDr",
  "risa",
  "sonri",
  "sonrisa",
  "luz",
  "brilla",
  "ilumin",
  "calor",
  "c\xE1lid",
  "paz",
  "calma",
  "tranquil",
  "seren",
  "esperanz",
  "sue\xF1",
  "libert",
  "libre",
  "salv",
  "protej",
  "belle",
  "hermos",
  "bell",
  "precios",
  "perfect",
  "triunf",
  "vict",
  "logr",
  "gana",
  "\xE9xito",
  "amig",
  "familia",
  "hogar",
  "casa",
  "refugi",
  "nace",
  "nacer",
  "vida",
  "vivir",
  "flor",
  "jard\xEDn",
  // en
  "love",
  "kiss",
  "embrace",
  "tender",
  "sweet",
  "happy",
  "joy",
  "laugh",
  "smile",
  "light",
  "shine",
  "warm",
  "peace",
  "calm",
  "serene",
  "hope",
  "dream",
  "free",
  "save",
  "protect",
  "beauty",
  "beautiful",
  "perfect",
  "triumph",
  "victory",
  "achieve",
  "win",
  "success",
  "friend",
  "family",
  "home",
  "shelter",
  "born",
  "life",
  "live",
  "flower",
  "garden",
  "gentle",
  "safe"
];
var HIGH_AROUSAL = [
  "corr",
  "salt",
  "golpe",
  "grit",
  "estall",
  "explo",
  "romp",
  "lucha",
  "pelea",
  "persig",
  "huy",
  "atac",
  "defiend",
  "dispar",
  "clav",
  "arranc",
  "arroj",
  "precipit",
  "urgen",
  "s\xFAbit",
  "repent",
  "de pronto",
  "de golpe",
  "jam\xE1s",
  "nunca",
  "siempre",
  "todo",
  "nada",
  "run",
  "jump",
  "strike",
  "scream",
  "burst",
  "explo",
  "break",
  "fight",
  "chase",
  "flee",
  "attack",
  "defend",
  "shoot",
  "sudden",
  "urgent",
  "never",
  "always"
];
function buildMatcher(stems) {
  const escaped = stems.map((s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  return new RegExp(`\\b(?:${escaped.join("|")})`, "gi");
}
var NEG_RE = buildMatcher(NEGATIVE);
var POS_RE = buildMatcher(POSITIVE);
var AROUSE_RE = buildMatcher(HIGH_AROUSAL);
function wordCharge(word) {
  const neg = (word.match(NEG_RE) ?? []).length, pos = (word.match(POS_RE) ?? []).length;
  return { valence: pos > neg ? 1 : neg > pos ? -1 : 0, arousal: (word.match(AROUSE_RE) ?? []).length > 0 ? 1 : 0 };
}
function scoreSection(text) {
  const words = (text.match(/\S+/g) ?? []).length;
  if (words < 20) return { valence: 0, arousal: 0, words };
  const neg = (text.match(NEG_RE) ?? []).length;
  const pos = (text.match(POS_RE) ?? []).length;
  const arouse = (text.match(AROUSE_RE) ?? []).length;
  const per1k = (n) => n / words * 1e3;
  const negRate = per1k(neg), posRate = per1k(pos);
  const total = negRate + posRate;
  const valence = total > 0 ? Math.round((posRate - negRate) / total * 100) : 0;
  const arousal = Math.round(Math.min(100, (total + per1k(arouse)) / 40 * 100));
  return { valence, arousal, words };
}
function emotionArc(sections) {
  const scored = sections.map((s, i) => {
    const sc = scoreSection(s.text);
    return {
      position: sections.length > 1 ? i / (sections.length - 1) : 0,
      label: s.label,
      valence: sc.valence,
      arousal: sc.arousal,
      words: sc.words
    };
  }).filter((p) => p.words >= 20);
  if (scored.length === 0) {
    return { points: [], overallValence: 0, lowest: null, highest: null, peak: null, shape: "unknown" };
  }
  const overall = Math.round(scored.reduce((n, p) => n + p.valence, 0) / scored.length);
  const lowest = scored.reduce((a, b) => b.valence < a.valence ? b : a);
  const highest = scored.reduce((a, b) => b.valence > a.valence ? b : a);
  const peak = scored.reduce((a, b) => b.arousal > a.arousal ? b : a);
  return { points: scored, overallValence: overall, lowest, highest, peak, shape: describeShape(scored) };
}
function describeShape(points) {
  if (points.length < 3) return "too short to trace";
  const third = Math.max(1, Math.floor(points.length / 3));
  const mean2 = (arr) => arr.reduce((n, p) => n + p.valence, 0) / arr.length;
  const start = mean2(points.slice(0, third));
  const middle = mean2(points.slice(third, points.length - third));
  const end = mean2(points.slice(-third));
  const rising = end - start > 15;
  const falling = start - end > 15;
  const dipped = middle < start - 15 && middle < end - 15;
  const arched = middle > start + 15 && middle > end + 15;
  if (dipped) return "falls into a dark middle and recovers";
  if (arched) return "rises through the middle and darkens at the end";
  if (rising) return "darkest at the start, brightening towards the end";
  if (falling) return "brightest at the start, darkening towards the end";
  return "holds an even emotional register throughout";
}
function arcSparkline(arc, width = 24) {
  if (!arc.points.length) return "";
  const bars = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588";
  const step = Math.max(1, Math.floor(arc.points.length / width));
  const sampled = arc.points.filter((_, i) => i % step === 0).slice(0, width);
  return sampled.map((p) => bars[Math.min(bars.length - 1, Math.floor((p.valence + 100) / 200 * bars.length))]).join("");
}

// src/lib/nodes/embedding.ts
function rng(seed) {
  let x = (seed ^ 2654435769) >>> 0 || 1;
  return () => {
    x ^= x << 13;
    x >>>= 0;
    x ^= x >>> 17;
    x ^= x << 5;
    x >>>= 0;
    return x / 4294967296;
  };
}
function buildEmbedding(sentences, opts = {}) {
  const dim = opts.dim ?? 128, win = opts.window ?? 12, minCount = opts.minCount ?? 2, maxVocab = opts.maxVocab ?? 5e3;
  const freq = /* @__PURE__ */ new Map();
  for (const s of sentences) for (const w of s) freq.set(w, (freq.get(w) ?? 0) + 1);
  const vocab = [...freq].filter(([, c]) => c >= minCount).sort((a, b) => b[1] - a[1]).slice(0, maxVocab).map((x) => x[0]);
  const id = new Map(vocab.map((w, i) => [w, i]));
  const V = vocab.length;
  const vec = /* @__PURE__ */ new Map();
  if (V < 4) return { dim, vec, sim: () => 0, neighbors: () => [], simToVec: () => 0, centroid: () => null };
  const co = /* @__PURE__ */ new Map();
  const row = new Float64Array(V);
  let total = 0;
  for (const s of sentences) {
    const ids = s.map((w) => id.get(w) ?? -1);
    for (let i = 0; i < ids.length; i++) {
      if (ids[i] < 0) continue;
      for (let j = Math.max(0, i - win); j <= Math.min(ids.length - 1, i + win); j++) {
        if (j === i || ids[j] < 0) continue;
        const wgt = 1 / Math.abs(i - j);
        const k = ids[i] * V + ids[j];
        co.set(k, (co.get(k) ?? 0) + wgt);
        row[ids[i]] += wgt;
        total += wgt;
      }
    }
  }
  const alpha = 0.75;
  let ctxTotal = 0;
  const ctx = new Float64Array(V);
  for (let i = 0; i < V; i++) {
    ctx[i] = Math.pow(row[i], alpha);
    ctxTotal += ctx[i];
  }
  const R = vocab.map((w, i) => {
    const g = rng(i * 2654435761 + w.length);
    const v = new Float32Array(dim);
    for (let d = 0; d < dim; d++) v[d] = g() < 0.5 ? -1 : 1;
    return v;
  });
  const acc = vocab.map(() => new Float32Array(dim));
  for (const [k, c] of co) {
    const a = Math.floor(k / V), b = k % V;
    const pmi = Math.log(c / total / (row[a] / total * (ctx[b] / ctxTotal)));
    if (pmi <= 0) continue;
    const t = acc[a], r = R[b];
    for (let d = 0; d < dim; d++) t[d] += pmi * r[d];
  }
  for (let i = 0; i < V; i++) {
    const t = acc[i];
    let n = 0;
    for (let d = 0; d < dim; d++) n += t[d] * t[d];
    n = Math.sqrt(n);
    if (n > 0) for (let d = 0; d < dim; d++) t[d] /= n;
    vec.set(vocab[i], t);
  }
  const dot = (a, b) => {
    let s = 0;
    for (let d = 0; d < dim; d++) s += a[d] * b[d];
    return s;
  };
  return {
    dim,
    vec,
    sim: (a, b) => {
      const x = vec.get(a), y = vec.get(b);
      return x && y ? dot(x, y) : 0;
    },
    simToVec: (w, v) => {
      const x = vec.get(w);
      return x ? dot(x, v) : 0;
    },
    neighbors: (w, k = 8) => {
      const x = vec.get(w);
      if (!x) return [];
      const out = [];
      for (const [o, y] of vec) if (o !== w) out.push({ word: o, sim: dot(x, y) });
      return out.sort((p, q) => q.sim - p.sim).slice(0, k);
    },
    centroid: (words) => {
      const c = new Float32Array(dim);
      let n = 0;
      for (const w of words) {
        const x = vec.get(w);
        if (!x) continue;
        for (let d = 0; d < dim; d++) c[d] += x[d];
        n++;
      }
      if (!n) return null;
      let m = 0;
      for (let d = 0; d < dim; d++) m += c[d] * c[d];
      m = Math.sqrt(m) || 1;
      for (let d = 0; d < dim; d++) c[d] /= m;
      return c;
    }
  };
}
function equivalenceClasses(items, related) {
  const parent = items.map((_, i) => i);
  const find = (x) => {
    while (parent[x] !== x) {
      parent[x] = parent[parent[x]];
      x = parent[x];
    }
    return x;
  };
  for (let i = 0; i < items.length; i++) for (let j = i + 1; j < items.length; j++) if (related(items[i], items[j])) parent[find(i)] = find(j);
  const groups = /* @__PURE__ */ new Map();
  items.forEach((it, i) => {
    const r = find(i);
    (groups.get(r) ?? groups.set(r, []).get(r)).push(it);
  });
  return [...groups.values()];
}
function clusterVocabulary(emb, k, iterations = 10) {
  const words = [...emb.vec.keys()];
  const fullDim = emb.dim;
  const fieldOf = /* @__PURE__ */ new Map();
  if (words.length < k * 3 || k < 2) return { fields: [], fieldOf };
  const dim = Math.min(fullDim, 96), N = words.length;
  const M = new Float32Array(N * dim);
  words.forEach((w, i) => {
    const v = emb.vec.get(w);
    let n = 0;
    for (let d = 0; d < dim; d++) n += v[d] * v[d];
    n = Math.sqrt(n) || 1;
    for (let d = 0; d < dim; d++) M[i * dim + d] = v[d] / n;
  });
  const dotRC = (i, c) => {
    let s = 0;
    const o = i * dim;
    for (let d = 0; d < dim; d++) s += M[o + d] * c[d];
    return s;
  };
  const g = rng(N * 7919 + fullDim);
  const first = Math.floor(g() * N);
  const centres = [M.slice(first * dim, first * dim + dim)];
  const bestSim = new Float32Array(N).fill(-2);
  while (centres.length < k) {
    const last = centres[centres.length - 1];
    let sum = 0;
    for (let i = 0; i < N; i++) {
      const sm = dotRC(i, last);
      if (sm > bestSim[i]) bestSim[i] = sm;
      const d = 1 - bestSim[i];
      sum += d * d;
    }
    let r = g() * sum, pick = 0;
    for (let i = 0; i < N; i++) {
      const d = 1 - bestSim[i];
      r -= d * d;
      if (r <= 0) {
        pick = i;
        break;
      }
    }
    centres.push(M.slice(pick * dim, pick * dim + dim));
  }
  const assign = new Int32Array(N).fill(-1);
  for (let it = 0; it < iterations; it++) {
    let moved = 0;
    for (let i = 0; i < N; i++) {
      let b = 0, bs = -2;
      for (let c = 0; c < k; c++) {
        const sm = dotRC(i, centres[c]);
        if (sm > bs) {
          bs = sm;
          b = c;
        }
      }
      if (assign[i] !== b) {
        assign[i] = b;
        moved++;
      }
    }
    const acc = centres.map(() => new Float32Array(dim)), cnt = new Array(k).fill(0);
    for (let i = 0; i < N; i++) {
      const a = acc[assign[i]], o = i * dim;
      for (let d = 0; d < dim; d++) a[d] += M[o + d];
      cnt[assign[i]]++;
    }
    acc.forEach((a, ci) => {
      if (!cnt[ci]) return;
      let n = 0;
      for (let d = 0; d < dim; d++) n += a[d] * a[d];
      n = Math.sqrt(n) || 1;
      for (let d = 0; d < dim; d++) centres[ci][d] = a[d] / n;
    });
    if (!moved) break;
  }
  const fields = centres.map((c, id) => {
    const idx = [];
    for (let i = 0; i < N; i++) if (assign[i] === id) idx.push(i);
    const label = [...idx].sort((a, b) => dotRC(b, c) - dotRC(a, c)).slice(0, 5).map((i) => words[i]);
    return { id, label, members: idx.map((i) => words[i]) };
  }).filter((f) => f.members.length >= 3);
  const remap = new Map(fields.map((f, i) => [f.id, i]));
  fields.forEach((f, i) => {
    f.id = i;
  });
  words.forEach((w, i) => {
    const ni = remap.get(assign[i]);
    if (ni !== void 0) fieldOf.set(w, ni);
  });
  return { fields, fieldOf };
}

// src/lib/nodes/completion.ts
var completion_exports = {};
__export(completion_exports, {
  buildCompletionBrief: () => buildCompletionBrief
});
var clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
function buildCompletionBrief(r) {
  const L = Math.max(1, r.structure.body ? Math.min(r.layers, r.structure.body[1]) : r.layers), tail = Math.max(1, Math.round(L * 0.1)), endFrom = L - tail + 1;
  const lastCh = r.chapters[r.chapters.length - 1];
  const curve = r.tension.curve, endT = curve.filter((c) => c.page >= endFrom).map((c) => c.tension), allT = curve.map((c) => c.tension);
  const endTension = endT.length ? Math.round(endT.reduce((a, b) => a + b, 0) / endT.length) : 0, peak = allT.length ? Math.max(...allT) : 0;
  const lastScene = lastCh?.events[lastCh.events.length - 1];
  const chOfPage = (pg) => {
    let c = 1;
    for (const ch of r.chapters) if (pg >= ch.pages[0]) c = ch.index;
    return c;
  };
  const readAround = (pg) => [Math.max(1, pg - 1), Math.min(L, pg + 1)];
  const lastLayers = r.map4d.layers.filter((l) => l.page >= endFrom);
  const stage = /* @__PURE__ */ new Map();
  for (const l of lastLayers) for (const n of l.nodes) {
    const c = stage.get(n.name) ?? stage.set(n.name, { n: 0, last: 0, place: null, with: /* @__PURE__ */ new Map(), v: 0, t: 0 }).get(n.name);
    c.n += n.n;
    c.last = Math.max(c.last, l.page);
    c.place = n.place ?? c.place;
    for (const w of n.with) c.with.set(w, (c.with.get(w) ?? 0) + 1);
    c.v += n.tone.valence * n.n;
    c.t += n.tone.tension * n.n;
  }
  const alive = [...stage].sort((a, b) => b[1].n - a[1].n).slice(0, 12).map(([name, c]) => ({ name, kind: r.nodes.find((x) => x.name === name)?.kind ?? "character", lastPage: c.last, place: c.place, with: [...c.with].sort((a, b) => b[1] - a[1]).slice(0, 3).map((x) => x[0]), valence: Math.round(c.v / c.n), tension: Math.round(c.t / c.n) }));
  const open = [], closed = [];
  const maxMentions = Math.max(1, ...r.dossiers.map((d) => d.presence.mentions));
  for (const d of r.dossiers) {
    if (d.kind !== "character" || d.presence.mentions < 8) continue;
    const gone = d.presence.last < L * 0.85, weight = clamp(0.55 * (d.presence.mentions / maxMentions) ** 0.5 + 0.45 * d.presence.share);
    if (gone) open.push({ kind: "vanished character", subject: d.name, weight: Math.round(weight * 100) / 100, evidence: [`${d.presence.mentions} mentions over ${d.presence.chapters.length} chapters, last seen on page ${d.presence.last} of ${L}`, d.lastSeen.line ? `last line: \xAB${d.lastSeen.line.slice(0, 110)}\xBB` : "", d.tone ? `its tone at the end of its line: ${d.tone.trend}` : ""].filter(Boolean), lastSeen: { page: d.presence.last, chapter: d.lastSeen.chapter }, readPages: [readAround(d.presence.last), ...d.introduced.page ? [[d.introduced.page, d.introduced.page]] : []] });
    else if (d.presence.first > L * 0.1 || d.presence.mentions >= 20) closed.push({ kind: "character present to the end", subject: d.name, evidence: `last seen on page ${d.presence.last} of ${L}` });
  }
  for (const p of r.tension.pairs) {
    if (p.sentences < 5) continue;
    const endsLate = p.pages[1] >= L * 0.6, tense = p.bond === "hostile" || p.bond === "strained";
    if (tense && p.trend === "escalates" && endsLate) open.push({ kind: "unresolved bond", subject: `${p.a} + ${p.b}`, weight: Math.round(clamp(p.tension / 100 * 0.6 + Math.min(0.4, Math.log10(p.sentences) * 0.25)) * 100) / 100, evidence: [`${p.bond}, tension ${p.tension} and rising over ${p.sentences} sentences (pages ${p.pages[0]}\u2013${p.pages[1]})`, p.peak ? `peak of the bond on page ${p.peak}` : ""].filter(Boolean), lastSeen: { page: p.pages[1], chapter: chOfPage(p.pages[1]) }, readPages: [...p.peak ? [readAround(p.peak)] : [], readAround(p.pages[1])] });
    else if (p.trend === "eases" && p.sentences >= 8) closed.push({ kind: "bond that eased", subject: `${p.a} + ${p.b}`, evidence: `tension falls over pages ${p.pages[0]}\u2013${p.pages[1]}` });
  }
  for (const t of r.themeForest) if (t.flow === "builds" && t.mentions >= 6) open.push({ kind: "building theme", subject: t.root, weight: Math.round(clamp(t.share * 0.7) * 100) / 100, evidence: [`a ${t.class} that grows through the work (${t.mentions} mentions, ${Math.round(t.share * 100)}% of the chapters) and has not peaked`, t.branches.length ? `grows: ${t.branches.slice(0, 4).map((b) => b.word).join(", ")}` : ""].filter(Boolean), lastSeen: t.chapters.length ? { page: r.chapters[t.chapters[t.chapters.length - 1] - 1]?.pages[1] ?? L, chapter: t.chapters[t.chapters.length - 1] } : null, readPages: t.chapters.slice(-2).map((c) => r.chapters[c - 1]?.pages).filter((x) => !!x) });
  for (const a of r.arcs) {
    const d = r.dossiers.find((x) => x.name === a.node);
    if (!d || d.kind !== "character" || d.rank !== "primary" || a.confidence < 0.5) continue;
    if (a.verdict !== "identity" && a.direction === "falls") open.push({ kind: "dark arc", subject: a.node, weight: Math.round(clamp(0.5 + (1 - a.identity) * 0.4) * 100) / 100, evidence: [`its surroundings change (${a.verdict}) and the charge falls from ${a.chargeEarly} to ${a.chargeLate}`, `lost ${a.lost.slice(0, 3).join(", ") || "\u2014"} \xB7 gained ${a.gained.slice(0, 3).join(", ") || "\u2014"}`], lastSeen: { page: d.presence.last, chapter: d.lastSeen.chapter }, readPages: [readAround(d.presence.last), ...d.climax ? [d.climax.pages] : []] });
    else if (a.verdict === "identity") closed.push({ kind: "character unchanged", subject: a.node, evidence: "its surroundings at the end are those of the beginning" });
  }
  const endsHigh = peak > 0 && endTension >= peak * 0.7;
  if (endsHigh) open.push({ kind: "tension left high", subject: `pages ${endFrom}\u2013${L}`, weight: Math.round(clamp(endTension / 100) * 100) / 100, evidence: [`tension at the end ${endTension} against a peak of ${peak}`, ...r.tension.peaks.length ? [`peaks of the work: pages ${r.tension.peaks.join(", ")}`] : []], lastSeen: { page: L, chapter: lastCh?.index ?? 1 }, readPages: [[endFrom, L], ...r.tension.peaks.length ? [readAround(r.tension.peaks[r.tension.peaks.length - 1])] : []] });
  for (const c of r.chapters.filter((c2) => c2.inferred)) open.push({ kind: "missing chapter", subject: `chapter ${c.index}`, weight: 0.5, evidence: [`no heading was found; recovered from the spacing (${c.inferredBy ?? "rhythm"})`], lastSeen: { page: c.pages[0], chapter: c.index }, readPages: [c.pages] });
  for (const pc of r.placeCasts) {
    if (pc.mentions < 6 || pc.pages[1] >= L * 0.8) continue;
    const d = r.dossiers.find((x) => x.name === pc.place);
    open.push({ kind: "abandoned place", subject: pc.place, weight: Math.round(clamp(Math.log10(pc.mentions + 1) / 2) * 60) / 100, evidence: [`${pc.mentions} mentions, last on page ${pc.pages[1]} of ${L}`, pc.cast.length ? `who weighed there: ${pc.cast.slice(0, 3).map((c) => c.name).join(", ")}` : ""].filter(Boolean), lastSeen: { page: pc.pages[1], chapter: chOfPage(pc.pages[1]) }, readPages: [readAround(pc.pages[1]), ...d?.climax ? [d.climax.pages] : []] });
  }
  const kept = [];
  for (const kind of [...new Set(open.map((t) => t.kind))]) {
    const fam = open.filter((t) => t.kind === kind).sort((a, b) => b.weight - a.weight);
    if (fam.length <= 3) {
      kept.push(...fam);
      continue;
    }
    const mu = fam.reduce((a, t) => a + t.weight, 0) / fam.length, sd2 = Math.sqrt(fam.reduce((a, t) => a + (t.weight - mu) ** 2, 0) / fam.length);
    kept.push(...fam.filter((t, i) => i < 3 || t.weight >= mu + 0.5 * sd2));
  }
  open.length = 0;
  open.push(...kept);
  open.sort((a, b) => b.weight - a.weight);
  const returns = r.worldIdentity ? r.worldIdentity.circularity.verdict === "circular" : null;
  const lastPlace = lastScene?.place ?? alive.find((a) => a.place)?.place ?? null;
  return {
    endsAt: { page: L, of: L, chapter: lastCh?.index ?? 0, chapterTitle: lastCh?.title ?? "", place: lastPlace, actors: lastScene?.actors ?? alive.slice(0, 4).map((a) => a.name), tension: endTension, peak, tone: lastCh?.tone.label ?? "neutral", scene: lastScene?.words.slice(0, 8) ?? [] },
    alive,
    openThreads: open,
    closedThreads: closed.slice(0, 20),
    returnsToStart: returns,
    summary: { open: open.length, ends: endsHigh ? "on a peak" : endTension >= peak * 0.4 ? "resolving" : "flat", mostUrgent: open[0] ? `${open[0].kind}: ${open[0].subject}` : null }
  };
}

// src/lib/nodes/restructure.ts
var targetAt = (p) => p <= 0.85 ? 22 + 78 * Math.pow(p / 0.85, 1.35) : 100 - 62 * Math.pow((p - 0.85) / 0.15, 1.1);
var isPartTitle = (t) => PART.test(t);
var PART = /^\s*(primer[ao]?|segund[ao]?|tercer[ao]?|cuart[ao]?|quint[ao]?|sext[ao]?|first|second|third|fourth|fifth|sixth|part|parte|libro|book|acto|act)\b.*\b(parte|part)\b|^\s*(part|parte|libro|book|acto|act)\b/i;
var DATED = /\b(d[ií]a|day)\s+\d+|\b\d{1,2}\s+de\s+\p{L}+|\b(chapter|cap[ií]tulo)\s+\d+|^\s*\d+[.)]?\s/iu;
function proposeRestructure(r, maxProposals = 6) {
  const n = r.chapters.length;
  const t = r.chapters.map((c) => c.tension);
  const target = Array.from({ length: n }, (_, i) => Math.round(targetAt(n > 1 ? i / (n - 1) : 0)));
  const BAND = 12, CONT = 150, MAXMOVE = Math.max(3, Math.min(6, Math.round(n * 0.15)));
  const cast = r.chapters.map((c) => new Set(c.nodes));
  const jac = (a, b) => {
    const A = cast[a], B = cast[b];
    if (!A.size || !B.size) return 0.5;
    let i = 0;
    for (const x of A) if (B.has(x)) i++;
    return i / (A.size + B.size - i);
  };
  const fit = (ord) => ord.reduce((a, ci, pos) => a + Math.max(0, Math.abs(t[ci] - target[pos]) - BAND) ** 2 + (pos ? CONT * (1 - jac(ord[pos - 1], ci)) : 0), 0);
  const rms = (ord) => Math.sqrt(ord.reduce((a, ci, pos) => a + Math.max(0, Math.abs(t[ci] - target[pos]) - BAND) ** 2, 0) / Math.max(1, ord.length));
  const pinned = [];
  r.chapters.forEach((c, i) => {
    if (PART.test(c.title)) pinned.push({ chapter: i + 1, why: "a part of the book: it marks an act and keeps its place" });
    else if (DATED.test(c.title)) pinned.push({ chapter: i + 1, why: "dated or numbered: its order is part of the story" });
  });
  const isPinned = new Set(pinned.map((p) => p.chapter - 1));
  const isDated = new Set(r.chapters.map((c, i) => DATED.test(c.title) && !PART.test(c.title) ? i : -1).filter((i) => i >= 0));
  const major = r.dossiers.filter((d) => d.kind === "character" && d.presence.mentions >= 8);
  const inCh = (name) => new Set(r.dossiers.find((d) => d.name === name)?.presence.chapters.map((c) => c - 1) ?? []);
  const presence = major.map((d) => ({ name: d.name, chapters: inCh(d.name) }));
  const firstIn = (ord, chs) => {
    for (const ci of ord) if (chs.has(ci)) return ci;
    return -1;
  };
  const original = Array.from({ length: n }, (_, i) => i);
  const introducer = presence.map((p) => firstIn(original, p.chapters));
  const keepsIntroductions = (ord) => presence.every((p, i) => firstIn(ord, p.chapters) === introducer[i]);
  const apply = (ord, k, to) => {
    const o = ord.filter((x) => x !== k);
    o.splice(to, 0, k);
    return o;
  };
  let order = original.slice(), base = fit(order);
  const baseFit = base;
  const proposals = [], moved = /* @__PURE__ */ new Set();
  for (let step = 0; step < maxProposals && n >= 4; step++) {
    let best = null;
    for (const k of order) {
      if (isPinned.has(k) || moved.has(k)) continue;
      const from2 = order.indexOf(k);
      for (let to = Math.max(0, from2 - MAXMOVE); to <= Math.min(n - 1, from2 + MAXMOVE); to++) {
        if (to === from2) continue;
        const cand = apply(order, k, to);
        const pinOrder = cand.filter((x) => isPinned.has(x)), pinOrig = order.filter((x) => isPinned.has(x));
        if (isDated.has(cand[to - 1] ?? -1) && isDated.has(cand[to + 1] ?? -1)) continue;
        if (pinOrder.join() !== pinOrig.join() || !keepsIntroductions(cand)) continue;
        const c = fit(cand);
        if (!best || c < best.cost) best = { k, to, cost: c };
      }
    }
    if (!best || best.cost >= base * 0.96) break;
    const from = order.indexOf(best.k), next = apply(order, best.k, best.to);
    const stand = next[best.to - 1], ch = r.chapters[best.k];
    const reason = [`its tension is ${t[best.k]} and it stands at position ${from + 1} of ${n}, where the curve of a story asks for about ${target[from]}; at position ${best.to + 1} it asks for ${target[best.to]}`];
    const before = order.slice(Math.max(0, best.to - 3), best.to).map((x) => t[x]), prev = order.slice(Math.max(0, from - 3), from).map((x) => t[x]);
    if (before.length) reason.push(`it would follow tensions ${before.join(", ")}`);
    if (prev.length && Math.max(...prev) - Math.min(...prev) <= 15) reason.push(`where it stands now the stretch before it is flat (${prev.join(", ")})`);
    const intro = presence.filter((_, i) => introducer[i] === best.k).map((p) => p.name);
    const pg = (ci) => r.chapters[ci].pages;
    proposals.push({
      facts: { tension: t[best.k], fromTarget: target[from], toTarget: target[best.to], follows: before, flatBefore: prev.length && Math.max(...prev) - Math.min(...prev) <= 15 ? prev : null, introduces: intro },
      chapter: best.k + 1,
      title: ch.title,
      from: from + 1,
      to: best.to + 1,
      after: stand === void 0 ? null : stand + 1,
      afterTitle: stand === void 0 ? null : r.chapters[stand].title,
      gain: Math.round((base - best.cost) / Math.max(1, baseFit) * 1e3) / 10,
      tension: t[best.k],
      reason,
      keeps: [intro.length ? `${intro.join(", ")} still ${intro.length > 1 ? "are" : "is"} introduced in this chapter` : "every character is introduced where it was", "dated entries and parts keep their order"],
      readPages: [pg(best.k), ...stand !== void 0 ? [pg(stand)] : [], ...next[best.to + 1] !== void 0 ? [pg(next[best.to + 1])] : []]
    });
    order = next;
    base = best.cost;
    moved.add(best.k);
  }
  return { before: { tension: t, fit: Math.round(rms(original)) }, after: { tension: order.map((i) => t[i]), fit: Math.round(rms(order)), order: order.map((i) => i + 1) }, target, proposals, pinned };
}

// src/lib/nodes/report-detect.ts
var mean = (a) => a.length ? a.reduce((x, y) => x + y, 0) / a.length : 0;
var sd = (a) => {
  const m = mean(a);
  return Math.sqrt(mean(a.map((x) => (x - m) ** 2))) || 1e-9;
};
var zs = (a) => {
  const m = mean(a), s = sd(a);
  return a.map((x) => (x - m) / s);
};
function proof(r, word) {
  const e = r.wordIndex[word.toLowerCase()];
  if (!e) return null;
  return { word, n: e.n, pages: e.pages, chapters: e.chapters.filter((c) => c > 0).length, orbit: e.orbit.slice(0, 6), near: e.near.slice(0, 4), after: e.after[0]?.[0] ?? null };
}
var proofs = (r, ws) => ws.map((w) => proof(r, w)).filter((p) => !!p);
function standouts(items, score, floor, chance = true) {
  if (!items.length) return [];
  if (items.length === 1) return score(items[0]) >= floor ? [{ item: items[0], z: score(items[0]) / Math.max(floor, 1e-9) }] : [];
  const sc = items.map(score), z = zs(sc).map((v) => Math.min(v, 99));
  const cut = chance ? Math.max(1, Math.sqrt(2 * Math.log(items.length))) : 1;
  return items.map((item, i) => ({ item, z: z[i], s: sc[i] })).filter((x) => x.z >= cut && x.s >= floor).map(({ item, z: z2 }) => ({ item, z: z2 }));
}
function detectThemes(r) {
  const titleWords = new Set(r.chapters.flatMap((c) => c.title.toLowerCase().split(/[^\p{L}]+/u)).filter(Boolean)), scaffold = /* @__PURE__ */ new Set([...r.structuralWords.map((w) => w.toLowerCase()), ...titleWords]);
  const trees = r.themeForest.filter((t) => t.mentions >= 3 && !scaffold.has(t.root.toLowerCase()));
  const out = [];
  for (const { item: t, z } of standouts(trees, (t2) => t2.share * Math.log(1 + t2.mentions) * (1 + 0.15 * t2.branches.length), 0, false)) {
    const th = r.morphisms.thematic.find((x) => x.root === t.root);
    out.push({
      id: `theme:${t.root}`,
      family: "theme",
      title: t.root,
      salience: Math.round(z * 100) / 100,
      evidence: [`${t.class}, ${t.flow}, in ${Math.round(t.share * 100)}% of the chapters (${t.mentions} mentions)`, t.branches.length ? `grows: ${t.branches.slice(0, 6).map((b) => b.word).join(", ")}` : "", t.peaks.length ? `peaks in chapters ${t.peaks.join(", ")}` : "", th ? `${th.verdict} (${Math.round(th.preservation * 100)}% of its relations survive from the first half to the second)` : ""].filter(Boolean),
      words: proofs(r, [t.root, ...t.branches.slice(0, 5).map((b) => b.word)])
    });
  }
  return out.sort((a, b) => b.salience - a.salience);
}
function detectStrengths(r) {
  const out = [];
  for (const { item: a, z } of standouts(r.arcs.filter((a2) => a2.confidence >= 0.5), (a2) => (1 - a2.identity) * a2.confidence, 0.2)) {
    out.push({
      id: `arc:${a.node}`,
      family: "transformation",
      title: `The arc of ${a.node}`,
      salience: z,
      evidence: [`${a.verdict}: ${Math.round((1 - a.identity) * 100)}% of its circle changes (${a.basis}); charge ${a.chargeEarly} \u2192 ${a.chargeLate} (${a.direction})`, `kept ${a.kept.slice(0, 4).join(", ") || "\u2014"} \xB7 lost ${a.lost.slice(0, 4).join(", ") || "\u2014"} \xB7 gained ${a.gained.slice(0, 4).join(", ") || "\u2014"}`],
      words: proofs(r, [a.node, ...a.gained.slice(0, 3), ...a.lost.slice(0, 3)])
    });
  }
  for (const { item: p, z } of standouts(r.morphisms.parallels, (p2) => p2.similarity * (1 - p2.castOverlap * 0.5), 0.5)) {
    out.push({
      id: `echo:${p.a.chapter}-${p.b.chapter}`,
      family: "structure",
      title: `${p.kind === "echo" ? "Echo" : "Hidden parallel"}: chapters ${p.a.chapter} and ${p.b.chapter}`,
      salience: z,
      evidence: [`same skeleton of relations (${Math.round(p.similarity * 100)}%) with ${Math.round((1 - p.castOverlap) * 100)}% of the cast different`, `map: ${p.mapping.slice(0, 5).map(([x, y]) => `${x}\u21A6${y}`).join(", ")}`],
      words: []
    });
  }
  {
    const ar = r.chapters.map((c) => c.tone.arousal);
    if (ar.length >= 4) {
      const swing = ar.map((v, i) => i ? Math.abs(v - ar[i - 1]) : 0);
      const hi = standouts(r.chapters.map((c, i) => ({ c, s: swing[i] })).filter((x) => x.s > 0), (x) => x.s, 0);
      if (hi.length >= 1 && sd(ar) > 4) out.push({
        id: "rhythm",
        family: "rhythm",
        title: "Rhythm of intensity between chapters",
        salience: Math.max(...hi.map((h) => h.z)),
        evidence: [`arousal moves between ${Math.min(...ar)} and ${Math.max(...ar)} with the sharpest turns into chapters ${hi.slice(0, 4).map((h) => h.item.c.index).join(", ")}`],
        words: []
      });
    }
  }
  if (r.worldIdentity && r.worldIdentity.circularity.verdict === "circular" && r.worldIdentity.invariant.length >= 3) out.push({
    id: "world-return",
    family: "world",
    title: "A world that comes back to where it began",
    salience: 1 + r.worldIdentity.circularity.similarity,
    evidence: [`end against beginning: ${Math.round(r.worldIdentity.circularity.similarity * 100)}% alike${r.worldIdentity.circularity.samePlace ? ", in the same place" : ""}`, `unchanged: ${r.worldIdentity.invariant.slice(0, 6).map((w) => w.word).join(", ")}`, `changed most: ${r.worldIdentity.drift.slice(0, 5).map((w) => w.word).join(", ")}`],
    words: proofs(r, r.worldIdentity.invariant.slice(0, 5).map((w) => w.word))
  });
  for (const { item: pc, z } of standouts(r.placeCasts.filter((p) => p.cast.length >= 2), (p) => p.cast.length * Math.log(1 + p.mentions) * (1 + p.meetings.length), 0)) {
    out.push({
      id: `place:${pc.place}`,
      family: "place",
      title: `${pc.place} as a place with life`,
      salience: z,
      evidence: [`${pc.cast.length} people live or pass through it (natives: ${pc.cast.filter((c) => c.role === "native").map((c) => c.name).join(", ") || "\u2014"}); ${pc.meetings.length} meetings`],
      words: proofs(r, [pc.place])
    });
  }
  {
    const ch = r.dossiers.filter((d) => d.kind === "character" && d.presence.mentions >= 15);
    for (const { item: d, z } of standouts(ch, (d2) => Math.abs(d2.voice.dialogue - mean(ch.map((x) => x.voice.dialogue))), 0.15)) out.push({
      id: `voice:${d.name}`,
      family: "voice",
      title: `A distinct voice: ${d.name}`,
      salience: z,
      evidence: [`${Math.round(d.voice.dialogue * 100)}% dialogue against ${Math.round(mean(ch.map((x) => x.voice.dialogue)) * 100)}% for the cast`, `distinctive words: ${d.traits.elements.slice(0, 5).join(", ")}`],
      words: proofs(r, d.traits.elements.slice(0, 4))
    });
  }
  return dedupe(out).sort((a, b) => b.salience - a.salience);
}
function detectWeaknesses(r) {
  const out = [];
  const wi = r.wordIndex;
  const nameWord = /* @__PURE__ */ new Set();
  for (const n of r.nodes) for (const w of n.name.toLowerCase().split(/\s+/)) nameWord.add(w);
  {
    const cands = Object.entries(wi).filter(([w, e]) => e.n >= 20 && w.length >= 3 && !e.function && !nameWord.has(w) && e.after[0] && e.after[0][1] / e.n >= 0.3 && e.after[0][0].length >= 3 && !nameWord.has(e.after[0][0]) && wi[e.after[0][0]] && !wi[e.after[0][0]].function);
    for (const { item: [w, e], z } of standouts(cands, ([, e2]) => e2.after[0][1] / e2.n * Math.log(e2.n), 0)) out.push({
      id: `tic:${w}`,
      family: "repetition",
      title: `Stock phrase: \xAB${w} ${e.after[0][0]}\xBB`,
      salience: z,
      evidence: [`${Math.round(e.after[0][1] / e.n * 100)}% of the ${e.n} times \xAB${w}\xBB appears it is followed by \xAB${e.after[0][0]}\xBB`],
      words: proofs(r, [w, e.after[0][0]])
    });
  }
  {
    const ch = r.chapters.filter((c) => !c.inferred && c.words > 200);
    if (ch.length >= 5) for (const { item: c, z } of standouts(ch, (c2) => -(c2.tone.arousal - mean(ch.map((x) => x.tone.arousal))), 5)) out.push({
      id: `flat:${c.index}`,
      family: "pace",
      title: `A flat stretch: chapter ${c.index} \xAB${c.title}\xBB`,
      salience: z,
      evidence: [`arousal ${c.tone.arousal} against ${Math.round(mean(ch.map((x) => x.tone.arousal)))} for the book`, `${c.events.length} scenes, carried by ${c.nodes.slice(0, 3).join(", ") || "no named node"}`],
      words: proofs(r, c.signature.slice(0, 3))
    });
  }
  {
    const inf = r.chapters.filter((c) => c.inferred);
    if (inf.length) out.push({
      id: "gaps",
      family: "structure",
      title: "Chapters the book's own rhythm says are missing or unmarked",
      salience: 1 + inf.length / r.chapters.length * 4,
      evidence: [`chapters ${inf.map((c) => c.index).join(", ")} had no heading and were recovered from the spacing (${inf.map((c) => c.inferredBy).join(", ")})`],
      words: []
    });
  }
  for (const d of r.dossiers.filter((d2) => d2.kind === "character" && d2.rank === "primary")) {
    const den = d.presence.density;
    if (den.length < 8) continue;
    let run = 0, best = 0, at = 0;
    den.forEach((v, i) => {
      run = v === 0 ? run + 1 : 0;
      if (run > best) {
        best = run;
        at = i - run + 1;
      }
    });
    if (best / den.length >= 0.2 && at > 0 && at + best < den.length) out.push({
      id: `absent:${d.name}`,
      family: "presence",
      title: `${d.name} disappears for a fifth of the book`,
      salience: 1 + best / den.length * 5,
      evidence: [`no mention in ${best} of ${den.length} slices (from slice ${at + 1}), though it appears before and after`],
      words: proofs(r, [d.name])
    });
  }
  for (const k of r.injectivity.keptApart.slice(0, 3)) out.push({
    id: `confusable:${k.a ?? ""}${k.b ?? ""}`,
    family: "identity",
    title: `Two characters who live in the same surroundings: ${k.a} and ${k.b}`,
    salience: 1 + k.similarity,
    evidence: [`their surroundings are ${Math.round(k.similarity * 100)}% alike (${k.sharedPages} shared pages) though they are different people: easy to blur`],
    words: proofs(r, [k.a, k.b].filter(Boolean))
  });
  {
    const mixes = r.chapters.map((c) => c.mix.dialogue);
    if (mean(mixes) > 0.1) {
      const dry = r.chapters.filter((c) => c.mix.dialogue < 0.02 && c.words > 300);
      if (dry.length && dry.length < r.chapters.length) out.push({
        id: "dry",
        family: "voice",
        title: "Chapters without a single line of speech",
        salience: 1 + dry.length / r.chapters.length * 3,
        evidence: [`chapters ${dry.map((c) => c.index).join(", ")} against ${Math.round(mean(mixes) * 100)}% dialogue for the book`],
        words: []
      });
    }
  }
  return dedupe(out).sort((a, b) => b.salience - a.salience);
}
function dedupe(f) {
  const seen = /* @__PURE__ */ new Set();
  return f.filter((x) => seen.has(x.id) ? false : (seen.add(x.id), true));
}

// src/lib/nodes/dossier-spec.ts
var has = (v) => Array.isArray(v) ? v.length > 0 : !!v;
function build(specs, x) {
  return specs.map((s) => {
    const filled = s.needs.filter((n) => n.has(x)).map((n) => n.field), missing = s.needs.filter((n) => !n.has(x)).map((n) => n.field);
    const all = s.needs.length > 0 && missing.length === 0;
    const status = s.writtenBy === "model" ? all ? "evidence-ready" : filled.length ? "thin" : "to-complete" : all ? "filled" : filled.length ? "thin" : "to-complete";
    return { id: s.id, title: s.title, page: s.page, purpose: s.purpose, writtenBy: s.writtenBy, status, filled, missing, feeds: s.feeds, limit: s.limit, readPages: [] };
  });
}
var F = {
  identity: { ideas: [1, 6, 15, 21, 34, 44, 50], source: "nodes \xB7 equivalenceClasses \xB7 injectivity", fn: "capital runs \u2192 typeOf \u2192 identity stage (containment, glued appositives, adaptive nearest solar system, claimed map)", gives: "one entity per name, aliases folded, kind" },
  rank: { ideas: [17, 18], source: "forest", fn: "forest roots, primary / secondary", gives: "rank in the cast" },
  standing: { ideas: [48], source: "morphisms.hierarchy", fn: "learned forms of address + precedence \u2192 ranks, ownership, containment", gives: "standing, who it defers to, what it owns" },
  presence: { ideas: [2, 13, 27, 32], source: "layers \xB7 chapters \xB7 wordIndex", fn: "page(); chapter detection; buildWordIndex", gives: "where and how much it is on the page" },
  sentences: { ideas: [9, 12, 33, 43, 46], source: "sentences \xB7 structure", fn: "sentence rows (solar system between two full stops); front/back matter and titles masked", gives: "its first and last real sentences" },
  voice: { ideas: [11], source: "nodes.voice", fn: "tmode (dash, quotes, guillemets, screenplay cues)", gives: "dialogue / action / narration mix" },
  orbit: { ideas: [8, 37, 38], source: "affinity \xB7 circles \xB7 orbit", fn: "shrunk log-likelihood lift; canonical injection (circle A / outside B)", gives: "what is proper to it: body words, objects, actions" },
  events: { ideas: [23, 25], source: "chapters.events \xB7 chapters.tone", fn: "beats \u2192 scenes (actors, place, ordered words); charge from the extended lexicon", gives: "its scenes with charge" },
  arc: { ideas: [22, 39, 40], source: "arcs \xB7 embedding \xB7 worldIdentity", fn: "identity function in the embedding, permutation-test rank", gives: "what stays, is lost, is gained; direction of charge" },
  relations: { ideas: [20, 36, 17], source: "routePairs \xB7 knots \xB7 treeRelations", fn: "proximity node\u2013node (together, encounters, closest, trend); strand crossings", gives: "who it relates to, how, and where it tightens or breaks" },
  world: { ideas: [16, 35, 45], source: "places \xB7 routes \xB7 placeCasts", fn: "place casts (native / regular / visitor, meetings, tension); routes", gives: "home, places, route, meetings" },
  parallels: { ideas: [47], source: "morphisms.parallels", fn: "type-preserving matching of chapter skeletons", gives: "echoes of its situation with another cast" },
  themes: { ideas: [19, 24, 49], source: "themeForest \xB7 chapters.symbols \xB7 morphisms.thematic", fn: "theme trees; semantic fields; thematic consistency", gives: "motifs and symbols it carries" },
  tone: { ideas: [57], source: "tension", fn: "charge of every sentence (extended lexicon) \u2192 tone of each character, tone of each pair, tension per page / chapter", gives: "its tone, the tone of each bond and the tension levels" },
  prose: { ideas: [41], source: "this sheet (all sections)", fn: "one model call over the structured evidence \u2014 the only paid step", gives: "the prose" }
};
var PRINCIPAL = [
  {
    id: "anatomy",
    title: "Sociodemographic sheet and physical aspect",
    page: 1,
    writtenBy: "model",
    purpose: "name, aliases, role, how it looks and where it comes from",
    feeds: [F.identity, F.rank, F.orbit, F.sentences],
    needs: [{ field: "identity", has: (d) => !!d.name }, { field: "introduced", has: (d) => has(d.introduced.line) }, { field: "traits.elements", has: (d) => has(d.traits.elements) }, { field: "standing", has: (d) => has(d.standing) }],
    limit: "age, profession and looks come only from the words that orbit it; if the book never states them, they stay empty"
  },
  {
    id: "mannerisms",
    title: "Mannerisms and voice register",
    page: 1,
    writtenBy: "code",
    purpose: "how it speaks, what it does habitually, its register",
    feeds: [F.voice, F.orbit, F.events, F.tone],
    needs: [{ field: "voice", has: (d) => d.voice.dialogue + d.voice.action + d.voice.narration > 0 }, { field: "traits.actions", has: (d) => has(d.traits.actions) }, { field: "keyMoments", has: (d) => has(d.keyMoments) }, { field: "tone", has: (d) => !!d.tone }]
  },
  {
    id: "wound",
    title: "Original wound (ghost)",
    page: 1,
    writtenBy: "model",
    purpose: "the past event that conditions its view of the world",
    feeds: [F.arc, F.events, F.sentences, F.themes],
    needs: [{ field: "arc.lost", has: (d) => !!d.arc && has(d.arc.lost) }, { field: "keyMoments", has: (d) => has(d.keyMoments) }, { field: "introduced", has: (d) => has(d.introduced.line) }],
    limit: "a wound told only as backstory is read from the dark-charged scenes around its first appearance; if it is never narrated, it is inferred, not found"
  },
  {
    id: "lie",
    title: "The lie",
    page: 1,
    writtenBy: "model",
    purpose: "the false belief about itself or the world that the story puts to the test",
    feeds: [F.arc, F.standing, F.themes],
    needs: [{ field: "arc", has: (d) => has(d.arc) }, { field: "standing", has: (d) => has(d.standing) }, { field: "themes", has: (d) => has(d.themes) }],
    limit: "interpretive: the engine supplies what holds and what breaks around the character, not the belief itself"
  },
  {
    id: "want",
    title: "Want (conscious desire)",
    page: 2,
    writtenBy: "model",
    purpose: "what it believes it wants across the novel",
    feeds: [F.orbit, F.relations, F.world, F.standing],
    needs: [{ field: "traits.actions", has: (d) => has(d.traits.actions) }, { field: "route", has: (d) => has(d.route) }, { field: "relations", has: (d) => has(d.relations) }]
  },
  {
    id: "need",
    title: "Need (unconscious necessity)",
    page: 2,
    writtenBy: "model",
    purpose: "what it must learn or accept in order to mature",
    feeds: [F.arc, F.events],
    needs: [{ field: "arc.gained", has: (d) => !!d.arc && has(d.arc.gained) }, { field: "climax", has: (d) => has(d.climax) }]
  },
  {
    id: "obstacles",
    title: "Internal and external obstacles",
    page: 2,
    writtenBy: "code",
    purpose: "who and what stands against it: pulling-apart relations, tensions, rank above it",
    feeds: [F.relations, F.standing, F.world, F.tone],
    needs: [{ field: "relations", has: (d) => has(d.relations) }, { field: "relations.tone", has: (d) => d.relations.some((r) => !!r.tone) }, { field: "standing", has: (d) => has(d.standing) }, { field: "places", has: (d) => has(d.places) }]
  },
  {
    id: "steps",
    title: "Transformation, step by step",
    page: 3,
    writtenBy: "model",
    purpose: "starting point, catalyst, second-act crisis, dark night, climax, final state",
    feeds: [F.arc, F.events, F.presence, F.tone],
    needs: [{ field: "arc", has: (d) => has(d.arc) }, { field: "keyMoments", has: (d) => has(d.keyMoments) }, { field: "climax", has: (d) => has(d.climax) }, { field: "presence.density", has: (d) => has(d.presence.density) }, { field: "tone.byChapter", has: (d) => !!d.tone && has(d.tone.byChapter) }]
  },
  {
    id: "agency",
    title: "Key moral decisions and weight in the plot",
    page: 3,
    writtenBy: "model",
    purpose: "the choices that define its agency and how much the plot rests on it",
    feeds: [F.voice, F.events, F.standing, F.relations],
    needs: [{ field: "keyMoments", has: (d) => has(d.keyMoments) }, { field: "presence.share", has: (d) => d.presence.share > 0 }, { field: "generates", has: (d) => has(d.generates) }],
    limit: 'the engine ranks the scenes where it acts; calling a choice "moral" is the reading step'
  },
  {
    id: "echoes",
    title: "Echoes, motifs and territory",
    page: 3,
    writtenBy: "code",
    purpose: "chapters that repeat its situation with another cast, motifs it carries, what it owns",
    feeds: [F.parallels, F.themes, F.standing],
    needs: [{ field: "parallels", has: (d) => has(d.parallels) }, { field: "themes", has: (d) => has(d.themes) }, { field: "owns", has: (d) => has(d.owns) }]
  }
];
var SECONDARY = [
  {
    id: "function",
    title: "Dramatic function (mirror, catalyst, obstacle, mentor, antagonist)",
    page: 1,
    writtenBy: "model",
    purpose: "its role in the structure",
    feeds: [F.relations, F.standing, F.rank],
    needs: [{ field: "relations", has: (d) => has(d.relations) }, { field: "standing", has: (d) => has(d.standing) }, { field: "generates", has: (d) => has(d.generates) }],
    limit: "the role label is the reading step; the engine shows whom it stands against, beside or above"
  },
  {
    id: "profile",
    title: "Link to the main plot and basic profile",
    page: 1,
    writtenBy: "code",
    purpose: "identity, first and last sighting, voice, what is proper to it",
    feeds: [F.identity, F.sentences, F.voice, F.orbit],
    needs: [{ field: "identity", has: (d) => !!d.name }, { field: "introduced", has: (d) => has(d.introduced.line) }, { field: "voice", has: (d) => d.voice.dialogue + d.voice.action + d.voice.narration > 0 }, { field: "traits.elements", has: (d) => has(d.traits.elements) }]
  },
  {
    id: "dynamics",
    title: "How it affects and is affected by the protagonists",
    page: 2,
    writtenBy: "code",
    purpose: "relations, shared places, trend of each tie",
    feeds: [F.relations, F.world, F.tone],
    needs: [{ field: "relations", has: (d) => has(d.relations) }, { field: "relations.tone", has: (d) => d.relations.some((r) => !!r.tone) }, { field: "places", has: (d) => has(d.places) }]
  },
  {
    id: "subplot",
    title: "Subplot and evolution",
    page: 2,
    writtenBy: "model",
    purpose: "its own line from the first to the last page",
    feeds: [F.arc, F.events, F.presence, F.parallels],
    needs: [{ field: "arc", has: (d) => has(d.arc) }, { field: "keyMoments", has: (d) => has(d.keyMoments) }, { field: "route", has: (d) => has(d.route) }]
  }
];
var LOCATION = [
  {
    id: "sensory",
    title: "Sensory description, architecture and symbolism",
    page: 1,
    writtenBy: "model",
    purpose: "what the place is made of in the words around it",
    feeds: [F.orbit, F.themes],
    needs: [{ field: "traits.elements", has: (d) => has(d.traits.elements) }, { field: "circle.inner", has: (d) => has(d.circle.inner) }, { field: "themes", has: (d) => has(d.themes) }]
  },
  {
    id: "inhabitants",
    title: "Who lives or passes through",
    page: 1,
    writtenBy: "code",
    purpose: "natives, regulars, visitors and their weight; meetings and tension",
    feeds: [F.world, F.relations],
    needs: [{ field: "relations", has: (d) => has(d.relations) }, { field: "places", has: (d) => has(d.places) }]
  },
  {
    id: "events",
    title: "Critical dramatic events here",
    page: 1,
    writtenBy: "code",
    purpose: "the scenes of greatest charge that happen in it",
    feeds: [F.events, F.presence],
    needs: [{ field: "keyMoments", has: (d) => has(d.keyMoments) }, { field: "climax", has: (d) => has(d.climax) }]
  }
];
var SHEET_PAGES = { principal: 3, secondary: 2, location: 1 };
function sheetKind(d) {
  return d.kind === "place" ? "location" : d.rank === "primary" ? "principal" : "secondary";
}
function buildSections(d) {
  const k = sheetKind(d);
  return build(k === "principal" ? PRINCIPAL : k === "secondary" ? SECONDARY : LOCATION, d);
}
function buildReportPlan(r, target = 40) {
  const chars = r.dossiers.filter((d) => d.kind === "character");
  const principals = chars.filter((d) => d.rank === "primary");
  const secondaries = chars.filter((d) => d.rank !== "primary");
  const locations = r.dossiers.filter((d) => d.kind === "place");
  const themes = detectThemes(r), strengths = detectStrengths(r), weaknesses = detectWeaknesses(r);
  const chaptersWithEvents = r.chapters.filter((c) => c.events.length).length;
  const R = (field, ok) => ({ field, has: () => ok });
  const glob = (id, title, writtenBy, purpose, feeds, needs, limit, page = 1) => build([{ id, title, page, writtenBy, purpose, feeds, needs: needs.map((n) => R(n.field, n.ok)), limit }], null)[0];
  const blocks = [];
  const add = (id, title, pages, sections, sheets) => blocks.push({ id, title, pages, span: [0, 0], sections, sheets });
  add("technical", "1. Technical sheet and executive summary", 1, [
    glob("facts", "Hard data, tone, logline, premise, structural metrics", "model", "words, pages, chapters, cast size, tone of the whole, premise", [
      { ideas: [2, 13, 12, 43], source: "words \xB7 layers \xB7 structure", fn: "page(); chapter detection; front/back matter", gives: "hard data and structural metrics" },
      { ideas: [25, 57], source: "chapters.tone \xB7 tension", fn: "extended-lexicon tone, sentence = one event; tension per page", gives: "general tone and tension curve" },
      F.rank
    ], [{ field: "tension curve", ok: r.tension.curve.length > 0 }, { field: "metrics", ok: r.words > 0 && r.layers > 0 }, { field: "chapters", ok: r.chapters.length > 0 }, { field: "tone", ok: r.chapters.some((c) => !!c.tone) }, { field: "cast", ok: chars.length > 0 }], "logline and premise are written from the cast, the first scenes and the climax; the engine only holds the evidence")
  ]);
  add("synopsis", "2. Extended synopsis and dramatic outline", 5, [
    glob("synopsis", "Global synopsis with full ending", "model", "what happens, in order, to the end", [
      F.events,
      { ideas: [13, 23], source: "chapters", fn: "chapters as islands; event chains per chapter", gives: "ordered chapters with their scenes" }
    ], [{ field: "events", ok: chaptersWithEvents > 0 }, { field: "chapters", ok: r.chapters.length > 0 }, { field: "last chapter", ok: r.chapters.length > 1 }], void 0),
    glob("outline", "Outline chapter by chapter: turning points, tension peaks, rhythm", "code", "for every chapter: cast, place, scenes, charge, rarity signature, gaps", [
      { ideas: [13, 23, 25], source: "chapters \xB7 events \xB7 tone \xB7 signature", fn: "chapter loop", gives: "per-chapter outline with charge" },
      { ideas: [13], source: "structure.chapterSource \xB7 inferred", fn: "rhythm gap recovery", gives: "missing chapters flagged" },
      { ideas: [47], source: "morphisms.parallels", fn: "skeleton matching", gives: "echoing chapters" }
    ], [{ field: "chapters", ok: r.chapters.length > 0 }, { field: "events", ok: chaptersWithEvents === r.chapters.length && r.chapters.length > 0 }, { field: "tone", ok: r.chapters.every((c) => !!c.tone) }, { field: "parallels", ok: r.morphisms.parallels.length > 0 }], void 0, 2)
  ]);
  add("principals", "3. Principal characters (3 pages each)", principals.length * SHEET_PAGES.principal, [], principals.map((d) => ({ name: d.name, kind: "principal", pages: SHEET_PAGES.principal, sections: buildSections(d) })));
  add("secondaries", "4. Secondary characters (2 pages each)", secondaries.length * SHEET_PAGES.secondary, [], secondaries.map((d) => ({ name: d.name, kind: "secondary", pages: SHEET_PAGES.secondary, sections: buildSections(d) })));
  add("network", "5. Relationship map and network mechanics", 3, [
    glob("taxonomy", "Taxonomy of bonds", "code", "alliances, dependence, power hierarchies, latent enmities \u2014 classified", [F.relations, F.standing, F.tone], [{ field: "routePairs", ok: r.routePairs.some((p) => p.kind === "node-node") }, { field: "deference", ok: r.morphisms.hierarchy.deference.length > 0 }, { field: "hierarchy", ok: r.morphisms.hierarchy.characters.length > 0 }, { field: "bond tone", ok: r.tension.pairs.length > 0 }], "bonds are classified by proximity, trend, deference and the tone of the sentences the two share (hostile / strained / warm / calm); the lexicon behind the tone covers Spanish and English only"),
    glob("sociogram", "Sociogram and faction dynamics", "code", "groups of nodes, how they cluster, how things flow between them", [
      { ideas: [17, 20], source: "forest \xB7 treeRelations \xB7 knots", fn: "tree\u2013tree relations; strand crossings", gives: "clusters and hand-overs" },
      { ideas: [38], source: "circles", fn: "shared elements between circles", gives: "what groups share" }
    ], [{ field: "treeRelations", ok: r.treeRelations.length > 0 }, { field: "knots", ok: r.knots.pairs.length > 0 }, { field: "circles", ok: r.circles.length > 0 }], void 0, 2),
    glob("power", "Power mechanics and catalysts", "model", "friction points, shared secrets, how the balance shifts", [
      F.standing,
      { ideas: [45], source: "placeCasts.meetings", fn: "meetings with tension", gives: "friction points" },
      F.relations,
      F.tone
    ], [{ field: "hierarchy", ok: r.morphisms.hierarchy.characters.length > 0 }, { field: "meetings", ok: r.placeCasts.some((p) => p.meetings.length > 0) }, { field: "trends", ok: r.routePairs.some((p) => p.trend !== void 0) }, { field: "tension of bonds", ok: r.tension.pairs.some((p) => p.trend !== "steady" || p.tension > 0) }], "debts and secrets are not visible to letters alone; what is shown is where tension meets", 3)
  ]);
  add("world", "6. World, locations and human geography", 1 + locations.length, [
    glob("worldframe", "Global frame and worldbuilding", "model", "physical, social, atmospheric and temporal rules of the setting", [
      F.world,
      { ideas: [26], source: "timeAxis", fn: "calendar nodes, year axis", gives: "time frame" },
      { ideas: [48], source: "morphisms.hierarchy.containment", fn: "containment between places", gives: "nested geography" }
    ], [{ field: "places", ok: r.places.length > 0 }, { field: "placeCasts", ok: r.placeCasts.length > 0 }, { field: "containment", ok: r.morphisms.hierarchy.containment.length > 0 }, { field: "timeAxis", ok: r.timeAxis.months.length > 0 }], "rules of a world are read from what is repeated about it")
  ], locations.map((d) => ({ name: d.name, kind: "location", pages: SHEET_PAGES.location, sections: buildSections(d) })));
  const FEEDS_BY_FAMILY = {
    theme: [F.themes, { ideas: [32], source: "wordIndex", fn: "chain of every word of the theme: positions, before / after, solar system", gives: "where the theme's words stand and what surrounds them" }],
    transformation: [F.arc, { ideas: [32], source: "wordIndex", fn: "chain of the words gained and lost", gives: "positions and solar systems of what changes" }],
    structure: [F.parallels, { ideas: [13], source: "structure \xB7 chapters.inferred", fn: "chapter detection and rhythm gap", gives: "chapter skeletons and gaps" }],
    rhythm: [F.events, { ideas: [25], source: "chapters.tone", fn: "arousal per chapter", gives: "swings of intensity" }],
    world: [F.arc, { ideas: [40], source: "worldIdentity", fn: "solar system of every word, first third against last third", gives: "invariant and drifting words" }],
    place: [F.world, F.relations],
    voice: [F.voice, F.orbit, { ideas: [32], source: "wordIndex", fn: "chains of its distinctive words", gives: "what only it says" }],
    repetition: [{ ideas: [32], source: "wordIndex", fn: "chain of EVERY word (basic ones too): count, positions, what comes right before and after, solar system", gives: "stock phrases and words that crowd the page" }, { ideas: [3, 4], source: "catalogue \xB7 scales", fn: "rarity at page / chapter / work", gives: "what is common vs. exotic" }],
    pace: [F.events, { ideas: [25], source: "chapters.tone", fn: "arousal per chapter", gives: "flat stretches" }],
    presence: [F.presence, { ideas: [32], source: "wordIndex / dossiers.presence.density", fn: "density per slice", gives: "silences in a character's chain" }],
    relations: [F.relations, F.presence],
    identity: [F.identity, { ideas: [34], source: "injectivity.keptApart", fn: "pairs kept apart because both are names", gives: "confusable names" }]
  };
  const fromFinding = (f, kind, page) => {
    const feeds = FEEDS_BY_FAMILY[f.family] ?? [F.themes];
    return {
      id: f.id,
      title: f.title,
      page,
      writtenBy: "model",
      purpose: kind === "theme" ? "thesis, antithesis and subtext of this theme" : kind === "strength" ? "a powerful element, analysed alone on its page" : "a fault, its diagnosis and the fix",
      readPages: [],
      status: f.evidence.length ? "evidence-ready" : "thin",
      filled: ["evidence", ...f.words.length ? ["word chains"] : []],
      missing: f.words.length ? [] : ["word chains"],
      feeds,
      finding: f
    };
  };
  const findingBlock = (id, title, list, kind, extra = []) => add(id, title, list.length + extra.length, [...list.map((f, i) => fromFinding(f, kind, i + 1)), ...extra.map((e, i) => ({ ...e, page: list.length + i + 1 }))]);
  findingBlock(
    "themes",
    `7. Themes, symbols and deep subtext (${themes.length} detected, 1 page each)`,
    themes,
    "theme",
    themes.length ? [glob("glossary", "Symbols and motifs: glossary", "code", "recurring objects, images and metaphors with their flow through the book", [{ ideas: [19], source: "themeForest", fn: "theme trees with flow", gives: "glossary of motifs" }, { ideas: [49], source: "morphisms.thematic", fn: "thematic consistency", gives: "whether a motif holds or shifts" }], [{ field: "themeForest", ok: r.themeForest.length > 0 }, { field: "flow", ok: r.themeForest.some((t) => !!t.flow) }])] : []
  );
  findingBlock("strengths", `8. Strengths and powerful elements (${strengths.length} detected, 1 page each)`, strengths, "strength");
  findingBlock(
    "weaknesses",
    `9. Weaknesses, diagnosis and improvement plan (${weaknesses.length} detected, 1 page each + plan)`,
    weaknesses,
    "weakness",
    weaknesses.length ? [glob("plan", "Optimisation plan and rewrite proposal", "model", "step-by-step fixes for each fault above", [{ ideas: [41], source: "the faults above", fn: "one model call over the detected faults", gives: "the proposals" }], [{ field: "faults", ok: true }])] : []
  );
  add("conclusion", "10. Conclusions and global assessment", 1, [
    glob("verdict", "Definitive synthesis of literary and commercial value", "model", "what the work is worth and to whom", [F.themes, F.arc, F.rank], [{ field: "worldIdentity", ok: !!r.worldIdentity }, { field: "cast", ok: chars.length > 0 }, { field: "themes", ok: r.themeForest.length > 0 }], "commercial value needs the market, which is outside the text")
  ]);
  const merge = (rs, cap = 10) => {
    const v = rs.filter((x) => x && x[0] > 0).map((x) => [Math.min(x[0], x[1]), Math.min(Math.max(x[0], x[1]), Math.min(x[0], x[1]) + 2)]).sort((a, b) => a[0] - b[0]);
    const out = [];
    for (const x of v) {
      const l = out[out.length - 1];
      if (l && x[0] <= l[1] + 1) l[1] = Math.max(l[1], x[1]);
      else out.push([x[0], x[1]]);
    }
    let n = 0;
    return out.filter((x) => (n += x[1] - x[0] + 1) <= cap || n - (x[1] - x[0] + 1) === 0);
  };
  const chPages = (c) => r.chapters[c - 1] ? [r.chapters[c - 1].pages] : [];
  const topScene = (c) => {
    const ev = r.chapters[c - 1]?.events ?? [];
    const b = [...ev].sort((x, y) => Math.abs(y.charge) - Math.abs(x.charge))[0];
    return b ? [b.pages] : chPages(c).map((x) => [x[0], x[0]]);
  };
  const atPages = (w) => (r.wordIndex[w.toLowerCase()]?.at ?? []).slice(0, 6).map((p) => [p, p]);
  const forDossier = (d, id) => {
    const km = d.keyMoments.map((m) => m.pages), intro = d.introduced.page ? [[d.introduced.page, d.introduced.page]] : [], last = d.lastSeen.page ? [[d.lastSeen.page, d.lastSeen.page]] : [];
    const climax = d.climax ? [d.climax.pages] : [];
    switch (id) {
      case "anatomy":
      case "profile":
      case "sensory":
        return intro;
      case "mannerisms":
      case "agency":
      case "events":
        return km;
      case "wound":
        return [...intro, ...km.slice(0, 1)];
      case "lie":
        return [...km.slice(0, 1), ...km.slice(-1)];
      case "want":
        return d.route.slice(0, 2).map((x) => x.pages);
      case "need":
        return [...climax, ...last];
      case "obstacles":
      case "dynamics":
        return [...d.relations.map((x) => x.tone?.peak ? [x.tone.peak, x.tone.peak] : x.closest).filter((x) => !!x).slice(0, 3)];
      case "inhabitants":
      case "function":
        return d.relations.map((x) => x.closest).filter((x) => !!x).slice(0, 3);
      case "steps":
        return [...intro, ...km, ...climax, ...d.tone?.peak ? [[d.tone.peak, d.tone.peak]] : [], ...last];
      case "subplot":
        return [...intro, ...km.slice(0, 2), ...last];
      case "echoes":
        return d.parallels.flatMap((pp) => pp.chapters.flatMap((c) => topScene(c))).slice(0, 4);
      default:
        return [];
    }
  };
  const forFinding = (f) => {
    const [fam, key] = [f.id.split(":")[0], f.id.slice(f.id.indexOf(":") + 1)];
    if (fam === "theme") {
      const t = r.themeForest.find((x) => x.root === key);
      return t ? (t.peaks.length ? t.peaks : t.chapters.slice(0, 3)).flatMap(topScene) : [];
    }
    if (fam === "arc" || fam === "voice" || fam === "absent") {
      const d = r.dossiers.find((x) => x.name === key);
      return d ? [...d.introduced.page ? [[d.introduced.page, d.introduced.page]] : [], ...d.keyMoments.slice(0, 2).map((m) => m.pages), ...d.lastSeen.page ? [[d.lastSeen.page, d.lastSeen.page]] : []] : [];
    }
    if (fam === "echo") {
      const [a, b] = key.split("-").map(Number);
      return [...topScene(a), ...topScene(b)];
    }
    if (fam === "place") {
      const d = r.dossiers.find((x) => x.name === key);
      return d ? d.keyMoments.map((m) => m.pages) : [];
    }
    if (fam === "tic" || fam === "crowd") return atPages(key);
    if (fam === "flat") return topScene(Number(key));
    if (fam === "rhythm") {
      return r.chapters.slice().sort((x, y) => y.tone.arousal - x.tone.arousal).slice(0, 3).flatMap((c) => topScene(c.index));
    }
    if (fam === "gaps") return r.chapters.filter((c) => c.inferred).slice(0, 4).flatMap((c) => [[c.pages[0], c.pages[0]]]);
    if (fam === "dry") return r.chapters.filter((c) => c.mix.dialogue < 0.02).slice(0, 3).flatMap((c) => topScene(c.index));
    if (fam === "confusable") return [key].flatMap(() => []);
    if (fam === "world-return") return [[1, 1], [Math.max(1, r.layers), Math.max(1, r.layers)]];
    return [];
  };
  for (const b of blocks) {
    for (const sec of b.sections) {
      if (sec.finding) sec.readPages = merge(forFinding(sec.finding));
      else if (sec.id === "synopsis") sec.readPages = merge(r.chapters.flatMap((c) => topScene(c.index)), 60);
      else if (sec.id === "facts") sec.readPages = merge([[1, 1], [r.layers, r.layers]]);
      else if (sec.id === "verdict") sec.readPages = merge([...principals.flatMap((d) => d.climax ? [d.climax.pages] : []), [r.layers, r.layers]]);
    }
    for (const sh of b.sheets ?? []) {
      const d = r.dossiers.find((x) => x.name === sh.name);
      if (d) for (const sec of sh.sections) {
        sec.readPages = merge(forDossier(d, sec.id));
        const mine = d.sections.find((x) => x.id === sec.id);
        if (mine) mine.readPages = sec.readPages;
      }
    }
  }
  const wpp = r.words / Math.max(1, r.layers), OUT_PER_PAGE = 900, EVIDENCE_TOKENS = 1500, TOK_PER_WORD = 1.4;
  let aiSections = 0, pointed = 0, inTok = 0, outTok = 0;
  const countModel = (secs, pages, total) => {
    for (const sec of secs) if (sec.writtenBy === "model") {
      const pg = sec.readPages.reduce((a, x) => a + x[1] - x[0] + 1, 0);
      aiSections++;
      pointed += pg;
      inTok += EVIDENCE_TOKENS + pg * wpp * TOK_PER_WORD;
      outTok += OUT_PER_PAGE * pages / Math.max(1, total);
    }
  };
  for (const b of blocks) {
    if (b.sections.length) countModel(b.sections, b.pages, b.sections.length);
    for (const sh of b.sheets ?? []) countModel(sh.sections, sh.pages, sh.sections.length);
  }
  const ai = { sections: aiSections, pointedPages: pointed, inputTokens: Math.round(inTok), outputTokens: Math.round(outTok), wordsPerPage: Math.round(wpp), bookPages: r.layers };
  let cursor = 1;
  for (const b of blocks) {
    b.span = b.pages ? [cursor, cursor + b.pages - 1] : [cursor, cursor];
    cursor += b.pages;
  }
  const allocated = blocks.reduce((a, b) => a + b.pages, 0);
  return { ai, target: Math.max(target, allocated), themes: themes.length, strengths: strengths.length, weaknesses: weaknesses.length, allocated, annexPages: Math.max(0, target - allocated), principals: principals.map((d) => d.name), secondaries: secondaries.map((d) => d.name), locations: locations.map((d) => d.name), blocks };
}

// src/lib/nodes/word-index.ts
var STRIDE = 1 << 16;
var TOP = (m, n) => [...m].sort((a, b) => b[1] - a[1]).slice(0, n);
function buildWordIndex(inp) {
  const { words, pages, chapters, NP, nChapters } = inp;
  const id = /* @__PURE__ */ new Map(), list = [];
  const ids = new Int32Array(words.length);
  words.forEach((w, i) => {
    let x = id.get(w);
    if (x === void 0) {
      x = list.length;
      id.set(w, x);
      list.push(w);
    }
    ids[i] = x;
  });
  const V = list.length, bins = Math.min(Math.max(NP, 1), 40);
  const total = new Int32Array(V);
  for (let i = 0; i < ids.length; i++) total[ids[i]]++;
  const n = new Int32Array(V), first = new Int32Array(V).fill(1 << 30), last = new Int32Array(V);
  const density = Array.from({ length: V }, () => new Uint16Array(bins));
  const chap = Array.from({ length: V }, () => new Uint16Array(Math.max(1, nChapters)));
  const pageSets = Array.from({ length: V }, () => /* @__PURE__ */ new Set());
  const at = Array.from({ length: V }, () => []);
  const before = /* @__PURE__ */ new Map(), after = /* @__PURE__ */ new Map(), orbit = /* @__PURE__ */ new Map(), near = /* @__PURE__ */ new Map();
  const nodeId = /* @__PURE__ */ new Map(), nodeNames = [];
  const WIN = 6;
  const isFn = list.map((w) => inp.isFunction(w));
  const lonely = /* @__PURE__ */ new Map();
  for (let i = 0; i < words.length; i++) {
    const w = ids[i], pg = pages[i];
    if (total[w] === 1) lonely.set(w, i);
    n[w]++;
    first[w] = Math.min(first[w], pg);
    last[w] = Math.max(last[w], pg);
    pageSets[w].add(pg);
    density[w][Math.min(bins - 1, Math.floor((pg - 1) / Math.max(NP, 1) * bins))]++;
    if (chapters[i] >= 0) chap[w][Math.min(nChapters - 1, chapters[i])]++;
    if (at[w].length <= 80) at[w].push(pg);
    if (i > 0) {
      const k = ids[i - 1] * V + w;
      after.set(k, (after.get(k) ?? 0) + 1);
      const k2 = w * V + ids[i - 1];
      before.set(k2, (before.get(k2) ?? 0) + 1);
    }
    if (total[w] > 1) for (let d = 1; d <= WIN && i + d < words.length; d++) {
      const o = ids[i + d];
      if (o === w || total[o] < 2) continue;
      if (!isFn[o]) {
        const k = w * V + o;
        orbit.set(k, (orbit.get(k) ?? 0) + 1 / d);
      }
      if (!isFn[w]) {
        const k = o * V + w;
        orbit.set(k, (orbit.get(k) ?? 0) + 1 / d);
      }
    }
    const nm = inp.nodeAt(i);
    if (nm) {
      let nid = nodeId.get(nm);
      if (nid === void 0) {
        nid = nodeNames.length;
        nodeId.set(nm, nid);
        nodeNames.push(nm);
      }
      for (let d = -8; d <= 8; d++) {
        const j = i + d;
        if (j < 0 || j >= words.length || d === 0 || inp.nodeAt(j) === nm) continue;
        const k = ids[j] * STRIDE + nid;
        near.set(k, (near.get(k) ?? 0) + 1);
      }
    }
  }
  const perBefore = /* @__PURE__ */ new Map(), perAfter = /* @__PURE__ */ new Map(), perOrbit = /* @__PURE__ */ new Map();
  const bucket = (src, dst) => {
    for (const [k, c] of src) {
      const a = Math.floor(k / V), b = k % V;
      (dst.get(a) ?? dst.set(a, /* @__PURE__ */ new Map()).get(a)).set(b, c);
    }
  };
  bucket(before, perBefore);
  bucket(after, perAfter);
  for (const [k, c] of orbit) {
    const a = Math.floor(k / V), b = k % V;
    (perOrbit.get(a) ?? perOrbit.set(a, /* @__PURE__ */ new Map()).get(a)).set(b, c);
  }
  const nearBy = /* @__PURE__ */ new Map();
  for (const [k, c] of near) {
    const w = Math.floor(k / STRIDE), nid = k % STRIDE;
    (nearBy.get(w) ?? nearBy.set(w, /* @__PURE__ */ new Map()).get(w)).set(nid, c);
  }
  const out = {};
  for (let w = 0; w < V; w++) {
    const word = list[w], fn = inp.isFunction(word);
    const ob = perOrbit.get(w);
    let orb;
    if (total[w] === 1) {
      const i = lonely.get(w), seen = /* @__PURE__ */ new Map();
      for (let d = -WIN; d <= WIN; d++) {
        const j = i + d;
        if (d === 0 || j < 0 || j >= words.length || isFn[ids[j]]) continue;
        seen.set(ids[j], (seen.get(ids[j]) ?? 0) + 1 / Math.abs(d));
      }
      orb = [...seen].map(([o, c]) => [o, c * Math.max(0.2, inp.rarity(list[o]))]).sort((a, b) => b[1] - a[1]).slice(0, 8).map((x) => list[x[0]]);
    } else orb = ob ? [...ob].map(([o, c]) => [o, c * Math.max(0.2, inp.rarity(list[o]))]).sort((a, b) => b[1] - a[1]).slice(0, 8).map((x) => list[x[0]]) : [];
    const nr = nearBy.get(w);
    const entry = {
      n: n[w],
      function: fn,
      class: fn ? "function" : inp.classOf(word),
      pages: pageSets[w].size,
      first: first[w],
      last: last[w],
      density: [...density[w]],
      chapters: [...chap[w]],
      before: TOP(perBefore.get(w) ?? /* @__PURE__ */ new Map(), 5).map(([o, c]) => [list[o], c]),
      after: TOP(perAfter.get(w) ?? /* @__PURE__ */ new Map(), 5).map(([o, c]) => [list[o], c]),
      orbit: orb,
      near: nr ? TOP(nr, 3).map(([nid]) => nodeNames[nid]) : []
    };
    if (n[w] <= 80) entry.at = at[w];
    out[word] = entry;
  }
  return out;
}

// src/lib/utils/text-metrics.ts
var text_metrics_exports = {};
__export(text_metrics_exports, {
  countSyllables: () => countSyllables,
  extractiveSummary: () => extractiveSummary,
  keyPhrases: () => keyPhrases,
  readability: () => readability,
  topicClusters: () => topicClusters
});
function countSyllables(word) {
  const w = word.toLowerCase().replace(/[^a-záéíóúüñàèìòùâêîôûäëïöüãõç]/g, "");
  if (!w) return 0;
  const groups = w.match(/[aeiouáéíóúüàèìòùâêîôûäëïöãõ]+/g) ?? [];
  const STRONG = /[aeoáéóàèòâêôäëöãõ]/;
  let n = groups.reduce((total, g) => {
    let extra = 0;
    for (let i = 1; i < g.length; i++) {
      if (STRONG.test(g[i - 1]) && STRONG.test(g[i])) extra++;
    }
    return total + 1 + extra;
  }, 0) || 1;
  if (/[^aeiou]e$/.test(w) && n > 1) n--;
  return Math.max(1, n);
}
function readability(text, lang = "en") {
  const sentences = text.split(/[.!?…]+/).map((s) => s.trim()).filter((s) => s.length > 1);
  const words = text.match(/[\p{L}\p{N}']+/gu) ?? [];
  if (!sentences.length || !words.length) {
    return { ease: 0, grade: 0, level: "unknown", avgSentenceWords: 0, avgWordSyllables: 0, complexWordPercent: 0 };
  }
  const syllables = words.reduce((n, w) => n + countSyllables(w), 0);
  const asw = words.length / sentences.length;
  const aws = syllables / words.length;
  const complex = words.filter((w) => countSyllables(w) >= 3).length;
  const isEs = lang.slice(0, 2).toLowerCase() === "es";
  const ease = isEs ? 206.84 - 60 * aws - 1.02 * asw : 206.835 - 1.015 * asw - 84.6 * aws;
  const grade = 0.39 * asw + 11.8 * aws - 15.59;
  const clamped = Math.max(0, Math.min(100, ease));
  const level = clamped >= 80 ? "very easy" : clamped >= 65 ? "easy" : clamped >= 50 ? "moderate" : clamped >= 35 ? "demanding" : "very demanding";
  return {
    ease: Math.round(clamped),
    grade: Math.round(Math.max(0, grade) * 10) / 10,
    level,
    avgSentenceWords: Math.round(asw * 10) / 10,
    avgWordSyllables: Math.round(aws * 100) / 100,
    complexWordPercent: Math.round(complex / words.length * 100)
  };
}
var STOPWORDS = {
  es: new Set("el la los las un una unos unas de del al a ante bajo con contra desde durante en entre hacia hasta para por seg\xFAn sin sobre tras y o u pero sino que como cuando donde quien cual si no ni se le lo les me te nos os su sus mi mis tu tus este esta estos estas ese esa esos esas aquel aquella es son era eran ser estar haber ha han hab\xEDa hab\xEDan fue fueron muy m\xE1s menos ya tambi\xE9n solo s\xF3lo todo todos toda todas otro otra cada mismo as\xED aunque porque pues entonces despu\xE9s antes ahora aqu\xED all\xED bien tan".split(/\s+/)),
  en: new Set("the a an of to in on at by for from with without and or but so that which who whom whose this that these those is are was were be been being have has had do does did not no nor as if then than there here it its he she they we you i his her their our your my me him them us at up out over under again further once all any both each few more most other some such only own same too very can will just should now".split(/\s+/))
};
function stopwordsFor(lang) {
  return STOPWORDS[lang.slice(0, 2).toLowerCase()] ?? STOPWORDS.en;
}
var tokenize = (s) => s.toLowerCase().match(/[\p{L}\p{N}']{2,}/gu) ?? [];
function keyPhrases(text, lang = "en", limit = 12) {
  const stop = stopwordsFor(lang);
  const words = tokenize(text);
  if (words.length < 20) return [];
  const graph = /* @__PURE__ */ new Map();
  const freq = /* @__PURE__ */ new Map();
  const WINDOW2 = 4;
  for (let i = 0; i < words.length; i++) {
    const w = words[i];
    if (stop.has(w) || w.length < 3) continue;
    freq.set(w, (freq.get(w) ?? 0) + 1);
    if (!graph.has(w)) graph.set(w, /* @__PURE__ */ new Map());
    for (let j = i + 1; j < Math.min(i + WINDOW2, words.length); j++) {
      const v = words[j];
      if (stop.has(v) || v.length < 3 || v === w) continue;
      graph.get(w).set(v, (graph.get(w).get(v) ?? 0) + 1);
      if (!graph.has(v)) graph.set(v, /* @__PURE__ */ new Map());
      graph.get(v).set(w, (graph.get(v).get(w) ?? 0) + 1);
    }
  }
  let score = new Map([...graph.keys()].map((k) => [k, 1]));
  const DAMPING = 0.85;
  for (let round = 0; round < 3; round++) {
    const next = /* @__PURE__ */ new Map();
    for (const [node, edges] of graph) {
      let sum = 0;
      for (const [nb, weight] of edges) {
        const outWeight = [...graph.get(nb)?.values() ?? []].reduce((a, b) => a + b, 0) || 1;
        sum += (score.get(nb) ?? 1) * weight / outWeight;
      }
      next.set(node, 1 - DAMPING + DAMPING * sum);
    }
    score = next;
  }
  const strong = new Set([...score.entries()].sort((a, b) => b[1] - a[1]).slice(0, 60).map(([w]) => w));
  const phraseCount = /* @__PURE__ */ new Map();
  let run = [];
  const flush = () => {
    if (run.length) {
      const p = run.join(" ");
      phraseCount.set(p, (phraseCount.get(p) ?? 0) + 1);
      run = [];
    }
  };
  for (const w of words) {
    if (strong.has(w)) run.push(w);
    else {
      flush();
    }
    if (run.length >= 3) flush();
  }
  flush();
  return [...phraseCount.entries()].map(([phrase, count]) => ({
    phrase,
    count,
    score: phrase.split(" ").reduce((n, w) => n + (score.get(w) ?? 0), 0) * Math.log(1 + count)
  })).filter((p) => p.count > 1 || p.phrase.includes(" ")).sort((a, b) => b.score - a.score).slice(0, limit).map((p) => ({ ...p, score: Math.round(p.score * 100) / 100 }));
}
function topicClusters(text, lang = "en", count = 5) {
  const phrases = keyPhrases(text, lang, 40);
  if (phrases.length === 0) return [];
  const stop = stopwordsFor(lang);
  const words = tokenize(text).filter((w) => !stop.has(w) && w.length > 3);
  const positions = /* @__PURE__ */ new Map();
  words.forEach((w, i) => {
    if (!positions.has(w)) positions.set(w, []);
    positions.get(w).push(i);
  });
  const seeds = phrases.slice(0, count * 3).map((p) => p.phrase.split(" ")[0]);
  const used = /* @__PURE__ */ new Set();
  const topics = [];
  for (const seed of seeds) {
    if (used.has(seed) || topics.length >= count) continue;
    const seedPos = positions.get(seed) ?? [];
    if (seedPos.length < 2) continue;
    const near = /* @__PURE__ */ new Map();
    for (const p of seedPos) {
      for (let j = Math.max(0, p - 30); j < Math.min(words.length, p + 30); j++) {
        const w = words[j];
        if (w === seed || used.has(w)) continue;
        near.set(w, (near.get(w) ?? 0) + 1);
      }
    }
    const terms = [seed, ...[...near.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5).map(([w]) => w)];
    terms.forEach((t) => used.add(t));
    topics.push({ terms, weight: Math.round(seedPos.length / words.length * 1e4) / 100 });
  }
  return topics.sort((a, b) => b.weight - a.weight);
}
function extractiveSummary(text, lang = "en", sentenceCount = 5) {
  const stop = stopwordsFor(lang);
  const sentences = text.split(/(?<=[.!?…])\s+/).map((s) => s.trim()).filter((s) => s.split(/\s+/).length >= 6);
  if (sentences.length <= sentenceCount) return sentences;
  const freq = /* @__PURE__ */ new Map();
  for (const w of tokenize(text)) {
    if (stop.has(w) || w.length < 3) continue;
    freq.set(w, (freq.get(w) ?? 0) + 1);
  }
  const max = Math.max(1, ...freq.values());
  const scored = sentences.map((s, i) => {
    const ws = tokenize(s).filter((w) => !stop.has(w) && w.length >= 3);
    if (!ws.length) return { i, s, score: 0 };
    const score = ws.reduce((n, w) => n + (freq.get(w) ?? 0) / max, 0) / Math.sqrt(ws.length);
    return { i, s, score };
  });
  return scored.sort((a, b) => b.score - a.score).slice(0, sentenceCount).sort((a, b) => a.i - b.i).map((x) => x.s);
}

// src/lib/nodes/engine.ts
var BINS_MAX = 40;
var round2 = (x) => Math.round(x * 100) / 100;
var DASH_START = /^[—–―«“「『"]/;
var WINDOW = 14;
var CJK_LIKE = /[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Thai}\p{Script=Lao}\p{Script=Khmer}\p{Script=Myanmar}]/u;
var wl = (w) => CJK_LIKE.test(w) ? [...w].length * 2 : w.length;
var isCapBase = (w) => /^\p{Lu}/u.test(w) && w.length > 1 && !/['’]/.test(w);
var isAllCaps = (w) => /^\p{Lu}{2,}$/u.test(w);
var normCache = /* @__PURE__ */ new WeakMap();
var normOf = (A) => {
  const c = normCache.get(A);
  if (c && c.size === A.size) return c.n;
  let n = 0;
  for (const v of A.values()) n += v * v;
  normCache.set(A, { n, size: A.size });
  return n;
};
var mergeBag = (into, from) => {
  for (const [w, c] of from) into.set(w, (into.get(w) ?? 0) + c);
  normCache.delete(into);
};
var cosine = (A, B) => {
  const [S, T] = A.size <= B.size ? [A, B] : [B, A];
  let d = 0;
  for (const [w, c] of S) {
    const o = T.get(w);
    if (o) d += c * o;
  }
  return d / Math.sqrt(normOf(A) * normOf(B) || 1);
};
function analyzeNodes(text, opts = {}) {
  const t0 = Date.now();
  const timings = {};
  let curStage = "start", lastLap = t0;
  const lap = (next) => {
    const t = Date.now();
    timings[curStage] = (timings[curStage] ?? 0) + t - lastLap;
    lastLap = t;
    curStage = next;
  };
  const lang = opts.language ?? detectLang(text);
  const L = LEXICONS[lang];
  const stopSet = lang === "auto" ? /* @__PURE__ */ new Set() : L.stop;
  lap("1 clean");
  const lineCount = /* @__PURE__ */ new Map();
  for (const l of text.split("\n")) {
    const s = l.trim();
    if (s && s.length <= 14) lineCount.set(s, (lineCount.get(s) ?? 0) + 1);
  }
  const junk = new Set([...lineCount].filter(([s, c]) => c >= 3 && !/^\p{Lu}{3,}$/u.test(s)).map(([s]) => s));
  const rawPages = text.split("\f");
  const furniture = /* @__PURE__ */ new Set();
  if (rawPages.length >= 2) {
    const onPages = /* @__PURE__ */ new Map();
    for (const pg of rawPages) for (const k of new Set(pg.split("\n").map((l) => l.trim().replace(/\d+/g, "#").replace(/\s+/g, " ")).filter(Boolean))) onPages.set(k, (onPages.get(k) ?? 0) + 1);
    const need = rawPages.length >= 8 ? Math.max(4, rawPages.length * 0.25) : Math.max(2, Math.ceil(rawPages.length * 0.5));
    for (const [k, c] of onPages) if (c >= need && k.length >= (rawPages.length >= 8 ? 6 : 12) && k !== k.toUpperCase()) furniture.add(k);
  }
  const pdfPages = rawPages.map((p) => p.split("\n").filter((l) => !junk.has(l.trim()) && !furniture.has(l.trim().replace(/\d+/g, "#").replace(/\s+/g, " "))).join("\n").replace(/\u200b/g, ""));
  const raw = pdfPages.join(" \f ").replace(/-\n(?=[a-zñáéíóú])/g, "").replace(/[ \t]*\n[ \t]*/g, " \xB6 ").replace(/ +/g, " ");
  const inParen = new Uint8Array(raw.length);
  {
    let d = 0;
    for (let i = 0; i < raw.length; i++) {
      if (raw[i] === "(") d++;
      inParen[i] = d > 0 ? 1 : 0;
      if (raw[i] === ")" && d > 0) d--;
    }
  }
  const slugs = [...raw.matchAll(/(\d+)\.\s*(INT|EXT)\.?\s+(.+?)\.\s+([A-ZÁÉÍÓÚ ]+)\./g)].map((m) => ({ a: m.index ?? 0, b: (m.index ?? 0) + m[0].length, id: m[1], ie: m[2], place: m[3].trim(), time: m[4].trim() }));
  const inSlug = (i) => slugs.some((s) => i >= s.a && i < s.b);
  lap("2 tokens");
  const toks = [];
  let pdfPg = 1;
  const SPACELESS = /[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Thai}\p{Script=Lao}\p{Script=Khmer}\p{Script=Myanmar}]/u;
  const scriptRuns = (w) => w.match(/\p{Script=Han}+|\p{Script=Hiragana}+|\p{Script=Katakana}+|[\p{Script=Thai}\p{Script=Lao}\p{Script=Khmer}\p{Script=Myanmar}]+|[^\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Thai}\p{Script=Lao}\p{Script=Khmer}\p{Script=Myanmar}]+/gu) ?? [w];
  const segLex = /* @__PURE__ */ new Map();
  const isLong = (r) => /^[\p{Script=Han}\p{Script=Thai}\p{Script=Lao}\p{Script=Khmer}\p{Script=Myanmar}]+$/u.test(r);
  if (SPACELESS.test(raw)) {
    const runs = [];
    for (const m of raw.matchAll(/[\p{L}\p{M}]+/gu)) if (SPACELESS.test(m[0])) {
      for (const r of scriptRuns(m[0])) if (isLong(r) && [...r].length >= 2) runs.push(r);
    }
    const cnt = /* @__PURE__ */ new Map();
    for (const r of runs) {
      const cs = [...r];
      for (let n = 1; n <= 4; n++) for (let i = 0; i + n <= cs.length; i++) {
        const g = cs.slice(i, i + n).join("");
        cnt.set(g, (cnt.get(g) ?? 0) + 1);
      }
    }
    const thr = Math.max(2, Math.round(runs.length / 4e3));
    for (const [g, c] of cnt) {
      const cs = [...g];
      if (cs.length < 2 || c < thr) continue;
      let coh = 1;
      for (let i = 1; i < cs.length; i++) coh = Math.min(coh, c / Math.max(1, Math.min(cnt.get(cs.slice(0, i).join("")) ?? 1, cnt.get(cs.slice(i).join("")) ?? 1)));
      if (coh >= 0.5) segLex.set(g, c * 1e3 + Math.round(coh * 999));
    }
  }
  const segment = (r) => {
    const cs = [...r];
    if (cs.length < 2 || !segLex.size) return cs.length < 2 ? [r] : cs;
    const best2 = new Array(cs.length + 1).fill(-1e9), from = new Array(cs.length + 1).fill(0);
    best2[0] = 0;
    for (let i = 1; i <= cs.length; i++) for (let n = 1; n <= 4 && n <= i; n++) {
      const g = cs.slice(i - n, i).join(""), e = n === 1 ? 0 : segLex.get(g) ?? 0, c = Math.floor(e / 1e3), coh = e % 1e3 / 999;
      const sc = n === 1 ? 0.05 : c ? Math.log(c) * coh * Math.sqrt(n) : -1e9;
      if (best2[i - n] + sc > best2[i]) {
        best2[i] = best2[i - n] + sc;
        from[i] = i - n;
      }
    }
    const out = [];
    for (let i = cs.length; i > 0; i = from[i]) out.unshift(cs.slice(from[i], i).join(""));
    return out;
  };
  for (const m of raw.matchAll(/\f|[\p{L}\p{M}][\p{L}\p{M}'’]*|\d+/gu)) {
    if (m[0] === "\f") {
      pdfPg++;
      continue;
    }
    const idx = m.index ?? 0;
    if (SPACELESS.test(m[0])) {
      let off = idx;
      for (const r of scriptRuns(m[0])) {
        for (const sg of isLong(r) ? segment(r) : [r]) {
          toks.push({ w: sg, idx: off, end: off + sg.length, pdf: pdfPg, par: inParen[off] === 1, slug: inSlug(off) });
          off += sg.length;
        }
      }
      continue;
    }
    toks.push({ w: m[0].replace(L.possessive, ""), idx, end: idx + m[0].length, pdf: pdfPg, par: inParen[idx] === 1, slug: inSlug(idx) });
  }
  const realPages = pdfPg > 1;
  const PAGE = opts.pageWords ?? 250;
  const page = (k) => realPages ? toks[k].pdf : Math.floor(k / PAGE) + 1;
  const NP = toks.length ? page(toks.length - 1) : 0;
  const letterCount = (raw.match(/\p{L}/gu) ?? []).length, casedCount = (raw.match(/[\p{Lu}\p{Ll}]/gu) ?? []).length;
  const caseless = letterCount > 50 && casedCount / letterCount < 0.2;
  const caselessCand = /* @__PURE__ */ new Set();
  const isCap = (w) => caseless ? caselessCand.has(w) : isCapBase(w);
  const sid = new Int32Array(toks.length);
  {
    let c = 0;
    for (let k = 0; k < toks.length; k++) {
      sid[k] = c;
      if (k + 1 < toks.length && /[.!?…。！？｡؟۔।॥¶\f]/.test(raw.slice(toks[k].end, toks[k + 1].idx))) c++;
    }
  }
  const lw = (k) => toks[k]?.w.toLowerCase() ?? "";
  const before = (k) => raw.slice(Math.max(0, toks[k].idx - 4), toks[k].idx);
  const sentStart = (k) => k === 0 || !(abbrTok[k - 1] === 1) && (/[.!?"”»—¶(。！？｡؟۔।]\s*$/.test(before(k)) || /[¿¡]$/.test(before(k).trim()));
  const alone = (k) => (k === 0 || /¶\s*$/.test(before(k))) && (/^\s*(\([^)]*\)\s*)?¶/.test(raw.slice(toks[k].end, toks[k].end + 40)) || raw.slice(toks[k].end).trim() === "");
  const abbrTok = new Uint8Array(toks.length);
  {
    const tot = /* @__PURE__ */ new Map(), hit = /* @__PURE__ */ new Map(), at = [];
    for (let k = 0; k < toks.length - 1; k++) {
      const w = toks[k].w;
      if (w.length > 4 || !/^\p{Lu}/u.test(w) || w !== w[0] + w.slice(1).toLowerCase()) continue;
      tot.set(w, (tot.get(w) ?? 0) + 1);
      const gap = raw.slice(toks[k].end, toks[k + 1].idx);
      if (/^\.[ \t]+$/.test(gap) && /^\p{Lu}/u.test(toks[k + 1].w)) {
        hit.set(w, (hit.get(w) ?? 0) + 1);
        at.push(k);
      }
    }
    const ok = new Set([...hit].filter(([w, h]) => h >= 2 && h / (tot.get(w) ?? 1) >= 0.8).map(([w]) => w));
    for (const k of at) if (ok.has(toks[k].w)) abbrTok[k] = 1;
  }
  const glue = (a, b) => {
    const g = raw.slice(toks[a].end, toks[b].idx).trim();
    return g === "" || g === "." && abbrTok[a] === 1;
  };
  lap("2b function words of THIS text");
  const monthSet0 = new Set(L.months);
  const freq = /* @__PURE__ */ new Map();
  for (const t of toks) {
    const w = t.w.toLowerCase();
    freq.set(w, (freq.get(w) ?? 0) + 1);
  }
  const topFreq = new Set([...freq].sort((a, b) => b[1] - a[1]).slice(0, 80).map((x) => x[0]));
  if (lang === "auto") {
    const cand2 = [...freq].sort((a, b) => b[1] - a[1]).slice(0, NP < 8 ? 40 : 150).map((x) => x[0]);
    const capN = /* @__PURE__ */ new Map(), pgsOf = /* @__PURE__ */ new Map();
    const sentCover = /* @__PURE__ */ new Map();
    toks.forEach((t, k) => {
      const w = t.w.toLowerCase();
      (sentCover.get(w) ?? sentCover.set(w, /* @__PURE__ */ new Set()).get(w)).add(sid[k]);
    });
    toks.forEach((t, k) => {
      const w = t.w.toLowerCase();
      if (isCap(t.w) && !sentStart(k)) capN.set(w, (capN.get(w) ?? 0) + 1);
      (pgsOf.get(w) ?? pgsOf.set(w, /* @__PURE__ */ new Set()).get(w)).add(page(k));
    });
    for (const w of cand2) {
      const capShare = (capN.get(w) ?? 0) / (freq.get(w) ?? 1);
      if (caseless) {
        const cov = (sentCover.get(w)?.size ?? 0) / Math.max(1, sid[toks.length - 1] + 1);
        if (cov < 0.25) continue;
      }
      if (capShare >= 0.3) continue;
      if (NP >= 8 && (pgsOf.get(w)?.size ?? 0) < NP * 0.5) continue;
      stopSet.add(w);
    }
  }
  lap("2c voice");
  const tmode = new Uint8Array(toks.length);
  {
    const DASH = "\u2014\u2013\u2015", OPEN = "\xAB\u201C\u300C\u300E", CLOSE = "\xBB\u201D\u300D\u300F", TERMINAL = '.!?\u2026:\xBB\u201D"\u300D\u300F)\u3002\uFF01\uFF1F';
    let mode = 0, ti = 0, paraStart = true, last = "";
    for (let i = 0; i < raw.length; i++) {
      while (ti < toks.length && toks[ti].idx === i) {
        tmode[ti] = mode;
        ti++;
      }
      const c = raw[i];
      if (c === "\xB6" || c === "\f") {
        let j = i + 1, breaks = c === "\f" ? 2 : 1;
        while (j < raw.length && (raw[j] === " " || raw[j] === "\xB6" || raw[j] === "\f")) {
          if (raw[j] !== " ") breaks++;
          j++;
        }
        const next = raw[j] ?? "";
        const startsNew = /[\p{Lu}¿¡\d]/u.test(next) || DASH.includes(next) || OPEN.includes(next) || next === '"';
        if (j >= raw.length || breaks >= 2 || TERMINAL.includes(last) && startsNew) {
          mode = 0;
          paraStart = true;
        }
        continue;
      }
      if (c === " ") continue;
      if (DASH.includes(c)) {
        mode = paraStart ? 1 : mode === 1 ? 2 : mode === 2 ? 1 : 2;
      } else if (OPEN.includes(c)) mode = 1;
      else if (CLOSE.includes(c)) mode = 0;
      else if (c === '"') mode = mode === 1 ? 0 : 1;
      paraStart = false;
      last = c;
    }
  }
  {
    const cueCount = /* @__PURE__ */ new Map();
    for (let k = 0; k < toks.length; k++) if (isAllCaps(toks[k].w) && !toks[k].slug && alone(k)) cueCount.set(toks[k].w, (cueCount.get(toks[k].w) ?? 0) + 1);
    const cues = new Set([...cueCount].filter(([, c]) => c >= 2).map(([w]) => w));
    if (cues.size) {
      let speaking = false;
      for (let k = 0; k < toks.length; k++) {
        if (cues.has(toks[k].w) && alone(k)) {
          speaking = true;
          tmode[k] = 1;
          continue;
        }
        if (k > 0 && /¶\s*¶/.test(raw.slice(toks[k - 1].end, toks[k].idx))) speaking = false;
        if (speaking && !toks[k].slug) tmode[k] = toks[k].par ? 2 : 1;
      }
    }
  }
  if (caseless) {
    const nSent = Math.max(1, sid[toks.length - 1] + 1), cover = /* @__PURE__ */ new Map(), near2 = /* @__PURE__ */ new Map();
    const inQ = (j) => j >= 0 && j < toks.length && tmode[j] === 1;
    toks.forEach((t, k) => {
      (cover.get(t.w) ?? cover.set(t.w, /* @__PURE__ */ new Set()).get(t.w)).add(sid[k]);
      if (!inQ(k) && (inQ(k - 1) || inQ(k - 2) || inQ(k - 3) || inQ(k + 1) || inQ(k + 2) || inQ(k + 3) || inQ(k + 4))) near2.set(t.w, (near2.get(t.w) ?? 0) + 1);
    });
    for (const orig of cover.keys()) {
      const w = orig.toLowerCase(), c = freq.get(w) ?? 0;
      if (/\d/.test(orig) || stopSet.has(w) || monthSet0.has(w)) continue;
      if (/^\p{Script=Katakana}{2,}$/u.test(orig)) {
        if (c >= 2) caselessCand.add(orig);
        continue;
      }
      if (c >= 4 && wl(orig) >= 4 && (cover.get(orig)?.size ?? 0) / nSent < 0.25 && (near2.get(orig) ?? 0) / c >= 0.3) caselessCand.add(orig);
    }
  }
  lap("2d structure");
  const layerOf = (k) => page(k);
  const proseShare = new Array(NP).fill(0), layerTokens = new Array(NP).fill(0);
  toks.forEach((t, k) => {
    const p = layerOf(k) - 1;
    layerTokens[p]++;
    if (topFreq.has(t.w.toLowerCase())) proseShare[p]++;
  });
  for (let p = 0; p < NP; p++) proseShare[p] = layerTokens[p] ? proseShare[p] / layerTokens[p] : 0;
  let body = null;
  if (NP >= 8) {
    const sorted = [...proseShare].sort((a, b) => a - b), ref = sorted[Math.floor(sorted.length * 0.6)];
    const isBody = proseShare.map((v) => v >= ref * 0.8);
    let bestLo = -1, bestHi = -1, lo = -1, gaps = 0;
    for (let p = 0; p <= NP; p++) {
      if (p < NP && isBody[p]) {
        if (lo < 0) lo = p;
        gaps = 0;
      } else if (lo >= 0 && (p === NP || ++gaps > 2)) {
        const hi = p === NP ? p - 1 - gaps : p - gaps;
        if (hi - lo > bestHi - bestLo) {
          bestLo = lo;
          bestHi = hi;
        }
        lo = -1;
        gaps = 0;
      }
    }
    if (bestLo >= 0 && bestHi - bestLo + 1 >= NP * 0.4 && (bestLo > 0 || bestHi < NP - 1)) body = [bestLo + 1, bestHi + 1];
  }
  const inBody = (k) => !body || layerOf(k) >= body[0] && layerOf(k) <= body[1];
  let allLines = [];
  const headings = [];
  const chapterMarks = [];
  let chapterSource = "none";
  {
    const lines = [];
    let tc = 0;
    const allGaps = [];
    pdfPages.forEach((pg, pi) => {
      const ls = pg.split("\n");
      ls.forEach((l, li) => {
        const t = l.trim();
        const n = (t.match(/[\p{L}\p{N}]+/gu) ?? []).length;
        if (t && li > 0) {
          let g = 0;
          for (let q2 = li - 1; q2 >= 0 && ls[q2].trim() === ""; q2--) g++;
          if (g > 0) allGaps.push(g);
        }
        if (t && n >= 1 && n <= 8 && !DASH_START.test(t) && /\p{L}|\d/u.test(t)) {
          let j = li + 1, seen = 0, nw = 0;
          for (; j < ls.length && seen < 3; j++) {
            if (ls[j].trim() === "") continue;
            seen++;
            nw = Math.max(nw, (ls[j].match(/[\p{L}\p{N}]+/gu) ?? []).length);
          }
          lines.push({
            page: realPages ? pi + 1 : Math.floor(tc / PAGE) + 1,
            text: t,
            words: n,
            term: /[.!?…,;:]$/.test(t),
            prevBlank: li === 0 || ls[li - 1].trim() === "",
            nextBlank: li === ls.length - 1 || ls[li + 1].trim() === "",
            nextWords: nw,
            gapAbove: (() => {
              let g = 0;
              for (let q2 = li - 1; q2 >= 0 && ls[q2].trim() === ""; q2--) g++;
              return g;
            })(),
            gapBelow: (() => {
              let g = 0;
              for (let q2 = li + 1; q2 < ls.length && ls[q2].trim() === ""; q2++) g++;
              return g;
            })()
          });
        }
        tc += n;
      });
    });
    allLines = lines;
    const lineFreq = /* @__PURE__ */ new Map();
    for (const l of lines) lineFreq.set(l.text, (lineFreq.get(l.text) ?? 0) + 1);
    for (let i = lines.length - 1; i >= 0; i--) if ((lineFreq.get(lines[i].text) ?? 0) >= 3 && lines[i].text === lines[i].text.toUpperCase() && !/\d/.test(lines[i].text)) lines.splice(i, 1);
    const shape = (t) => t.toLowerCase().replace(/\b[ivxlcdm]+\b/g, "#").replace(/\d+/g, "#");
    const byShape = /* @__PURE__ */ new Map();
    for (const l of lines) if (l.prevBlank && !l.term && /#/.test(shape(l.text))) (byShape.get(shape(l.text)) ?? byShape.set(shape(l.text), []).get(shape(l.text))).push(l);
    for (const grp of byShape.values()) if (grp.length >= 3 && grp.length < NP * 0.5 && new Set(grp.map((g) => g.text)).size >= 3) for (const g of grp) {
      headings.push({ page: g.page, text: g.text, numbered: true });
      chapterMarks.push({ page: g.page, title: g.text });
    }
    const bodyLen0 = body ? body[1] - body[0] + 1 : NP, numMarks = chapterMarks.slice(), numPages = numMarks.map((m) => m.page);
    const numCovers = numMarks.length >= 6 || numMarks.length >= 3 && (Math.max(...numPages) - Math.min(...numPages)) / Math.max(1, bodyLen0) >= 0.5;
    if (chapterMarks.length >= 3 && numCovers) chapterSource = "numbered";
    else {
      chapterMarks.length = 0;
      const bodyOk = (l) => !body || l.page >= body[0] && l.page <= body[1];
      const gaps = allGaps.slice().sort((a, b) => a - b), g0 = gaps.length ? gaps[Math.floor(gaps.length / 2)] : 1, bigGap = Math.max(g0 + 2, Math.ceil(g0 * 1.8));
      const sentenceLike = (l) => /[.!?…]$/.test(l.text) && l.words >= 4;
      const gapIslands = lines.filter((l) => l.gapAbove >= bigGap && l.gapBelow >= bigGap && l.words <= 8 && !sentenceLike(l) && !DASH_START.test(l.text) && l.nextWords >= 5 && bodyOk(l));
      const strict0 = lines.filter((l) => l.prevBlank && l.nextBlank && l.words <= 8 && /^\p{Lu}/u.test(l.text) && !/\d/.test(l.text) && l.nextWords >= 7 && bodyOk(l));
      const strict = strict0.filter((l) => !sentenceLike(l));
      const loose = lines.filter((l) => l.prevBlank && l.words <= 4 && /^\p{Lu}/u.test(l.text) && l.nextWords >= 7 && (!l.term || l.words <= 3) && bodyOk(l));
      const bodyLen = body ? body[1] - body[0] + 1 : NP;
      const fits = (a) => a.length >= 3 && a.length <= NP / 2 && bodyLen / a.length >= 2;
      const pick = gapIslands.length >= 5 && fits(gapIslands) ? gapIslands : fits(strict) ? strict : fits(loose) ? loose : null;
      if (pick) {
        for (const g of pick) {
          headings.push({ page: g.page, text: g.text, numbered: false });
          chapterMarks.push({ page: g.page, title: g.text });
        }
        chapterSource = pick === loose ? "titles-loose" : "titles";
        for (const m of numMarks) if (!chapterMarks.some((x) => x.page === m.page)) chapterMarks.push(m);
      } else if (numMarks.length >= 3) {
        for (const m of numMarks) chapterMarks.push(m);
        chapterSource = "numbered";
      }
    }
    const used = new Set(headings.map((h) => h.text));
    for (const l of lines) if (l.prevBlank && !l.term && !used.has(l.text) && (!body || l.page < body[0] || l.page > body[1]) && headings.length < 80) headings.push({ page: l.page, text: l.text, numbered: false });
    headings.sort((a, b) => a.page - b.page);
  }
  let bodyFrom = body ? body[0] : 1, bodyTo = body ? body[1] : NP;
  let starts = [...new Set(chapterMarks.map((m) => m.page).filter((pg) => pg >= bodyFrom && pg <= bodyTo))].sort((x, y) => x - y);
  if (starts.length < 2) {
    chapterSource = NP >= 8 ? "windows" : "none";
    const n = NP >= 8 ? Math.min(12, Math.max(2, Math.round((bodyTo - bodyFrom + 1) / 8))) : 1;
    starts = Array.from({ length: n }, (_, i) => bodyFrom + Math.round(i * (bodyTo - bodyFrom + 1) / n));
  } else if (starts[0] > bodyFrom) starts.unshift(bodyFrom);
  const inferred = /* @__PURE__ */ new Map();
  if (starts.length >= 6 && (chapterSource === "numbered" || chapterSource === "titles" || chapterSource === "titles-loose")) {
    const sp = starts.slice(1).map((v, i) => v - starts[i]).sort((a, b) => a - b), med = sp[Math.floor(sp.length / 2)];
    const pageSets = Array.from({ length: NP + 2 }, () => /* @__PURE__ */ new Set());
    toks.forEach((t, k) => {
      const w = t.w.toLowerCase();
      if (wl(w) >= 4 && !topFreq.has(w) && !stopSet.has(w) && !/\d/.test(w)) pageSets[page(k)].add(w);
    });
    const shift = (pg) => {
      const A = /* @__PURE__ */ new Set(), B = /* @__PURE__ */ new Set();
      for (const d of [-2, -1]) pageSets[pg + d]?.forEach((w) => A.add(w));
      for (const d of [0, 1]) pageSets[pg + d]?.forEach((w) => B.add(w));
      let i = 0;
      for (const w of A) if (B.has(w)) i++;
      return 1 - i / (A.size + B.size - i || 1);
    };
    const dev = sp.map((v) => Math.abs(v - med)).sort((a, b) => a - b), mad = dev[Math.floor(dev.length / 2)];
    const regular = med > 0 && mad / med <= 0.12;
    const bounds = [...starts, bodyTo + 1];
    const shifts = /* @__PURE__ */ new Map();
    for (let q2 = bodyFrom + 2; q2 <= bodyTo - 1; q2++) shifts.set(q2, shift(q2));
    const sortedShifts = [...shifts.values()].sort((x, y) => x - y), p80 = sortedShifts[Math.floor(sortedShifts.length * 0.8)] ?? 1, p90 = sortedShifts[Math.floor(sortedShifts.length * 0.9)] ?? 1;
    for (let g = 0; g + 1 < bounds.length; g++) {
      const a = bounds[g], b = bounds[g + 1], span = b - a;
      if (span <= med * (regular ? 1.6 : 1.4) || span < 6) continue;
      const missing = Math.max(1, Math.round(span / med) - 1);
      const margin = Math.max(2, Math.round(med * 0.4));
      const taken = [];
      for (let m = 1; m <= missing; m++) {
        const expect = a + Math.round(span * m / (missing + 1));
        let best2 = null;
        for (let q2 = a + margin; q2 <= b - margin; q2++) {
          if (taken.some((t) => Math.abs(t - q2) < margin)) continue;
          const isl = allLines.filter((l) => l.page === q2 && l.prevBlank && l.nextBlank && l.words <= 10 && /^\p{Lu}/u.test(l.text) && !l.term && !DASH_START.test(l.text))[0];
          const sh = shifts.get(q2) ?? 0;
          const score = (isl ? 2 : 0) + sh - Math.abs(q2 - expect) / span;
          if (!regular && !isl && sh < p90) continue;
          if (!best2 || score > best2.score) best2 = { pg: q2, score, title: isl?.text ?? "", by: isl ? sh >= p80 ? "island+shift" : "island" : "shift" };
        }
        if (best2 && !starts.includes(best2.pg)) {
          starts.push(best2.pg);
          taken.push(best2.pg);
          inferred.set(best2.pg, best2.by);
          chapterMarks.push({ page: best2.pg, title: best2.title || "Chapter ?", inferred: true });
        }
      }
    }
    starts.sort((x, y) => x - y);
  }
  const frontSections = [], backSections = [];
  {
    const fold = (t) => t.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^\p{L}]/gu, "");
    const markAt = (pg) => chapterMarks.find((m) => m.page === pg);
    let tocLabel = null;
    const labelled = /* @__PURE__ */ new Set(), unlabelled = /* @__PURE__ */ new Set();
    let firstLabelledPage = Infinity;
    if (NP >= 8) {
      const front = allLines.filter((l) => l.page <= Math.max(12, Math.ceil(NP * 0.08)));
      const ft = (t) => t.toLowerCase().match(/^\p{L}{3,}/u)?.[0] ?? "";
      const cnt = /* @__PURE__ */ new Map();
      for (const l of front) {
        const f = ft(l.text);
        if (f) cnt.set(f, (cnt.get(f) ?? 0) + 1);
      }
      const top = [...cnt].sort((a, b) => b[1] - a[1])[0];
      if (top && top[1] >= 6) {
        tocLabel = top[0];
        const idx = allLines.map((l, i) => ({ l, i })).filter((x) => x.l.page <= Math.max(12, Math.ceil(NP * 0.08)) && ft(x.l.text) === tocLabel);
        const isEntryOf = new Set(idx.map((x) => x.i + 1));
        const pgLo = idx[0].l.page - 1, pgHi = idx[idx.length - 1].l.page + 1;
        for (const x of idx) {
          const e = allLines[x.i + 1];
          if (e && ft(e.text) !== tocLabel) labelled.add(fold(e.text));
        }
        allLines.forEach((l, i) => {
          if (l.page >= pgLo && l.page <= pgHi && ft(l.text) !== tocLabel && !isEntryOf.has(i)) unlabelled.add(fold(l.text));
        });
      }
    }
    const inSet = (set, f) => wl(f) >= 4 && [...set].some((x) => wl(x) >= 4 && (x.includes(f) || f.includes(x)));
    const kindOf = (pg) => {
      const m = markAt(pg);
      if (!m) return "story";
      const f = fold(m.title);
      if (L.sections.front.some((w) => f.includes(w))) return "front";
      if (L.sections.back.some((w) => f.includes(w))) return "back";
      if (tocLabel && !inSet(labelled, f) && inSet(unlabelled, f)) return pg < firstLabelledPage ? "front" : "back";
      return "story";
    };
    if (tocLabel) for (const st of starts) {
      const m = markAt(st);
      if (m && inSet(labelled, fold(m.title))) {
        firstLabelledPage = Math.min(firstLabelledPage, st);
      }
    }
    if ((L.sections.front.length || tocLabel) && chapterSource !== "windows" && chapterSource !== "none") {
      {
        const lim = bodyFrom + Math.max(6, Math.round((bodyTo - bodyFrom + 1) * 0.12));
        let lastF = -1;
        starts.forEach((st, i) => {
          if (st <= lim && kindOf(st) === "front") lastF = i;
        });
        for (let i = 0; i < lastF && starts.length > 1; i++) {
          frontSections.push({ title: markAt(starts[0])?.title ?? "Front matter", pages: [starts[0], starts[1] - 1] });
          starts.shift();
        }
      }
      while (starts.length > 1 && (!markAt(starts[0]) || kindOf(starts[0]) === "front")) {
        frontSections.push({ title: markAt(starts[0])?.title ?? "Front matter", pages: [starts[0], starts[1] - 1] });
        starts.shift();
      }
      while (starts.length > 1 && kindOf(starts[starts.length - 1]) === "back") {
        const st = starts.pop();
        backSections.unshift({ title: markAt(st)?.title ?? "", pages: [st, bodyTo] });
        bodyTo = st - 1;
      }
      if (frontSections.length || backSections.length) {
        bodyFrom = starts[0];
        body = [bodyFrom, bodyTo];
      }
    }
  }
  if (body) {
    const norm2 = (t) => t.toLowerCase().replace(/[^\p{L}]/gu, "");
    const known = new Set([...frontSections, ...backSections].map((x) => norm2(x.title)));
    const after = headings.filter((h) => !h.numbered && h.page > body[1] && !known.has(norm2(h.text))).filter((h, i, a) => a.findIndex((x) => norm2(x.text) === norm2(h.text)) === i).slice(0, 12);
    after.forEach((h, i) => backSections.push({ title: h.text, pages: [h.page, i + 1 < after.length ? after[i + 1].page - 1 : NP] }));
  }
  const chapterOfPage = (pg) => {
    let c = 0;
    for (let i = 0; i < starts.length; i++) if (pg >= starts[i]) c = i;
    return c;
  };
  const titleTok = new Uint8Array(toks.length);
  {
    const norm2 = (t) => t.toLowerCase().replace(/[^\p{L}]/gu, "");
    const titles = chapterMarks.map((m) => ({ page: m.page, key: norm2(m.title) })).filter((t) => t.key.length > 0 && t.key !== "chapter");
    if (titles.length) {
      let s0 = 0;
      for (let k = 0; k < toks.length; k++) {
        const endOfLine = k === toks.length - 1 || /[¶\f]/.test(raw.slice(toks[k].end, toks[k + 1].idx));
        if (!endOfLine) continue;
        const key2 = norm2(raw.slice(toks[s0].idx, toks[k].end)), pg = realPages ? toks[s0].pdf : Math.floor(s0 / PAGE) + 1;
        if (key2 && titles.some((t) => t.key === key2 && Math.abs(t.page - pg) <= 1)) for (let j = s0; j <= k; j++) titleTok[j] = 1;
        s0 = k + 1;
      }
    }
  }
  const structure = {
    frontSections,
    backSections,
    chapterSource,
    body,
    proseShare: proseShare.map((v) => Math.round(v * 100) / 100),
    frontMatter: body ? Array.from({ length: body[0] - 1 }, (_, i) => i + 1) : [],
    backMatter: body ? Array.from({ length: NP - body[1] }, (_, i) => body[1] + 1 + i) : [],
    headings: headings.slice(0, 60)
  };
  lap("3 calendar events month  number/year and the yea");
  const monthSet = new Set(L.months);
  if (lang === "en") for (const m of L.months) monthSet.add(m.slice(0, 3));
  const monthEvents = [];
  const yearFirstPage = {};
  const isYear = (w) => /^(1[5-9]|20)\d\d$/.test(w);
  const isDay = (w) => /^\d{1,2}$/.test(w) && +w >= 1 && +w <= 31;
  for (let k = 0; k < toks.length; k++) {
    const w = toks[k].w;
    if (isYear(w)) {
      const y = +w;
      if (yearFirstPage[y] === void 0) yearFirstPage[y] = page(k);
    }
    const m = w.toLowerCase();
    if (!monthSet.has(m)) continue;
    const p1 = toks[k - 1]?.w, p2 = toks[k - 2]?.w, n1 = toks[k + 1]?.w, n2 = toks[k + 2]?.w;
    const day = p1 && isDay(p1) ? +p1 : p1 && L.joiners.has(p1.toLowerCase()) && p2 && isDay(p2) ? +p2 : n1 && isDay(n1) ? +n1 : null;
    const year = n1 && isYear(n1) ? +n1 : n1 && L.joiners.has(n1.toLowerCase()) && n2 && isYear(n2) ? +n2 : n2 && isDay(n1 ?? "") && isYear(n2) ? +n2 : null;
    if (day || year) monthEvents.push({ month: m, day, year, page: page(k) });
  }
  lap("4 nodes  capital runs");
  const midCap = /* @__PURE__ */ new Map();
  toks.forEach((t, k) => {
    if (isCap(t.w) && !sentStart(k) && !t.par) midCap.set(t.w, (midCap.get(t.w) ?? 0) + 1);
  });
  const capTok = /* @__PURE__ */ new Map(), lowTok = /* @__PURE__ */ new Map();
  for (let k = 0; k < toks.length; k++) {
    if (titleTok[k] || !inBody(k)) continue;
    const w = toks[k].w;
    if (isCap(w)) capTok.set(w, (capTok.get(w) ?? 0) + 1);
    else lowTok.set(w.toLowerCase(), (lowTok.get(w.toLowerCase()) ?? 0) + 1);
  }
  const consistency = (name) => {
    if (name.includes(" ")) return 1;
    const cap = capTok.get(name) ?? 0, low = lowTok.get(name.toLowerCase()) ?? 0;
    return cap + low ? cap / (cap + low) : 1;
  };
  const named = /* @__PURE__ */ new Map();
  for (let k = 0; k < toks.length; k++) {
    const w = toks[k].w;
    if (titleTok[k] || !inBody(k) || !isCap(w) || toks[k].slug || sentStart(k) && !isAllCaps(w) && consistency(w) < 0.5 && (capTok.get(w) ?? 0) + (lowTok.get(w.toLowerCase()) ?? 0) >= 6 || stopSet.has(w.toLowerCase()) || monthSet.has(w.toLowerCase())) continue;
    const caps = isAllCaps(w);
    if (caps) {
      if (!alone(k) && !((midCap.get(w) ?? 0) >= 2)) continue;
      if (!alone(k) && (lowTok.get(w.toLowerCase()) ?? 0) >= 2) continue;
    } else if (!caseless && sentStart(k) && !((midCap.get(w) ?? 0) >= 3) && !abbrTok[k]) continue;
    let j = k;
    const run = [w];
    while (j + 1 < toks.length) {
      const n = toks[j + 1].w;
      if (!caps && !caseless && glue(j, j + 1) && isCap(n) && !stopSet.has(n.toLowerCase()) && !monthSet.has(n.toLowerCase())) {
        run.push(n);
        j++;
      } else if (!caps && !caseless && glue(j, j + 1) && L.joiners.has(n.toLowerCase()) && j + 2 < toks.length && isCap(toks[j + 2].w)) {
        run.push(n, toks[j + 2].w);
        j += 2;
      } else break;
    }
    let name = run.join(" ");
    {
      const parts = [];
      for (let q2 = k; q2 <= j; q2++) parts.push(toks[q2].w + (abbrTok[q2] === 1 ? "." : ""));
      name = parts.join(" ");
    }
    if (run.length === 1 && abbrTok[k] === 1) continue;
    (named.get(name) ?? named.set(name, []).get(name)).push({ pg: page(k), k });
    k = j;
  }
  const notNames = [];
  for (const name of [...named.keys()]) {
    if (name.includes(" ") || isAllCaps(name)) continue;
    const cap = capTok.get(name) ?? 0, low = lowTok.get(name.toLowerCase()) ?? 0;
    if (cap + low >= 6 && cap / (cap + low) < 0.5) {
      named.delete(name);
      notNames.push(name);
    }
  }
  const byWord = /* @__PURE__ */ new Map();
  for (const n of named.keys()) if (n.includes(" ")) for (const p of new Set(n.split(" "))) (byWord.get(p) ?? byWord.set(p, []).get(p)).push(n);
  const fusions = [];
  const aliasesOf = /* @__PURE__ */ new Map();
  if (caseless) {
    const ns = [...named.keys()].filter((n) => !n.includes(" ") && !CJK_LIKE.test(n)), pre = /* @__PURE__ */ new Map(), pairs = [];
    for (const t of ns) for (const u of ns) {
      const d = t.length - u.length;
      if (t !== u && d >= 1 && d <= 2 && u.length >= 3 && t.endsWith(u)) {
        const p = t.slice(0, d);
        (pre.get(p) ?? pre.set(p, /* @__PURE__ */ new Set()).get(p)).add(u);
        pairs.push([t, u, p]);
      }
    }
    for (const [t, u, p] of pairs) if ((pre.get(p)?.size ?? 0) >= 2 && named.has(t) && named.has(u) && named.get(t).length <= named.get(u).length * 1.5) {
      named.get(u).push(...named.get(t));
      named.delete(t);
      aliasesOf.set(u, [...aliasesOf.get(u) ?? [], t]);
    }
  }
  for (const s of [...named.keys(), ...named.keys()]) {
    if (s.includes(" ") || !named.has(s)) continue;
    const multi = byWord.get(s);
    if (!multi) continue;
    const tot = multi.reduce((a, n) => a + named.get(n).length, 0);
    if (tot < 3) continue;
    multi.sort((a, b) => named.get(b).length - named.get(a).length);
    const best2 = multi[0];
    const second = multi[1] ? named.get(multi[1]).length : 0;
    if (named.get(best2).length / tot >= 0.7 || named.get(best2).length >= 3 * second && named.get(best2).length >= 5) {
      named.get(best2).push(...named.get(s));
      named.delete(s);
      (aliasesOf.get(best2) ?? aliasesOf.set(best2, []).get(best2)).push(s);
      fusions.push(`${s} \u2192 ${best2}`);
    }
  }
  lap("5 catalogue EVERY word weight  rarity at page le");
  const occL = /* @__PURE__ */ new Map(), pgset = /* @__PURE__ */ new Map();
  toks.forEach((t, k) => {
    const w = t.w.toLowerCase();
    if (titleTok[k] || !inBody(k) || wl(w) < 3 || stopSet.has(w) || /\d/.test(w)) return;
    (occL.get(w) ?? occL.set(w, []).get(w)).push({ pg: page(k), k });
    (pgset.get(w) ?? pgset.set(w, /* @__PURE__ */ new Set()).get(w)).add(page(k));
  });
  const wt = (c, p) => c * Math.log(1 + NP / p);
  const idf = (w) => NP < 8 ? Math.log((toks.length + 1) / (1 + (occL.get(w)?.length ?? 0))) : Math.log((NP + 1) / (1 + (pgset.get(w)?.size ?? 0)));
  lap("5b every sentence is a solar system");
  const idfs = [...pgset.keys()].map(idf).sort((a, b) => a - b);
  const highIdf = idfs.length ? idfs[Math.floor(idfs.length * 0.75)] : 0;
  const sentRows = [];
  const sentOf = new Int32Array(toks.length).fill(-1);
  {
    let s0 = 0;
    for (let k = 0; k < toks.length; k++) {
      const last = k === toks.length - 1;
      const gapTxt = last ? "." : raw.slice(toks[k].end, toks[k + 1].idx);
      const abbr = abbrTok[k] === 1;
      if (!last && !(/[.!?…。！？｡؟۔।॥]/.test(gapTxt) && !abbr)) continue;
      if (inBody(s0) && !titleTok[s0]) {
        let words = 0;
        const ex = [];
        const seenEx = /* @__PURE__ */ new Set();
        let max = 0;
        for (let j = s0; j <= k; j++) {
          const w = toks[j].w.toLowerCase();
          if (wl(w) < 3 || stopSet.has(w) || /\d/.test(w)) continue;
          words++;
          const v = idf(w);
          if (v >= highIdf) {
            ex.push({ w, k: j });
            if (!seenEx.has(w)) {
              seenEx.add(w);
              max += v;
            }
          }
        }
        if (words >= 2) {
          let gap = null;
          if (ex.length >= 2) {
            let g = 0;
            for (let i = 1; i < ex.length; i++) g += ex[i].k - ex[i - 1].k;
            gap = Math.round(g / (ex.length - 1) * 10) / 10;
          }
          sentRows.push({ s: s0, e: k, words, max, ex: [...new Set(ex.map((x) => x.w))].slice(0, 5), gap });
          for (let j = s0; j <= k; j++) sentOf[j] = sentRows.length - 1;
        }
      }
      s0 = k + 1;
    }
  }
  lap("5c the vocabulary laid out in space");
  const seqs = sentRows.map((r) => {
    const out = [];
    for (let j = r.s; j <= r.e; j++) {
      const w = toks[j].w.toLowerCase();
      if (wl(w) >= 3 && !stopSet.has(w) && !/\d/.test(w)) out.push(w);
    }
    return out;
  });
  const emb = buildEmbedding(seqs);
  const axis = (seedOf) => {
    const seeds = [...emb.vec.keys()].filter((w) => seedOf(w) > 0);
    const c = emb.centroid(seeds);
    if (!c || seeds.length < 3) return null;
    const raw2 = /* @__PURE__ */ new Map();
    let m = 0;
    for (const w of emb.vec.keys()) {
      const v = emb.simToVec(w, c);
      raw2.set(w, v);
      m += v;
    }
    m /= raw2.size;
    let sd2 = 0;
    for (const v of raw2.values()) sd2 += (v - m) ** 2;
    sd2 = Math.sqrt(sd2 / raw2.size) || 1;
    return (w) => ((raw2.get(w) ?? m) - m) / sd2;
  };
  const charge = /* @__PURE__ */ new Map();
  for (const w of emb.vec.keys()) charge.set(w, wordCharge(w));
  const posAxis = axis((w) => (charge.get(w)?.valence ?? 0) > 0 ? 1 : 0), negAxis = axis((w) => (charge.get(w)?.valence ?? 0) < 0 ? 1 : 0), aroAxis = axis((w) => charge.get(w)?.arousal ?? 0);
  const extV = /* @__PURE__ */ new Map(), extA = /* @__PURE__ */ new Map();
  for (const [w, c] of charge) {
    const lean = posAxis && negAxis ? (posAxis(w) - negAxis(w)) / 2 : 0;
    if (c.valence) extV.set(w, c.valence > 0 && lean <= -1 || c.valence < 0 && lean >= 1 ? 0 : c.valence);
    else if (lean >= 1) extV.set(w, 0.5);
    else if (lean <= -1) extV.set(w, -0.5);
    if (c.arousal) extA.set(w, 1);
    else if (aroAxis && aroAxis(w) >= 1.5) extA.set(w, 0.5);
  }
  const { fields: semFields, fieldOf } = clusterVocabulary(emb, Math.max(8, Math.min(24, Math.round(emb.vec.size / 90))));
  const fieldValence = semFields.map((f) => {
    let p = 0, n = 0;
    for (const w of f.members) {
      const v = extV.get(w) ?? 0;
      if (v > 0) p += v;
      else if (v < 0) n -= v;
    }
    return p + n >= 3 ? (p - n) / (p + n) : 0;
  });
  const sentSorted = sentRows.map((r) => r.max).filter((v) => v > 0).sort((a, b) => a - b);
  const q = (f) => sentSorted.length ? sentSorted[Math.min(sentSorted.length - 1, Math.floor(sentSorted.length * f))] : 0;
  const cuts = [q(0.25), q(0.5), q(0.75)];
  const classes = [0, 0, 0, 0, 0];
  const pageSum = new Array(NP).fill(0), pageCnt = new Array(NP).fill(0);
  for (const r of sentRows) {
    classes[r.max <= 0 ? 0 : 1 + cuts.filter((c) => r.max > c).length]++;
    const p = page(r.s) - 1;
    pageSum[p] += r.max;
    pageCnt[p]++;
  }
  const sentences = {
    total: sentRows.length,
    classes,
    perPage: pageSum.map((v, i) => pageCnt[i] ? Math.round(v / pageCnt[i] * 100) / 100 : 0),
    top: [...sentRows].sort((a, b) => b.max + b.ex.length * 0.01 - (a.max + a.ex.length * 0.01)).slice(0, 12).map((r) => ({
      page: page(r.s),
      text: raw.slice(toks[r.s].idx, toks[r.e].end).replace(/[¶\f]/g, " ").replace(/\s+/g, " ").slice(0, 170),
      words: r.words,
      exotic: r.ex,
      score: Math.round(r.max * 100) / 100,
      gap: r.gap,
      scales: null
    }))
  };
  const core80 = (occ) => {
    const s = occ.map((o) => o.pg).sort((a, b) => a - b);
    const need = Math.max(1, Math.ceil(s.length * 0.8));
    let bi = 0, bw = Infinity;
    for (let a = 0; a + need - 1 < s.length; a++) {
      const w = s[a + need - 1] - s[a];
      if (w < bw) {
        bw = w;
        bi = a;
      }
    }
    return [s[bi], s[bi + need - 1]];
  };
  const density = (occ) => {
    const bins = Math.min(NP, BINS_MAX) || 1, b = new Array(bins).fill(0);
    for (const o of occ) b[Math.min(bins - 1, Math.floor((o.pg - 1) / NP * bins))]++;
    return b;
  };
  const bagOf = (e) => {
    const own = new Set(e.name.toLowerCase().split(/[ =]+/));
    const bag = /* @__PURE__ */ new Map();
    for (const o of e.occ) for (let d = -WINDOW; d <= WINDOW; d++) {
      const t = toks[o.k + d];
      if (!t || d === 0 || titleTok[o.k + d] || sentOf[o.k] >= 0 && sentOf[o.k + d] !== sentOf[o.k]) continue;
      const w = t.w.toLowerCase();
      if (own.has(w) || stopSet.has(w) || wl(w) < 3) continue;
      bag.set(w, (bag.get(w) ?? 0) + 1);
    }
    return bag;
  };
  const MIN_N = Math.max(1, Math.ceil(NP / 80));
  const MIN_LEX = Math.max(2, Math.round(NP / 25));
  const shortLine = new Uint8Array(toks.length);
  {
    let s0 = 0;
    for (let k = 0; k < toks.length; k++) {
      if (k === toks.length - 1 || /[¶\f]/.test(raw.slice(toks[k].end, toks[k + 1].idx))) {
        if (k - s0 + 1 <= 8) for (let j = s0; j <= k; j++) shortLine[j] = 1;
        s0 = k + 1;
      }
    }
  }
  const structuralWords = [];
  const ents = [...named].map(([name, occ]) => ({ name, aliases: aliasesOf.get(name) ?? [], occ, lex: false })).filter((e) => e.occ.length >= MIN_N).filter((e) => {
    if (e.occ.length < 3) return true;
    const inShort = e.occ.filter((o) => shortLine[o.k]).length / e.occ.length, speaks = e.occ.filter((o) => tmode[o.k] === 1).length / e.occ.length;
    if (inShort >= 0.7 && speaks < 0.2) {
      structuralWords.push(e.name);
      return false;
    }
    return true;
  });
  lap("6 what each node IS");
  const storyStart = slugs.length ? slugs[0].a : 0;
  const lastK = toks.length - 6;
  for (const e of ents) {
    e.bag = bagOf(e);
    let ch = 0, pl = 0;
    for (const [w, c] of e.bag) {
      if (L.personCues.has(w) || L.speech.has(w)) ch += c;
      if (L.placeCues.has(w)) pl += c;
    }
    pl += e.occ.filter((o) => L.placePreps.has(lw(o.k - 1))).length * 1.5;
    for (const o of e.occ) if (isAllCaps(toks[o.k].w) && alone(o.k)) ch += 4;
    for (const o of e.occ) {
      const m = tmode[o.k];
      if (m === 1) ch += 0.25;
      else if (m === 2) ch += 1.5;
    }
    e.ch = ch / e.occ.length;
    e.pl = pl / e.occ.length;
    e.kind = ch >= pl ? "character" : "place";
    if (e.occ.length <= 3 && e.occ.every((o) => o.k >= lastK)) e.kind = "end-mark";
    else if (slugs.length && e.occ.every((o) => toks[o.k].idx < storyStart)) e.kind = "paratext";
  }
  lap("7 paratext lists");
  const blocks = [];
  {
    let cur = [];
    for (const l of pdfPages.join("\n").split("\n").map((x) => x.trim())) {
      if (/^\p{Lu}[\p{L}]+$/u.test(l)) cur.push(l);
      else if (l === "") continue;
      else {
        if (cur.length >= 3) blocks.push(cur);
        cur = [];
      }
    }
    if (cur.length >= 3) blocks.push(cur);
  }
  const countWord = (w) => {
    let n = 0;
    for (const t of toks) if (t.w === w) n++;
    return n;
  };
  const paratext = blocks.map((items) => ({ items, appearancesInWork: Object.fromEntries(items.map((w) => [w, countWord(w)])) }));
  const inList = new Set(blocks.flat());
  for (const e of ents) if (inList.has(e.name) && e.occ.length <= 2 && e.kind !== "end-mark") e.kind = "paratext";
  const lexEnts = [...occL].filter(([w, o]) => o.length >= MIN_LEX && !L.verbish.test(w) && !named.has(w[0].toUpperCase() + w.slice(1))).map(([w, o]) => ({ name: w, aliases: [], occ: o, lex: true }));
  const wCache = /* @__PURE__ */ new Map();
  const weightOf = (e) => {
    let v = wCache.get(e);
    if (v === void 0) {
      v = wt(e.occ.length, pgset.get(e.name)?.size ?? new Set(e.occ.map((o) => o.pg)).size);
      wCache.set(e, v);
    }
    return v;
  };
  lexEnts.sort((a, b) => weightOf(b) - weightOf(a));
  const lexRank = new Map(lexEnts.map((e, i) => [e, i]));
  const chars = ents.filter((e) => e.kind === "character");
  const roleSet = new Set(L.roleWords);
  const roleEnts = lexEnts.filter((e) => roleSet.has(e.name) || L.entityWords.has(e.name) && (lexRank.get(e) ?? 99) < 60);
  const cand = [...chars, ...roleEnts.filter((e) => !L.address.has(e.name) || roleSet.has(e.name))];
  cand.forEach((c) => {
    c.bag = c.bag ?? bagOf(c);
  });
  lap("9 identity");
  const slices = Math.max(1, NP / BINS_MAX);
  const pgSlices = (e) => new Set(e.occ.map((o) => Math.floor((o.pg - 1) / slices)));
  const jac = (a, b) => {
    const A = pgSlices(a), B = pgSlices(b);
    let i = 0;
    for (const x of A) if (B.has(x)) i++;
    return i / (A.size + B.size - i || 1);
  };
  const pageSetCache = /* @__PURE__ */ new Map();
  const pageSet = (e) => {
    let v = pageSetCache.get(e);
    if (!v) {
      v = new Set(e.occ.map((o) => o.pg));
      pageSetCache.set(e, v);
    }
    return v;
  };
  const nC = cand.length, cosM = Array.from({ length: nC }, () => new Array(nC).fill(0));
  for (let i = 0; i < nC; i++) for (let j = i + 1; j < nC; j++) {
    const c = cosine(cand[i].bag, cand[j].bag);
    cosM[i][j] = c;
    cosM[j][i] = c;
  }
  const stats = cosM.map((row, i) => {
    const v = row.filter((_, j) => j !== i);
    const mean2 = v.reduce((a, b) => a + b, 0) / (v.length || 1), sd2 = Math.sqrt(v.reduce((a, b) => a + (b - mean2) ** 2, 0) / (v.length || 1));
    return { mean: mean2, sd: sd2 };
  });
  const zOf = (i, j) => stats[i].sd > 0 ? (cosM[i][j] - stats[i].mean) / stats[i].sd : 0;
  const rankIn = (i, j) => cosM[i].filter((c, q2) => q2 !== i && c > cosM[i][j]).length;
  const best = cand.map((_, i) => {
    let bj = -1, bs = 0;
    cosM[i].forEach((c, j) => {
      if (j !== i && c > bs) {
        bs = c;
        bj = j;
      }
    });
    return { j: bj, s: bs, z: bj >= 0 ? zOf(i, bj) : 0 };
  });
  const injRefused = [];
  const keptApart = [];
  cand.forEach((a, i) => {
    const j = best[i].j;
    if (j > i && !a.lex && !cand[j].lex && best[i].s >= 0.4 && best[j].j === i) {
      const A = pageSet(a), B = pageSet(cand[j]);
      let sh = 0;
      for (const x of A) if (B.has(x)) sh++;
      keptApart.push({ a: a.name, b: cand[j].name, similarity: round2(best[i].s), sharedPages: sh });
    }
  });
  const near = (i, j) => rankIn(i, j) === 0 && zOf(i, j) >= 2 && rankIn(j, i) <= 2 && zOf(j, i) >= 1.5;
  const sentSet = /* @__PURE__ */ new Map();
  const sentsOf = (e) => {
    let v = sentSet.get(e);
    if (!v) {
      v = new Set(e.occ.map((o) => sentOf[o.k]).filter((x) => x >= 0));
      sentSet.set(e, v);
    }
    return v;
  };
  const lexIdx = cand.map((c, i) => c.lex ? i : -1).filter((i) => i >= 0);
  const rankLex = (i, j) => lexIdx.filter((q2) => q2 !== i && q2 !== j && cosM[i][q2] > cosM[i][j]).length;
  const within = (a, b) => {
    const A = pgSlices(a), B = pgSlices(b);
    const [small, big] = A.size <= B.size ? [A, B] : [B, A];
    let n = 0;
    for (const x of small) if (big.has(x)) n++;
    return n / (small.size || 1);
  };
  const synonym = (i, j) => {
    if (!cand[i].lex || !cand[j].lex || cosM[i][j] < 0.2 || within(cand[i], cand[j]) < 0.8 || !(rankLex(i, j) === 0 || rankLex(j, i) === 0)) return false;
    const A = sentsOf(cand[i]), B = sentsOf(cand[j]);
    let co2 = 0;
    for (const x of A) if (B.has(x)) co2++;
    return co2 / Math.max(1, Math.min(A.size, B.size)) <= 0.1;
  };
  const mutual = (i, j) => cosM[i][j] >= 0.2 && (near(i, j) || near(j, i)) && jac(cand[i], cand[j]) >= 0.6 && (cand[i].lex || cand[j].lex) || synonym(i, j);
  const idClasses = equivalenceClasses(cand.map((_, i) => i), mutual);
  const dead = /* @__PURE__ */ new Set();
  const classReasons = /* @__PURE__ */ new Map();
  for (const cls of idClasses) {
    if (cls.length < 2) continue;
    const members = cls.map((i) => cand[i]).sort((x, y) => y.occ.length - x.occ.length), keep = members[0];
    for (const drop of members.slice(1)) {
      keep.occ = [...keep.occ, ...drop.occ];
      mergeBag(keep.bag, drop.bag);
      keep.aliases = [...keep.aliases, drop.name, ...drop.aliases];
      fusions.push(`${drop.name} \u2192 ${keep.name} (closest solar systems, shared pages)`);
      (classReasons.get(keep.name) ?? classReasons.set(keep.name, []).get(keep.name)).push(`${drop.name}: closest solar system on the same pages`);
      dead.add(cand.indexOf(drop));
    }
  }
  let live = cand.filter((_, i) => !dead.has(i));
  const glued = /* @__PURE__ */ new Map();
  for (const e of ents) for (const o of e.occ) {
    if (o.k === 0) continue;
    const prev = toks[o.k - 1], p = prev.w.toLowerCase();
    if (isCap(prev.w) || stopSet.has(p) || wl(p) < 3 || /\d/.test(p) || L.determiners.has(p) || !glue(o.k - 1, o.k)) continue;
    const m = glued.get(p) ?? glued.set(p, /* @__PURE__ */ new Map()).get(p);
    m.set(e.name, (m.get(e.name) ?? 0) + 1);
  }
  for (const [word, names] of glued) {
    if (names.size !== 1) continue;
    const [[nm, cnt]] = [...names];
    const uses = occL.get(word)?.length ?? cnt, known = L.titles.has(word);
    if (!known && !(cnt >= 3 && cnt / uses >= 0.5)) continue;
    const N = live.find((c) => c.name === nm);
    if (!N) continue;
    let T = live.find((c) => c.name === word || c.aliases.includes(word));
    if (!T) {
      const oc = occL.get(word);
      if (!oc || oc.length < cnt) continue;
      T = { name: word, aliases: [], occ: oc.map((o) => ({ ...o })), lex: true };
      T.bag = bagOf(T);
    }
    if (T === N) continue;
    if (!T.lex) {
      injRefused.push(`${word} \u2261 ${nm} refused: \xAB${word}\xBB already belongs to ${T.name}`);
      continue;
    }
    if (!known && cosine(T.bag, N.bag) < 0.3) continue;
    N.occ = [...N.occ, ...T.occ];
    mergeBag(N.bag, T.bag);
    N.aliases = [...N.aliases, T.name, ...T.aliases];
    fusions.push(`${word} \u2261 ${nm} (the only name ever glued to \xAB${word}\xBB, ${cnt}\xD7)`);
    classReasons.set(N.name, [...classReasons.get(N.name) ?? [], ...classReasons.get(T.name) ?? []]);
    live = live.filter((c) => c !== T);
  }
  wCache.clear();
  const equivalence = [];
  for (const e of live) {
    const members = [.../* @__PURE__ */ new Set([e.name, ...e.aliases])];
    if (members.length < 2) continue;
    const reasons = [];
    for (const m of members.slice(1)) {
      if (e.name.split(" ").includes(m) || e.name.includes(m)) reasons.push(`${m}: contained in the longer name`);
      else if (fusions.some((f) => f.startsWith(`${m} \u2261`))) reasons.push(`${m}: the only name ever glued to that title`);
      else reasons.push(...(classReasons.get(e.name) ?? []).filter((r) => r.startsWith(m + ":")));
    }
    equivalence.push({ representative: e.name, members, reasons: [...new Set(reasons)] });
  }
  lap("10 scene links");
  const links = [];
  for (let i = 0; i < live.length; i++) for (let j = i + 1; j < live.length; j++) {
    const A = pageSet(live[i]), B = pageSet(live[j]);
    let sh = 0;
    for (const x of A) if (B.has(x)) sh++;
    const strength = sh / (A.size + B.size - sh || 1) * cosine(live[i].bag, live[j].bag);
    if (strength >= 0.04 && sh >= 2 && Math.min(live[i].occ.length, live[j].occ.length) >= 3) links.push({ a: live[i].name, b: live[j].name, strength: Math.round(strength * 100) / 100, sharedPages: sh });
  }
  links.sort((a, b) => b.strength - a.strength);
  lap("11 places and who acts in them");
  const placeEnts = ents.filter((e) => e.kind === "place" && e.occ.length >= 3);
  const ksCache = /* @__PURE__ */ new Map();
  const sortedKs = (e) => {
    let v = ksCache.get(e);
    if (!v) {
      v = e.occ.map((o) => o.k).sort((a, b) => a - b);
      ksCache.set(e, v);
    }
    return v;
  };
  const hasNear = (ks, k, d) => {
    let lo = 0, hi = ks.length;
    while (lo < hi) {
      const m = lo + hi >> 1;
      if (ks[m] < k - d) lo = m + 1;
      else hi = m;
    }
    return lo < ks.length && ks[lo] <= k + d;
  };
  const places = placeEnts.map((p) => {
    const c = /* @__PURE__ */ new Map();
    for (const o of p.occ) for (const r of live) {
      if (r.lex || r.kind === "place") continue;
      if (hasNear(sortedKs(r), o.k, 30)) c.set(r.name, (c.get(r.name) ?? 0) + 1);
    }
    return { name: p.name, core: core80(p.occ), inhabitants: [...c].sort((a, b) => b[1] - a[1]).slice(0, 5).map(([name, scenes]) => ({ name, scenes })) };
  });
  const orbit = (e) => [...e.bag ?? bagOf(e)].map(([w, c]) => [w, c * idf(w)]).sort((a, b) => b[1] - a[1]).slice(0, 8).map((x) => x[0]);
  lap("11b");
  const treeSet = [...live.filter((e) => !e.lex || e.aliases.length > 0 || roleSet.has(e.name)), ...placeEnts.filter((p) => !live.includes(p))].filter((e) => e.kind !== "paratext" && e.kind !== "end-mark" && e.occ.length >= 3);
  const firstPage = (e) => Math.min(...e.occ.map((o) => o.pg));
  const importance = (e) => e.occ.length * Math.log(1 + NP / new Set(e.occ.map((o) => o.pg)).size);
  const ranked = [...treeSet].sort((a, b) => importance(b) - importance(a));
  const topI = ranked.length ? importance(ranked[0]) : 0;
  const winP = Math.max(1, Math.round(NP * 0.03));
  const major = ranked.filter((e) => importance(e) >= topI * 0.12).slice(0, 8);
  const bursty = ranked.filter((e) => !major.includes(e) && e.occ.length >= 8 && (() => {
    const c = core80(e.occ);
    return c[1] - c[0] + 1 <= Math.max(3, NP * 0.12);
  })()).slice(0, 8);
  const rootEnts = [...major, ...bursty];
  const forest = rootEnts.map((R) => {
    const rp = pageSet(R), rc = core80(R.occ), rf = firstPage(R);
    const branches = treeSet.filter((x) => x !== R).map((X) => {
      const xp = pageSet(X);
      let sh = 0;
      for (const g of xp) if (rp.has(g)) sh++;
      const inside = sh / xp.size, fx = firstPage(X);
      const born = fx >= rf && fx <= rc[1] + winP && rp.has(fx) || fx >= rf && fx <= rc[1] + winP && [...rp].some((g) => Math.abs(g - fx) <= winP);
      return { X, sh, inside, born, fx, strength: (inside + (born ? 0.5 : 0)) * Math.log(1 + X.occ.length) };
    }).filter((b) => b.sh >= 2 && (b.inside >= 0.4 || b.born)).sort((a, b) => b.strength - a.strength).slice(0, 10);
    return {
      root: R.name,
      kind: R.kind ?? "character",
      mentions: R.occ.length,
      first: rf,
      last: Math.max(...R.occ.map((o) => o.pg)),
      core: rc,
      orbit: orbit(R).slice(0, 6),
      rank: "secondary",
      generates: [],
      branches: branches.map((b) => ({ name: b.X.name, kind: b.X.kind ?? "character", first: b.fx, inside: Math.round(b.inside * 100) / 100, born: b.born }))
    };
  });
  const rootNames = new Set(forest.map((f) => f.root));
  for (const f of forest) {
    const ent = rootEnts.find((e) => e.name === f.root);
    f.rank = importance(ent) >= topI * 0.35 ? "primary" : "secondary";
    f.generates = f.branches.filter((b) => b.born && rootNames.has(b.name)).map((b) => b.name);
  }
  const treeRelations = [];
  for (let i = 0; i < forest.length; i++) for (let j = i + 1; j < forest.length; j++) {
    const A = forest[i], B = forest[j];
    const sb = A.branches.map((b) => b.name).filter((n) => B.branches.some((x) => x.name === n));
    const ov = Math.max(0, Math.min(A.core[1], B.core[1]) - Math.max(A.core[0], B.core[0]) + 1);
    const shorter = Math.min(A.core[1] - A.core[0] + 1, B.core[1] - B.core[0] + 1);
    const relation = ov / shorter < 0.15 ? A.core[1] <= B.core[0] ? "a hands over to b" : "b hands over to a" : A.core[0] <= B.core[0] && A.core[1] >= B.core[1] || B.core[0] <= A.core[0] && B.core[1] >= A.core[1] ? "nested" : "run together";
    treeRelations.push({ a: A.root, b: B.root, sharedBranches: sb, coreOverlap: ov, relation });
  }
  treeRelations.sort((x, y) => y.sharedBranches.length - x.sharedBranches.length || y.coreOverlap - x.coreOverlap);
  lap("11c");
  const strands = [...treeSet].sort((a, b) => b.occ.length - a.occ.length).slice(0, 12);
  const SL = Math.min(NP, BINS_MAX) || 1;
  const curve = strands.map((e) => density(e.occ));
  const pairCross = /* @__PURE__ */ new Map();
  const sliceCross = new Array(Math.max(0, SL - 1));
  for (let t = 0; t < SL - 1; t++) {
    const involved = /* @__PURE__ */ new Set();
    let c = 0;
    for (let i = 0; i < strands.length; i++) for (let j = i + 1; j < strands.length; j++) {
      const a0 = curve[i][t] - curve[j][t], a1 = curve[i][t + 1] - curve[j][t + 1];
      if (curve[i][t] && curve[j][t] && curve[i][t + 1] && curve[j][t + 1] && a0 * a1 < 0) {
        c++;
        involved.add(strands[i].name);
        involved.add(strands[j].name);
        const key2 = strands[i].name + "|" + strands[j].name;
        pairCross.set(key2, (pairCross.get(key2) ?? 0) + 1);
      }
    }
    sliceCross[t] = { n: involved, c };
  }
  const toPage = (slice) => Math.max(1, Math.round(slice * NP / SL) + 1);
  const wins = [];
  {
    const order = sliceCross.map((v, t) => ({ t, c: (sliceCross[t - 1]?.c ?? 0) + v.c + (sliceCross[t + 1]?.c ?? 0) })).sort((a, b) => b.c - a.c);
    const used = /* @__PURE__ */ new Set();
    for (const o of order) {
      if (o.c < 3 || wins.length >= 5) break;
      if ([-1, 0, 1].some((d) => used.has(o.t + d))) continue;
      used.add(o.t);
      used.add(o.t - 1);
      used.add(o.t + 1);
      const nodesIn = /* @__PURE__ */ new Set();
      for (const d of [-1, 0, 1]) sliceCross[o.t + d]?.n.forEach((n) => nodesIn.add(n));
      wins.push({ pages: [toPage(Math.max(0, o.t - 1)), toPage(Math.min(SL, o.t + 2))], crossings: o.c, nodes: [...nodesIn] });
    }
  }
  const norm = curve.map((c) => {
    const mx = Math.max(...c) || 1;
    return c.map((v) => v / mx);
  });
  const closest = [];
  for (let i = 0; i < strands.length; i++) for (let j = i + 1; j < strands.length; j++) {
    let d = 0;
    for (let t = 0; t < SL; t++) d += (norm[i][t] - norm[j][t]) ** 2;
    closest.push({ a: strands[i].name, b: strands[j].name, distance: Math.round(Math.sqrt(d / SL) * 100) / 100 });
  }
  closest.sort((a, b) => a.distance - b.distance);
  const knots = {
    windows: wins.sort((a, b) => a.pages[0] - b.pages[0]),
    pairs: [...pairCross].map(([k, c]) => {
      const [a, b] = k.split("|");
      return { a, b, crossings: c };
    }).sort((a, b) => b.crossings - a.crossings).slice(0, 8),
    closest: closest.slice(0, 6)
  };
  lap("12 forms of address");
  const dfc = /* @__PURE__ */ new Map();
  live.forEach((c) => {
    for (const w of c.bag.keys()) dfc.set(w, (dfc.get(w) ?? 0) + 1);
  });
  const address = [];
  const nameTokAt = /* @__PURE__ */ new Map();
  for (const e of ents) if (e.kind === "character") for (const o of e.occ) nameTokAt.set(o.k, e.name);
  const speakerOf = (k0) => {
    for (let d = 0; d <= 14; d++) for (const sg of d === 0 ? [1] : [1, -1]) {
      const j = k0 + sg * d;
      if (!toks[j] || !L.speech.has(toks[j].w.toLowerCase()) || sentOf[j] !== sentOf[k0]) continue;
      for (const q2 of [1, 2, 3, -1, -2, -3]) {
        const nm = nameTokAt.get(j + q2);
        if (nm) return nm;
      }
    }
    return null;
  };
  toks.forEach((t, k) => {
    const w = t.w.toLowerCase();
    if (!L.address.has(w)) return;
    if (!(L.addressPoss.has(lw(k - 1)) || isCap(t.w))) return;
    const speaker = speakerOf(k);
    const scene = /* @__PURE__ */ new Set();
    for (let d = -40; d <= 40; d++) {
      const u = toks[k + d];
      if (u && d) scene.add(u.w.toLowerCase());
    }
    const sc = live.filter((c) => c.name.toLowerCase() !== w && !c.aliases.some((a) => a.toLowerCase() === w) && !(speaker && (c.name === speaker || c.aliases.includes(speaker)))).map((c) => {
      const sz = Math.sqrt([...c.bag.values()].reduce((a, b) => a + b, 0)) || 1;
      let s = 0;
      const hits = [];
      for (const x of scene) {
        const tf = c.bag.get(x);
        if (!tf) continue;
        const dw = Math.log(1 + live.length / (dfc.get(x) ?? 1));
        s += Math.min(tf, 6) * dw / sz;
        if (tf >= 2 && dw > 0.9) hits.push(x);
      }
      const present = hasNear(sortedKs(c), k, 25);
      if (present) s *= 1.8;
      return { node: c.name, score: Math.round(s * 100) / 100, evidence: hits.slice(0, 3), present };
    }).sort((a, b) => b.score - a.score);
    address.push({ page: page(k), form: (L.addressPoss.has(lw(k - 1)) ? lw(k - 1) + " " : "") + t.w, speaker, to: sc.slice(0, 2) });
  });
  lap("13 assemble the public result");
  const voiceOf = (e) => {
    let d = 0, a = 0, n = 0;
    for (const o of e.occ) {
      const m = tmode[o.k];
      if (m === 1) d++;
      else if (m === 2) a++;
      else n++;
    }
    const t = e.occ.length || 1;
    const r = (x) => Math.round(x / t * 100) / 100;
    return { dialogue: r(d), action: r(a), narration: r(n) };
  };
  const publicNode = (e) => {
    const pages = new Set(e.occ.map((o) => o.pg));
    return {
      name: e.name,
      aliases: [...new Set(e.aliases)],
      kind: e.kind ?? "character",
      evidence: { character: Math.round((e.ch ?? 0) * 100) / 100, place: Math.round((e.pl ?? 0) * 100) / 100 },
      mentions: e.occ.length,
      pages: pages.size,
      first: Math.min(...pages),
      last: Math.max(...pages),
      nameConsistency: round2(consistency(e.name)),
      voice: voiceOf(e),
      core: core80(e.occ),
      density: density(e.occ),
      orbit: orbit(e)
    };
  };
  const bigRole = (e) => e.lex && (roleSet.has(e.name) || L.entityWords.has(e.name)) && !L.address.has(e.name) && e.occ.length >= Math.max(10, 3 * MIN_LEX) && new Set(e.occ.map((o) => o.pg)).size >= Math.max(4, NP * 0.05);
  const nodeList = [...ents, ...live.filter((e) => e.lex && (e.aliases.length > 0 || bigRole(e)))].map(publicNode);
  nodeList.sort((a, b) => b.mentions * Math.log(1 + NP / b.pages) - a.mentions * Math.log(1 + NP / a.pages));
  lap("chapters");
  const nCh = starts.length;
  const chapOf = (e) => new Set(e.occ.map((o) => chapterOfPage(o.pg)));
  const chWords = Array.from({ length: nCh }, () => /* @__PURE__ */ new Map()), chTokens = new Array(nCh).fill(0);
  const wordChapters = /* @__PURE__ */ new Map();
  toks.forEach((t, k) => {
    if (!inBody(k)) return;
    const c = chapterOfPage(page(k));
    chTokens[c]++;
    const w = t.w.toLowerCase();
    if (wl(w) < 4 || stopSet.has(w) || /\d/.test(w)) return;
    chWords[c].set(w, (chWords[c].get(w) ?? 0) + 1);
    (wordChapters.get(w) ?? wordChapters.set(w, /* @__PURE__ */ new Set()).get(w)).add(c);
  });
  const chapterRar = (w) => Math.log((nCh + 1) / (1 + (wordChapters.get(w)?.size ?? 0)));
  const classCache = /* @__PURE__ */ new Map();
  const classifyWord = (w) => {
    const hit = classCache.get(w);
    if (hit) return hit;
    const occ = occL.get(w) ?? [];
    let place = 0, tool = 0, noun = 0, pre = 0;
    for (const o of occ) {
      if (L.determiners.has(lw(o.k - 1)) || L.determiners.has(lw(o.k - 2))) noun++;
      if (L.preVerb.has(lw(o.k - 1)) || isCap(toks[o.k - 1]?.w ?? "")) pre++;
      for (const d of [1, 2, 3]) {
        const pw = lw(o.k - d);
        if (L.placePreps.has(pw)) {
          place++;
          break;
        }
        if (L.toolPreps.has(pw)) {
          tool++;
          break;
        }
      }
    }
    const n = occ.length || 1, nounShare = noun / n, hasDet = L.determiners.size > 0;
    const isAction = L.verbish.test(w) && w.length >= 6 && (!hasDet || nounShare < 0.2 && pre / n >= 0.2);
    const cls = isAction ? "action" : place / n >= 0.25 || L.placeCues.has(w) ? "place" : tool / n >= 0.15 ? "object" : "element";
    const out = { cls, nounShare, isAction };
    classCache.set(w, out);
    return out;
  };
  const charNameWords = /* @__PURE__ */ new Set([...L.entityWords, ...L.roleWords]);
  for (const e of ents) {
    for (const part of e.name.toLowerCase().split(" ")) charNameWords.add(part);
    for (const a of e.aliases) charNameWords.add(a.toLowerCase());
  }
  const placeNameSet = new Set(ents.filter((e) => e.kind === "place").map((e) => e.name));
  const entSentE = /* @__PURE__ */ new Map();
  for (const e of ents) if (e.kind === "character" || e.kind === "place") for (const o of e.occ) {
    const si = sentOf[o.k];
    if (si >= 0) {
      const arr = entSentE.get(si) ?? entSentE.set(si, []).get(si);
      if (!arr.includes(e.name)) arr.push(e.name);
    }
  }
  const rareHere = (w) => wl(w) >= 4 && !stopSet.has(w) && !/\d/.test(w) && !charNameWords.has(w) && (wordChapters.get(w)?.size ?? 99) <= Math.max(2, Math.round(nCh * 0.12));
  const toneRaw = [];
  const chRange = Array.from({ length: nCh }, () => ({ lo: -1, hi: -1 })), chSents = Array.from({ length: nCh }, () => []);
  for (let k = 0; k < toks.length; k++) {
    if (!inBody(k)) continue;
    const c = chapterOfPage(page(k));
    if (c < 0 || c >= nCh) continue;
    if (chRange[c].lo < 0) chRange[c].lo = k;
    chRange[c].hi = k;
  }
  sentRows.forEach((r, si) => {
    const c = chapterOfPage(page(r.s));
    if (c >= 0 && c < nCh) chSents[c].push(si);
  });
  const chapters = starts.map((from, i) => {
    const to = i + 1 < nCh ? starts[i + 1] - 1 : bodyTo;
    const sig = [...chWords[i]].filter(([, c]) => c >= 2).map(([w, c]) => [w, c * chapterRar(w)]).sort((a, b) => b[1] - a[1]).slice(0, 6).map((x) => x[0]);
    const nodesHere = ents.filter((e) => e.kind !== "paratext" && e.kind !== "end-mark").map((e) => [e.name, e.occ.filter((o) => chapterOfPage(o.pg) === i).length]).filter((x) => x[1] > 0).sort((a, b) => b[1] - a[1]).slice(0, 4).map((x) => x[0]);
    const best2 = chSents[i].map((si) => sentRows[si]).reduce((b, r) => !b || r.max > b.max ? r : b, void 0);
    const lo = chRange[i].lo, hi = chRange[i].hi;
    const chText = lo >= 0 ? raw.slice(toks[lo].idx, toks[hi].end).replace(/[¶\f]/g, " ") : "";
    const sc = emb.vec.size ? { valence: 0, arousal: 0, words: 0 } : scoreSection(chText);
    let pos = 0, neg = 0, aro = 0, sn = 0;
    if (lo >= 0 && emb.vec.size) for (const r of sentRows) {
      if (page(r.s) < from || page(r.s) > to) continue;
      let net = 0, anyCharged = 0;
      for (let j = r.s; j <= r.e; j++) {
        const w = toks[j].w.toLowerCase();
        sn++;
        const v = extV.get(w) ?? 0;
        if (v) {
          net += v;
          anyCharged++;
        }
        aro += extA.get(w) ?? 0;
      }
      if (anyCharged) {
        if (net > 0) pos += net;
        else if (net < 0) neg -= net;
      }
    }
    const per1k = (n) => sn ? n / sn * 1e3 : 0, tot = per1k(pos) + per1k(neg);
    const sentenceBalance = tot > 0 ? (per1k(pos) - per1k(neg)) / tot : 0;
    const balance = sentenceBalance;
    const extScore = { valence: Math.round(balance * 100), arousal: tot + per1k(aro) };
    toneRaw.push({ v: extScore.valence, a: extScore.arousal, lex: sc, ev: null });
    const beats = [];
    let lastActors = [], lastPlace = null;
    for (let si = 0; si < sentRows.length; si++) {
      const r = sentRows[si], pg = page(r.s);
      if (pg < from || pg > to) continue;
      const names = entSentE.get(si) ?? [], places2 = names.filter((n) => placeNameSet.has(n)), actors = names.filter((n) => !placeNameSet.has(n));
      if (actors.length) lastActors = actors.slice(0, 2);
      if (places2.length) lastPlace = places2[0];
      const words = [];
      let net = 0;
      for (let j = r.s; j <= r.e; j++) {
        const w = toks[j].w.toLowerCase();
        net += extV.get(w) ?? 0;
        if (rareHere(w) && !words.includes(w)) words.push(w);
      }
      if (words.length) beats.push({ page: pg, actors: lastActors, place: lastPlace, words: words.slice(0, 3), charge: net });
    }
    const segs = [];
    for (const b of beats) {
      const last = segs[segs.length - 1];
      const lb = last?.b[last.b.length - 1];
      if (last && lb && lb.place === b.place && (lb.actors.some((a) => b.actors.includes(a)) || !lb.actors.length && !b.actors.length) && last.b.length < 8) last.b.push(b);
      else segs.push({ b: [b] });
    }
    while (segs.length > 10) {
      let bi = 0, bs = Infinity;
      for (let q2 = 0; q2 + 1 < segs.length; q2++) {
        const sz = segs[q2].b.length + segs[q2 + 1].b.length;
        if (sz < bs) {
          bs = sz;
          bi = q2;
        }
      }
      segs.splice(bi, 2, { b: [...segs[bi].b, ...segs[bi + 1].b] });
    }
    const events = segs.map((sg) => {
      const words = [];
      for (const b of sg.b) for (const w of b.words) if (!words.includes(w)) words.push(w);
      const cnt = /* @__PURE__ */ new Map();
      for (const b of sg.b) for (const a of b.actors) cnt.set(a, (cnt.get(a) ?? 0) + 1);
      return { pages: [sg.b[0].page, sg.b[sg.b.length - 1].page], actors: [...cnt].sort((x, y) => y[1] - x[1]).slice(0, 2).map((x) => x[0]), place: sg.b[0].place, words: words.slice(0, 8), charge: Math.round(sg.b.reduce((a, b) => a + b.charge, 0) * 10) / 10 };
    });
    const fcount = /* @__PURE__ */ new Map();
    let evWords = 0;
    for (const b of beats) for (const w of b.words) {
      const f = fieldOf.get(w);
      evWords++;
      if (f !== void 0) fcount.set(f, (fcount.get(f) ?? 0) + chapterRar(w));
    }
    const ftotal = [...fcount.values()].reduce((a, b) => a + b, 0) || 1;
    const symbols = [...fcount].sort((a, b) => b[1] - a[1]).slice(0, 3).map(([f, v]) => ({ label: semFields[f].label, share: Math.round(v / ftotal * 100) / 100, valence: Math.round(fieldValence[f] * 100) / 100 }));
    let evNum = 0, evDen = 0;
    for (const b of beats) for (const w of b.words) {
      const own = extV.get(w) ?? 0, f = fieldOf.get(w), fv = f !== void 0 ? fieldValence[f] : 0, wt2 = chapterRar(w);
      evNum += wt2 * (own !== 0 ? own : 0.5 * fv);
      evDen += wt2;
    }
    const evBalance = evWords >= 3 && evDen > 0 ? Math.max(-1, Math.min(1, evNum / evDen * 2)) : null;
    const mixCount = { action: 0, place: 0, object: 0, element: 0, dialogue: 0 };
    let mixN = 0;
    for (let k = lo; lo >= 0 && k <= hi; k++) {
      if (tmode[k] === 1) mixCount.dialogue++;
      const w = toks[k].w.toLowerCase();
      if (wl(w) < 4 || stopSet.has(w) || !occL.has(w)) continue;
      mixCount[classifyWord(w).cls]++;
      mixN++;
    }
    const mixDen = mixN || 1, mix = { action: round2(mixCount.action / mixDen), place: round2(mixCount.place / mixDen), object: round2(mixCount.object / mixDen), element: round2(mixCount.element / mixDen), dialogue: round2(mixCount.dialogue / Math.max(1, hi - lo + 1)) };
    toneRaw[toneRaw.length - 1].ev = evBalance;
    const clusters = chText.length > 800 ? topicClusters(chText.slice(0, 12e3), lang === "es" ? "es" : "en", 2).map((t) => t.terms.slice(0, 6)) : [];
    const mark = chapterMarks.find((m) => m.page === from);
    return {
      index: i + 1,
      title: mark?.title ?? `Chapter ${i + 1}`,
      pages: [from, to],
      words: chTokens[i],
      signature: sig,
      nodes: nodesHere,
      island: best2 ? raw.slice(toks[best2.s].idx, toks[best2.e].end).replace(/[¶\f]/g, " ").replace(/\s+/g, " ").slice(0, 170) : null,
      tension: 0,
      tone: { valence: 0, arousal: 0, eventBalance: null, label: "neutral" },
      clusters,
      themes: [],
      events,
      symbols,
      mix,
      inferred: inferred.has(from),
      kind: isPartTitle(mark?.title ?? "") ? "part" : inferred.has(from) && !mark?.title.trim().length ? "untitled" : inferred.has(from) && /^chapter\b/i.test(mark?.title ?? "") ? "untitled" : "chapter",
      inferredBy: inferred.get(from) ?? null
    };
  });
  {
    const mn = Math.min(...toneRaw.map((t) => t.a)), mx = Math.max(...toneRaw.map((t) => t.a));
    toneRaw.forEach((t, i) => {
      chapters[i].tone.valence = t.v;
      chapters[i].tone.eventBalance = t.ev === null ? null : round2(t.ev);
      chapters[i].tone.arousal = toneRaw.length > 1 ? Math.round(100 * (t.a - mn) / (mx - mn || 1)) : t.lex.arousal;
    });
  }
  if (chapters.length >= 4) {
    const vs = chapters.map((c) => c.tone.valence), as = chapters.map((c) => c.tone.arousal);
    const mean2 = vs.reduce((x, y) => x + y, 0) / vs.length, sd2 = Math.sqrt(vs.reduce((x, y) => x + (y - mean2) ** 2, 0) / vs.length) || 1;
    const sortedA = [...as].sort((x, y) => x - y), pct2 = (v) => sortedA.filter((x) => x <= v).length / sortedA.length;
    for (const c of chapters) {
      const z = (c.tone.valence - mean2) / sd2, ap = pct2(c.tone.arousal);
      c.tone.label = z <= -0.55 ? ap >= 0.45 ? "violent / dark" : "tense" : z >= 0.55 ? "tender / bright" : ap >= 0.85 ? "turbulent" : ap <= 0.25 ? "calm" : "neutral";
    }
  }
  void chapOf;
  lap("the thematic forest");
  const chIdx = (pg) => chapterOfPage(pg);
  const nChap = Math.max(1, nCh);
  const elWords = [];
  const charWords = /* @__PURE__ */ new Set([...L.entityWords, ...L.roleWords]);
  for (const e of ents) {
    for (const part of e.name.toLowerCase().split(" ")) charWords.add(part);
    for (const a of e.aliases) charWords.add(a.toLowerCase());
  }
  for (const [w, occ] of occL) {
    if (occ.length < Math.max(3, MIN_LEX) || named.has(w[0].toUpperCase() + w.slice(1)) || charWords.has(w) || wl(w) < 4) continue;
    const perCh = new Array(nChap).fill(0);
    for (const o of occ) perCh[Math.min(nChap - 1, chIdx(o.pg))]++;
    const present = perCh.filter((v) => v > 0).length;
    if (nChap >= 6 && present > nChap * 0.85) continue;
    const { cls, nounShare, isAction } = classifyWord(w);
    const hasDet = L.determiners.size > 0;
    if (hasDet && !isAction && nounShare < 0.3) continue;
    const tot = perCh.reduce((a, b) => a + b, 0);
    let H = 0;
    for (const v of perCh) if (v) H -= v / tot * Math.log(v / tot);
    const concentration = nChap > 1 ? 1 - H / Math.log(nChap) : 1;
    if (present < 2 && nChap >= 6) continue;
    if (isAction && concentration < 0.5) continue;
    elWords.push({ w, occ, cls, chaps: perCh, conc: concentration, present, score: isAction ? occ.length * concentration : concentration * Math.log(1 + occ.length) });
  }
  elWords.sort((a, b) => b.score - a.score);
  const motifsAll = elWords.filter((e) => e.cls !== "action" && e.present >= nChap * 0.6).sort((a, b) => b.occ.length - a.occ.length).slice(0, 10);
  const themesAll = elWords.filter((e) => e.cls !== "action" && e.present < nChap * 0.6 && e.occ.length >= 6).sort((a, b) => b.score - a.score).slice(0, 60);
  const actsAll = elWords.filter((e) => e.cls === "action").sort((a, b) => b.score - a.score).slice(0, 14);
  const elCand = [.../* @__PURE__ */ new Set([...motifsAll, ...themesAll, ...actsAll, ...elWords.filter((e) => e.cls !== "action").slice(0, 60)])], elIdx = new Map(elCand.map((e, i) => [e.w, i]));
  const perSent = /* @__PURE__ */ new Map();
  for (let i = 0; i < elCand.length; i++) for (const o of elCand[i].occ) {
    const si = sentOf[o.k];
    if (si < 0) continue;
    const arr = perSent.get(si) ?? perSent.set(si, []).get(si);
    if (!arr.includes(i)) arr.push(i);
  }
  const co = /* @__PURE__ */ new Map();
  const key = (a, b) => a < b ? a * 1e3 + b : b * 1e3 + a;
  for (const arr of perSent.values()) {
    const a = arr.slice(0, 14);
    for (let x = 0; x < a.length; x++) for (let y = x + 1; y < a.length; y++) co.set(key(a[x], a[y]), (co.get(key(a[x], a[y])) ?? 0) + 1);
  }
  const entSent = /* @__PURE__ */ new Map();
  for (const e of ents) if (e.kind === "character" || e.kind === "place") for (const o of e.occ) {
    const si = sentOf[o.k];
    if (si >= 0) (entSent.get(si) ?? entSent.set(si, /* @__PURE__ */ new Set()).get(si)).add(e.name);
  }
  const pearson = (a, b) => {
    const n = a.length, ma = a.reduce((x, y) => x + y, 0) / n, mb = b.reduce((x, y) => x + y, 0) / n;
    let d = 0, sa = 0, sb = 0;
    for (let i = 0; i < n; i++) {
      d += (a[i] - ma) * (b[i] - mb);
      sa += (a[i] - ma) ** 2;
      sb += (b[i] - mb) ** 2;
    }
    return d / Math.sqrt(sa * sb || 1);
  };
  const rootsT = [];
  const accept = (list, k) => {
    let taken = 0;
    for (const e of list) {
      if (taken >= k) break;
      const ei = elIdx.get(e.w);
      const dup = rootsT.some((r) => {
        const ri = elIdx.get(r.w);
        const c = co.get(key(ri, ei)) ?? 0;
        return c / Math.sqrt(r.occ.length * e.occ.length) >= 0.2 || pearson(r.chaps, e.chaps) >= 0.9;
      });
      if (!dup) {
        rootsT.push(e);
        taken++;
      }
    }
  };
  accept(motifsAll, 3);
  accept(themesAll, 9);
  accept(actsAll, 4);
  const themeForest = rootsT.map((R) => {
    const ri = elIdx.get(R.w);
    const rootChaps = R.chaps.map((v) => v > 0);
    const branches = elCand.map((X, xi) => ({ X, c: co.get(key(ri, xi)) ?? 0 })).filter((b) => b.X !== R && b.c >= 2).map((b) => ({ ...b, strength: b.c / Math.sqrt(R.occ.length * b.X.occ.length) })).sort((a, b) => b.strength - a.strength).slice(0, 6).map((b) => {
      const fx = b.X.chaps.findIndex((v) => v > 0), fr = R.chaps.findIndex((v) => v > 0);
      return { word: b.X.w, class: b.X.cls, strength: Math.round(b.strength * 100) / 100, born: fx >= fr && rootChaps[fx] === true };
    });
    const presentIdx = R.chaps.map((v, i) => v > 0 ? i + 1 : 0).filter(Boolean);
    const total = R.chaps.reduce((a, b) => a + b, 0) || 1;
    const centroid = R.chaps.reduce((a, v, i) => a + v * (i + 0.5), 0) / total / nChap;
    const share = presentIdx.length / nChap;
    const flow = presentIdx.length <= 3 ? "burst" : share >= 0.6 ? "constant motif" : centroid < 0.35 ? "fades" : centroid > 0.65 ? "builds" : presentIdx[presentIdx.length - 1] - presentIdx[0] + 1 > presentIdx.length * 1.8 ? "recurring" : "mid-book arc";
    const mx = Math.max(...R.chaps);
    const peaks = R.chaps.map((v, i) => v === mx && mx > 0 ? i + 1 : 0).filter(Boolean).slice(0, 3);
    const carry = /* @__PURE__ */ new Map();
    for (const o of R.occ) for (const n of entSent.get(sentOf[o.k]) ?? []) carry.set(n, (carry.get(n) ?? 0) + 1);
    return { root: R.w, class: R.cls, mentions: R.occ.length, chapters: presentIdx, share: Math.round(share * 100) / 100, flow, peaks, branches, orbit: emb.neighbors(R.w, 6).map((n) => n.word), rank: motifsAll.includes(R) || themesAll.indexOf(R) < 5 ? "primary" : "secondary", generates: [], carriers: [...carry].sort((a, b) => b[1] - a[1]).slice(0, 3).map((x) => x[0]) };
  });
  {
    const rn = new Set(themeForest.map((t) => t.root));
    for (const t of themeForest) t.generates = t.branches.filter((b) => b.born && rn.has(b.word)).map((b) => b.word);
  }
  const themeRelations = [];
  for (let i = 0; i < rootsT.length; i++) for (let j = i + 1; j < rootsT.length; j++) {
    const r = Math.round(pearson(rootsT[i].chaps, rootsT[j].chaps) * 100) / 100;
    const A = themeForest[i], B = themeForest[j];
    const shared = A.branches.map((b) => b.word).filter((w) => B.branches.some((x) => x.word === w));
    themeRelations.push({ a: A.root, b: B.root, sharedBranches: shared, coFlow: r, relation: r >= 0.45 ? "flow together" : r <= -0.2 ? "alternate" : "independent" });
  }
  themeRelations.sort((a, b) => Math.abs(b.coFlow) - Math.abs(a.coFlow));
  for (const c of chapters) c.themes = rootsT.map((R) => ({ w: R.w, v: R.chaps[c.index - 1] ?? 0 })).filter((x) => x.v > 0).sort((a, b) => b.v - a.v).slice(0, 3).map((x) => x.w);
  const claimed = /* @__PURE__ */ new Map();
  let collisions = 0;
  for (const e of [...ents, ...live.filter((x) => x.lex)].sort((a, b) => b.name.length - a.name.length)) {
    if (e.kind !== "character" && e.kind !== "place" && !e.lex) continue;
    for (const o of e.occ) {
      const had = claimed.get(o.k);
      if (had !== void 0 && had !== e.name) collisions++;
      else claimed.set(o.k, e.name);
    }
  }
  lap("a chain for every word of the work function word");
  let wordIndex = {};
  if (opts.wordIndex !== false) {
    const cw = [], cp = [], cc = [], origK = [];
    for (let k = 0; k < toks.length; k++) {
      if (!inBody(k) || titleTok[k]) continue;
      cw.push(toks[k].w.toLowerCase());
      cp.push(page(k));
      cc.push(chapterOfPage(page(k)));
      origK.push(k);
    }
    wordIndex = buildWordIndex({
      words: cw,
      pages: cp,
      chapters: cc,
      NP,
      nChapters: nCh,
      isFunction: (w) => stopSet.has(w) || wl(w) < 3,
      classOf: (w) => occL.has(w) ? classifyWord(w).cls : "element",
      rarity: (w) => pgset.has(w) ? idf(w) : 1,
      nodeAt: (i) => claimed.get(origK[i]) ?? null
    });
  }
  for (const t of sentences.top) {
    const ws = [...new Set((t.text.toLowerCase().match(/[\p{L}]{4,}/gu) ?? []).filter((w) => !stopSet.has(w) && occL.has(w)))];
    if (!ws.length) continue;
    const bestBy = (f) => ws.reduce((a, b) => f(b) > f(a) ? b : a, ws[0]);
    t.scales = { page: bestBy((w) => idf(w)), chapter: bestBy((w) => chapterRar(w)), book: bestBy((w) => -(occL.get(w)?.length ?? 0)) };
  }
  const wordNodes = lexEnts.slice(0, 30).map((e) => {
    const pages = new Set(e.occ.map((o) => o.pg));
    return { word: e.name, mentions: e.occ.length, pages: pages.size, first: Math.min(...pages), last: Math.max(...pages), weight: Math.round(weightOf(e)), scales: { page: Math.round(idf(e.name) * 100) / 100, chapter: Math.round(chapterRar(e.name) * 100) / 100, book: Math.round(Math.log(Math.max(2, toks.length) / e.occ.length) * 100) / 100 }, density: density(e.occ) };
  });
  lap("ROUTES & PROXIMITY");
  const entityCount = (/* @__PURE__ */ new Set([...claimed.values()])).size;
  const SLn = Math.min(Math.max(NP, 1), BINS_MAX);
  const sliceOfPg = (pg) => Math.min(SLn - 1, Math.floor((pg - 1) / Math.max(NP, 1) * SLn));
  const pgOfSlice = (sl) => [Math.round(sl * NP / SLn) + 1, Math.max(Math.round((sl + 1) * NP / SLn), Math.round(sl * NP / SLn) + 1)];
  const curPlace = new Array(sentRows.length).fill(null);
  {
    let last = null, lastCh = -1;
    sentRows.forEach((r, si) => {
      const c = chapterOfPage(page(r.s));
      if (c !== lastCh) {
        last = null;
        lastCh = c;
      }
      for (const n of entSentE.get(si) ?? []) if (placeNameSet.has(n)) last = n;
      curPlace[si] = last;
    });
  }
  const mkTrack = (name, kind, occs) => {
    const ks = Array.from({ length: SLn }, () => []), vec = new Array(SLn).fill(null), places2 = Array.from({ length: SLn }, () => /* @__PURE__ */ new Map());
    for (const o of occs) {
      const sl = sliceOfPg(o.pg);
      ks[sl].push(o.k);
      if (emb.vec.size) {
        let v = vec[sl];
        if (!v) {
          v = new Float32Array(emb.dim);
          vec[sl] = v;
        }
        for (let d = -8; d <= 8; d++) {
          const t = toks[o.k + d];
          if (!t || d === 0 || titleTok[o.k + d] || sentOf[o.k + d] !== sentOf[o.k]) continue;
          const x = emb.vec.get(t.w.toLowerCase());
          if (x) for (let q2 = 0; q2 < emb.dim; q2++) v[q2] += x[q2];
        }
      }
      const si = sentOf[o.k];
      if (si >= 0 && kind === "character" && curPlace[si]) places2[sl].set(curPlace[si], (places2[sl].get(curPlace[si]) ?? 0) + 1);
    }
    ks.forEach((a) => a.sort((x, y) => x - y));
    return { name, kind, mentions: occs.length, ks, vec, places: places2, present: ks.map((a) => a.length > 0) };
  };
  const minGap = (a, b) => {
    let i = 0, j = 0, best2 = Infinity;
    while (i < a.length && j < b.length) {
      best2 = Math.min(best2, Math.abs(a[i] - b[j]));
      if (a[i] < b[j]) i++;
      else j++;
    }
    return best2;
  };
  const cosV = (a, b) => {
    if (!a || !b) return null;
    let d = 0, na = 0, nb = 0;
    for (let q2 = 0; q2 < a.length; q2++) {
      d += a[q2] * b[q2];
      na += a[q2] * a[q2];
      nb += b[q2] * b[q2];
    }
    return d / Math.sqrt(na * nb || 1);
  };
  const topPlaces = (t) => {
    const c = /* @__PURE__ */ new Map();
    t.places.forEach((m) => m.forEach((v, k) => c.set(k, (c.get(k) ?? 0) + v)));
    return [...c].sort((a, b) => b[1] - a[1]).slice(0, 2).map((x) => x[0]);
  };
  const SCENE = 80;
  const pairOf = (kind, A, B) => {
    const together = [];
    for (let sl = 0; sl < SLn; sl++) if (A.present[sl] && B.present[sl]) together.push(sl);
    const pa = A.present.filter(Boolean).length, pb = B.present.filter(Boolean).length;
    if (!together.length) return null;
    const close = together.filter((sl) => minGap(A.ks[sl], B.ks[sl]) <= SCENE);
    const enc = [];
    let st = -1, pv = -1e3;
    for (const sl of close) {
      if (sl - pv > 2) {
        if (st >= 0) enc.push([pgOfSlice(st)[0], pgOfSlice(pv)[1]]);
        st = sl;
      }
      pv = sl;
    }
    if (st >= 0) enc.push([pgOfSlice(st)[0], pgOfSlice(pv)[1]]);
    let best2 = null;
    for (const sl of together) {
      const w = minGap(A.ks[sl], B.ks[sl]);
      if (!best2 || w < best2.w) best2 = { sl, w };
    }
    const sol = (sl) => {
      const c = cosV(A.vec[sl], B.vec[sl]);
      return c === null ? null : 1 - c;
    };
    const series = together.map((sl) => sol(sl)).filter((x) => x !== null);
    const half = Math.floor(series.length / 2), mean2 = (a) => a.reduce((x, y) => x + y, 0) / (a.length || 1);
    const trend = series.length >= 4 ? mean2(series.slice(half)) - mean2(series.slice(0, half)) < -0.05 ? "converging" : mean2(series.slice(half)) - mean2(series.slice(0, half)) > 0.05 ? "diverging" : "steady" : "steady";
    const share = together.length / Math.max(1, Math.min(pa, pb));
    const relation = share >= 0.85 && Math.max(pa, pb) >= 1.5 * Math.min(pa, pb) ? "contained" : share >= 0.6 && enc.length >= 2 ? "companions" : enc.length >= 1 ? "crossing" : "apart";
    const pl = topPlaces(A).filter((x) => topPlaces(B).includes(x));
    return { kind, a: A.name, b: B.name, together: together.length, encounters: enc.slice(0, 6), closest: best2 ? { pages: pgOfSlice(best2.sl), words: best2.w, solar: round2(sol(best2.sl) ?? 1) } : null, trend, relation, sharedPlaces: pl };
  };
  const tracked = live.filter((e) => !e.lex || e.aliases.length > 0).filter((e) => (e.kind === "character" || e.kind === "place") && e.occ.length >= 2).sort((a, b) => b.occ.length - a.occ.length).slice(0, 40);
  const trackOf = new Map(tracked.map((e) => [e.name, mkTrack(e.name, e.kind === "place" ? "place" : "character", e.occ)]));
  const routes = [...trackOf.values()].filter((t) => t.kind === "character").slice(0, 14).map((t) => {
    const legs = [];
    let cur = null;
    for (let sl = 0; sl < SLn; sl++) {
      const pl = [...t.places[sl]].sort((a2, b2) => b2[1] - a2[1])[0]?.[0] ?? null;
      if (!t.present[sl] || !pl) {
        continue;
      }
      const [a, b] = pgOfSlice(sl);
      if (cur && cur.place === pl && a - cur.pages[1] <= 3 * Math.ceil(NP / SLn)) cur.pages[1] = b;
      else {
        cur = { pages: [a, b], place: pl };
        legs.push(cur);
      }
    }
    return { name: t.name, kind: "character", mentions: t.mentions, legs: legs.slice(0, 14) };
  });
  const routePairs = [];
  const nodeTracks = [...trackOf.values()];
  for (let i = 0; i < nodeTracks.length; i++) for (let j = i + 1; j < nodeTracks.length; j++) {
    const p = pairOf("node-node", nodeTracks[i], nodeTracks[j]);
    if (p) routePairs.push(p);
  }
  const rank = (x) => x.encounters.length * 3 + x.together;
  const nodePairs = routePairs.splice(0).sort((a, b) => rank(b) - rank(a)).slice(0, 24);
  const entByName = new Map([...live, ...ents].map((e) => [e.name, e]));
  const memberCache = /* @__PURE__ */ new Map();
  const memberTrack = (n) => {
    if (!memberCache.has(n)) {
      const e = entByName.get(n);
      memberCache.set(n, e && !e.lex ? mkTrack(n, e.kind === "place" ? "place" : "character", e.occ) : null);
    }
    return memberCache.get(n);
  };
  const combine = (name, ts) => {
    const ks = Array.from({ length: SLn }, (_, sl) => ts.flatMap((t) => t.ks[sl]).sort((x, y) => x - y));
    const vec = Array.from({ length: SLn }, (_, sl) => {
      const parts = ts.map((t) => t.vec[sl]).filter((x) => !!x);
      if (!parts.length) return null;
      const v = new Float32Array(emb.dim);
      for (const p of parts) for (let q2 = 0; q2 < emb.dim; q2++) v[q2] += p[q2];
      return v;
    });
    const places2 = Array.from({ length: SLn }, (_, sl) => {
      const m = /* @__PURE__ */ new Map();
      for (const t of ts) t.places[sl].forEach((v, k) => m.set(k, (m.get(k) ?? 0) + v));
      return m;
    });
    return { name, kind: ts[0]?.kind ?? "character", mentions: ts.reduce((a, t) => a + t.mentions, 0), ks, vec, places: places2, present: ks.map((a) => a.length > 0) };
  };
  const trees = forest.slice(0, 12).map((f) => ({ f, members: /* @__PURE__ */ new Set([f.root, ...f.branches.map((b) => b.name)]) }));
  const treePairs = [];
  for (let i = 0; i < trees.length; i++) for (let j = i + 1; j < trees.length; j++) {
    const A = [...trees[i].members].filter((n) => !trees[j].members.has(n)).map(memberTrack).filter((t) => !!t);
    const B = [...trees[j].members].filter((n) => !trees[i].members.has(n)).map(memberTrack).filter((t) => !!t);
    if (!A.length || !B.length) continue;
    const p = pairOf("tree-tree", combine(trees[i].f.root, A), combine(trees[j].f.root, B));
    if (p) treePairs.push(p);
  }
  const nodeTree = [];
  for (const nt of nodeTracks) for (const tr of trees) {
    if (tr.members.has(nt.name)) continue;
    const ms = [...tr.members].map(memberTrack).filter((t) => !!t && t.name !== nt.name);
    if (!ms.length) continue;
    const p = pairOf("node-tree", nt, combine(tr.f.root, ms));
    if (p) nodeTree.push(p);
  }
  routePairs.push(...nodePairs, ...treePairs.sort((a, b) => rank(b) - rank(a)).slice(0, 12), ...nodeTree.sort((a, b) => rank(b) - rank(a)).slice(0, 12));
  lap("WHO LIVES WHERE");
  const castEnts = live.filter((e) => (!e.lex || e.aliases.length > 0) && e.kind === "character" && e.occ.length >= 2);
  const atPlace = /* @__PURE__ */ new Map(), homeTot = /* @__PURE__ */ new Map();
  for (const e of castEnts) {
    const m = /* @__PURE__ */ new Map();
    for (const o of e.occ) {
      const si = sentOf[o.k];
      const pl = si >= 0 ? curPlace[si] : null;
      if (pl) m.set(pl, (m.get(pl) ?? 0) + 1);
    }
    atPlace.set(e.name, m);
    homeTot.set(e.name, [...m.values()].reduce((a, b) => a + b, 0));
  }
  const homeOf = (name, place) => {
    const t = homeTot.get(name) ?? 0;
    return t ? (atPlace.get(name)?.get(place) ?? 0) / t : 0;
  };
  const roleOf = (h) => h >= 0.5 ? "native" : h >= 0.2 ? "regular" : "visitor";
  const meet = /* @__PURE__ */ new Map();
  {
    const castNames = new Set(castEnts.map((e) => e.name));
    for (let si = 0; si < sentRows.length; si++) {
      const here = [.../* @__PURE__ */ new Set([...entSentE.get(si) ?? [], ...entSentE.get(si + 1) ?? []])].filter((n) => castNames.has(n));
      const pl = curPlace[si];
      if (!pl || here.length < 2) continue;
      const r = sentRows[si];
      let sp = 0, ch = 0, nTok = 0;
      for (let j = r.s; j <= r.e; j++) {
        nTok++;
        if (tmode[j] === 1) sp++;
        ch += extV.get(toks[j].w.toLowerCase()) ?? 0;
      }
      for (let i = 0; i < here.length; i++) for (let j = i + 1; j < here.length; j++) {
        const [a, b] = here[i] < here[j] ? [here[i], here[j]] : [here[j], here[i]], key2 = `${a}|${b}|${pl}`;
        const m = meet.get(key2) ?? meet.set(key2, { a, b, place: pl, times: 0, dialogue: 0, charge: 0 }).get(key2);
        m.times++;
        if (nTok && sp / nTok >= 0.4) m.dialogue++;
        m.charge += nTok ? ch / nTok : 0;
      }
    }
  }
  const placeCasts = [...placeNameSet].map((pl) => {
    const members = castEnts.map((e) => ({ name: e.name, n: atPlace.get(e.name)?.get(pl) ?? 0 })).filter((x) => x.n > 0);
    const mass = members.reduce((a, b) => a + b.n, 0);
    if (!mass) return null;
    const cast = members.sort((a, b) => b.n - a.n).slice(0, 10).map((x) => ({ name: x.name, weight: round2(x.n / mass), home: round2(homeOf(x.name, pl)), role: roleOf(homeOf(x.name, pl)) }));
    const meetings = [...meet.values()].filter((m) => m.place === pl && m.times >= 2).sort((a, b) => b.times - a.times).slice(0, 6).map((m) => {
      const na = homeOf(m.a, pl) >= 0.5, nb = homeOf(m.b, pl) >= 0.5;
      return { a: m.a, b: m.b, times: m.times, dialogue: m.dialogue, charge: round2(m.charge / m.times * 10), kind: na && nb ? "between natives" : na || nb ? "host and guest" : "between guests" };
    });
    const pe = ents.find((e) => e.name === pl);
    return { place: pl, pages: pe ? core80(pe.occ) : [0, 0], mentions: mass, cast, meetings };
  }).filter((x) => !!x).sort((a, b) => b.mentions - a.mentions);
  lap("THE SOLAR SYSTEM OF EVERY NODE");
  const nodeList2 = [.../* @__PURE__ */ new Set([...live.filter((e) => !e.lex || e.aliases.length > 0 || bigRole(e)), ...ents])].filter((e) => (e.kind === "character" || e.kind === "place") && e.occ.length >= 2);
  nodeList2.sort((a, b) => b.occ.length - a.occ.length);
  let Ntot = 0;
  for (const o of occL.values()) Ntot += o.length;
  const Vtot = occL.size, hasDet2 = L.determiners.size > 0;
  const profile = /* @__PURE__ */ new Map();
  const acrossNodes = /* @__PURE__ */ new Map();
  const windowWords = (k0, R) => {
    const out = [];
    for (let d = -R; d <= R; d++) {
      const idx = k0 + d, tk = toks[idx];
      if (!tk || d === 0 || !inBody(idx) || titleTok[idx] || sentOf[idx] !== sentOf[k0]) continue;
      const w = tk.w.toLowerCase();
      if (wl(w) < 4 || stopSet.has(w) || charNameWords.has(w) || /\d/.test(w)) continue;
      out.push(w);
    }
    return out;
  };
  for (const e of nodeList2) {
    const counts = /* @__PURE__ */ new Map();
    let T = 0;
    for (const o of e.occ) for (const w of windowWords(o.k, 15)) {
      counts.set(w, (counts.get(w) ?? 0) + 1);
      T++;
      acrossNodes.set(w, (acrossNodes.get(w) ?? 0) + 1);
    }
    profile.set(e.name, { counts, T });
  }
  const shrunk = (c, T, w) => {
    const n = occL.get(w)?.length ?? 1, a = 0.5;
    const pX = (c + a * (n / Ntot) * Vtot) / (T + a * Vtot), p0 = n / Ntot;
    return Math.log(pX / p0) * c;
  };
  const ranked2 = (name) => {
    const pr = profile.get(name);
    return [...pr.counts].map(([w, c]) => {
      const cl = classifyWord(w);
      return { word: w, count: c, score: shrunk(c, pr.T, w), lift: round2(c / (pr.T || 1) / ((occL.get(w)?.length ?? 1) / Ntot)), exclusivity: round2(c / (acrossNodes.get(w) ?? c)), action: cl.isAction, noun: (!hasDet2 || cl.nounShare >= 0.4) && !L.verbish.test(w) };
    }).filter((x) => x.score > 0).sort((a, b) => b.score - a.score);
  };
  const affinity = nodeList2.map((e) => {
    const r = ranked2(e.name), strip = ({ word, count, lift, exclusivity }) => ({ word, count, lift, exclusivity });
    return { node: e.name, elements: r.filter((x) => !x.action && x.noun).slice(0, 12).map(strip), actions: r.filter((x) => x.action).slice(0, 5).map(strip) };
  });
  lap("CANONICAL INJECTION");
  const innerOf = new Map(affinity.map((a) => [a.node, a.elements.map((x) => x.word)]));
  const outerOf = /* @__PURE__ */ new Map();
  for (const e of nodeList2) {
    const inner = new Set(innerOf.get(e.name) ?? []), uni = /* @__PURE__ */ new Map();
    for (const o of e.occ) {
      const si = sentOf[o.k];
      if (si < 0) continue;
      for (let q2 = Math.max(0, si - 3); q2 <= Math.min(sentRows.length - 1, si + 3); q2++) {
        if (q2 === si) continue;
        const r = sentRows[q2];
        for (let j = r.s; j <= r.e; j++) {
          if (titleTok[j]) continue;
          const w = toks[j].w.toLowerCase();
          if (wl(w) < 4 || stopSet.has(w) || charNameWords.has(w) || inner.has(w) || /\d/.test(w)) continue;
          uni.set(w, (uni.get(w) ?? 0) + 1);
        }
      }
    }
    const rows = [...uni].filter(([w]) => {
      const cl = classifyWord(w);
      return !cl.isAction && (!hasDet2 || cl.nounShare >= 0.4) && !L.verbish.test(w);
    }).map(([w, c]) => [w, shrunk(c, [...uni.values()].reduce((a, b) => a + b, 0), w)]).filter((x) => x[1] > 0).sort((a, b) => b[1] - a[1]);
    outerOf.set(e.name, rows.slice(0, 14).map((x) => x[0]));
  }
  const holders = /* @__PURE__ */ new Map();
  for (const e of nodeList2) for (const w of [...innerOf.get(e.name) ?? [], ...outerOf.get(e.name) ?? []]) (holders.get(w) ?? holders.set(w, []).get(w)).push(e.name);
  const circles = nodeList2.map((e) => {
    const inner = innerOf.get(e.name) ?? [], outer = outerOf.get(e.name) ?? [];
    const withOf = (w) => (holders.get(w) ?? []).filter((n) => n !== e.name);
    return { node: e.name, inner, outer, shared: [...inner, ...outer].map((w) => ({ word: w, with: withOf(w).slice(0, 4) })).filter((x) => x.with.length).slice(0, 10), proper: inner.filter((w) => !withOf(w).length) };
  });
  lap("IDENTITY FUNCTION");
  const rngS = (seed) => {
    let x = (seed ^ 2654435769) >>> 0 || 1;
    return () => {
      x ^= x << 13;
      x >>>= 0;
      x ^= x >>> 17;
      x ^= x << 5;
      x >>>= 0;
      return x / 4294967296;
    };
  };
  const meanVec = new Float32Array(emb.dim);
  {
    let n = 0;
    for (const v of emb.vec.values()) {
      for (let q2 = 0; q2 < emb.dim; q2++) meanVec[q2] += v[q2];
      n++;
    }
    if (n) for (let q2 = 0; q2 < emb.dim; q2++) meanVec[q2] /= n;
  }
  const centredVec = (w) => {
    const v = emb.vec.get(w);
    if (!v) return null;
    const c = new Float32Array(emb.dim);
    for (let q2 = 0; q2 < emb.dim; q2++) c[q2] = v[q2] - meanVec[q2];
    return c;
  };
  const mentionVec = (k0) => {
    const v = new Float32Array(emb.dim);
    let any = false;
    for (const w of windowWords(k0, 15)) {
      const c = centredVec(w);
      if (c) {
        for (let q2 = 0; q2 < emb.dim; q2++) v[q2] += c[q2];
        any = true;
      }
    }
    return any ? v : null;
  };
  const cosF = (a, b) => {
    if (!a || !b) return 0;
    let d = 0, na = 0, nb = 0;
    for (let q2 = 0; q2 < a.length; q2++) {
      d += a[q2] * b[q2];
      na += a[q2] * a[q2];
      nb += b[q2] * b[q2];
    }
    return d / Math.sqrt(na * nb || 1);
  };
  const sumV = (vs) => {
    const t = new Float32Array(emb.dim);
    let any = false;
    for (const v of vs) if (v) {
      for (let q2 = 0; q2 < emb.dim; q2++) t[q2] += v[q2];
      any = true;
    }
    return any ? t : null;
  };
  const stabilityV = (early, late, seed) => {
    const obs = cosF(sumV(early), sumV(late)), pool = [...early, ...late], g = rngS(seed), reps = 40;
    let below = 0, acc = 0;
    for (let r = 0; r < reps; r++) {
      const sh = [...pool];
      for (let i = sh.length - 1; i > 0; i--) {
        const j = Math.floor(g() * (i + 1));
        [sh[i], sh[j]] = [sh[j], sh[i]];
      }
      const c = cosF(sumV(sh.slice(0, early.length)), sumV(sh.slice(early.length)));
      acc += c;
      if (c <= obs) below++;
    }
    return { obs, base: acc / reps, rank: below / reps };
  };
  const chargeOf = (ks) => {
    let c = 0, n = 0;
    for (const k0 of ks) for (let d = -15; d <= 15; d++) {
      const idx = k0 + d, tk = toks[idx];
      if (!tk || d === 0 || !inBody(idx) || titleTok[idx] || sentOf[idx] !== sentOf[k0]) continue;
      c += extV.get(tk.w.toLowerCase()) ?? 0;
      n++;
    }
    return n ? c / n : 0;
  };
  const bagOfKs = (ks) => {
    const m = /* @__PURE__ */ new Map();
    for (const k0 of ks) for (const w of windowWords(k0, 15)) m.set(w, (m.get(w) ?? 0) + 1);
    return m;
  };
  const arcs = [], arcObs = [];
  for (const e of nodeList2.slice(0, 60)) {
    const occs = [...e.occ].sort((a, b) => a.k - b.k), chs = [...new Set(occs.map((o) => chapterOfPage(o.pg)))].sort((a, b) => a - b);
    let earlyO, lateO;
    if (chs.length >= 2) {
      const cut = Math.ceil(chs.length / 2), eSet = new Set(chs.slice(0, cut));
      earlyO = occs.filter((o) => eSet.has(chapterOfPage(o.pg)));
      lateO = occs.filter((o) => !eSet.has(chapterOfPage(o.pg)));
    } else {
      const h = Math.floor(occs.length / 2);
      earlyO = occs.slice(0, h);
      lateO = occs.slice(occs.length - h);
    }
    if (!earlyO.length || !lateO.length) continue;
    const st = stabilityV(earlyO.map((o) => mentionVec(o.k)), lateO.map((o) => mentionVec(o.k)), occs.length * 31 + 7);
    const fe = bagOfKs(earlyO.map((o) => o.k)), fl = bagOfKs(lateO.map((o) => o.k));
    const te = [...fe.values()].reduce((a, b) => a + b, 0) || 1, tl = [...fl.values()].reduce((a, b) => a + b, 0) || 1;
    const rows = [.../* @__PURE__ */ new Set([...fe.keys(), ...fl.keys()])].filter((w) => {
      const cl = classifyWord(w);
      return !cl.isAction && (!hasDet2 || cl.nounShare >= 0.4) && !L.verbish.test(w);
    }).map((w) => ({ w, ce: fe.get(w) ?? 0, cl: fl.get(w) ?? 0, e: (fe.get(w) ?? 0) / te, l: (fl.get(w) ?? 0) / tl }));
    const kept = rows.filter((r) => r.ce >= 1 && r.cl >= 1).sort((a, b) => Math.min(b.e, b.l) - Math.min(a.e, a.l)).slice(0, 6).map((r) => r.w);
    const lost = rows.filter((r) => r.ce >= 1 && r.cl === 0).sort((a, b) => b.e - a.e).slice(0, 6).map((r) => r.w);
    const gained = rows.filter((r) => r.cl >= 1 && r.ce === 0).sort((a, b) => b.l - a.l).slice(0, 6).map((r) => r.w);
    const chE = chargeOf(earlyO.map((o) => o.k)), chL = chargeOf(lateO.map((o) => o.k)), dC = chL - chE;
    arcObs.push(st.obs);
    arcs.push({
      node: e.name,
      mentions: occs.length,
      identity: round2(st.rank),
      kept,
      lost,
      gained,
      chargeEarly: round2(chE * 10),
      chargeLate: round2(chL * 10),
      direction: dC > 4e-3 ? "rises" : dC < -4e-3 ? "falls" : "steady",
      verdict: st.rank >= 0.2 ? "identity" : st.rank <= 0.05 ? "transforms" : "partial",
      relative: 0,
      confidence: round2(Math.min(1, Math.min(earlyO.length, lateO.length) / 10)),
      basis: chs.length >= 2 ? `chapters ${chs[0] + 1}\u2013${chs[chs.length - 1] + 1}` : "pages within one chapter"
    });
  }
  {
    const sorted = [...arcObs].sort((a, b) => a - b);
    arcs.forEach((a, i) => {
      a.relative = round2(sorted.length > 1 ? sorted.filter((x) => x < arcObs[i]).length / (sorted.length - 1) : 1);
    });
  }
  const worldIdentity = (() => {
    const loPg = body ? body[0] : 1, hiPg = body ? body[1] : NP, span = Math.max(1, hiPg - loPg + 1);
    const freq2 = [...occL].filter(([w, o]) => o.length >= 8 && !charNameWords.has(w) && wl(w) >= 4 && emb.vec.has(w) && (!hasDet2 || classifyWord(w).nounShare >= 0.3 || classifyWord(w).isAction)).sort((a, b) => b[1].length - a[1].length).slice(0, 300);
    const rows = [];
    for (const [w, occs] of freq2) {
      const eV = [], lV = [];
      for (const o of occs) {
        if (!inBody(o.k) || titleTok[o.k]) continue;
        const rel = (o.pg - loPg) / span;
        if (rel < 1 / 3) eV.push(mentionVec(o.k));
        else if (rel >= 2 / 3) lV.push(mentionVec(o.k));
      }
      if (eV.length < 2 || lV.length < 2) continue;
      const st = stabilityV(eV, lV, w.length * 97 + occs.length);
      rows.push({ word: w, mentions: occs.length, stability: round2(st.rank), obs: st.obs });
    }
    const invariant = [...rows].sort((a, b) => b.obs - a.obs).slice(0, 10).map(({ word, mentions, stability }) => ({ word, mentions, stability }));
    const drift = [...rows].sort((a, b) => a.obs - b.obs).slice(0, 10).map(({ word, mentions, stability }) => ({ word, mentions, stability }));
    const f = chapters[0], l = chapters[chapters.length - 1];
    const setOf = (c) => new Set(c ? [...c.signature, ...c.events.flatMap((e) => e.words)] : []);
    const A = setOf(f), B = setOf(l);
    let inter = 0;
    for (const w of A) if (B.has(w)) inter++;
    const sim = A.size + B.size ? inter / (A.size + B.size - inter) : 0;
    const placeOf = (c) => c?.events.find((e) => e.place)?.place ?? null;
    const samePlace = !!placeOf(f) && placeOf(f) === placeOf(l);
    return { invariant, drift, circularity: { similarity: round2(sim), samePlace, verdict: sim >= 0.2 || samePlace && sim >= 0.1 ? "circular" : "open" } };
  })();
  lap("TONE");
  const nS = sentRows.length, sVal = new Float64Array(nS), sCh = new Int32Array(nS), sAro = new Float64Array(nS), sW = new Int32Array(nS), sSp = new Float64Array(nS);
  for (let si = 0; si < nS; si++) {
    const r = sentRows[si];
    let net = 0, charged = 0, ar = 0, w0 = 0, sp = 0, len = 0;
    for (let j = r.s; j <= r.e; j++) {
      len++;
      if (tmode[j] === 1) sp++;
      if (titleTok[j] || !inBody(j)) continue;
      const w = toks[j].w.toLowerCase();
      if (stopSet.has(w) || wl(w) < 3) continue;
      w0++;
      const v = extV.get(w) ?? 0;
      if (v) {
        net += v;
        charged++;
      }
      ar += extA.get(w) ?? 0;
    }
    sVal[si] = charged ? net / charged : 0;
    sCh[si] = charged;
    sW[si] = w0;
    sAro[si] = w0 >= 3 ? ar / Math.sqrt(w0) : 0;
    sSp[si] = len ? sp / len : 0;
  }
  const aSorted = [...sAro].filter((_, i) => sW[i] >= 3).sort((a, b) => a - b), pct = (a) => {
    if (!aSorted.length || a <= 0) return 0;
    let lo = 0, hi = aSorted.length;
    while (lo < hi) {
      const m = lo + hi >> 1;
      if (aSorted[m] < a) lo = m + 1;
      else hi = m;
    }
    return lo / aSorted.length * 100;
  };
  const sAroN = Float64Array.from(sAro, pct), sTen = Float64Array.from(sAroN, (a, i) => a * (0.5 + 0.5 * (sCh[i] ? (1 - sVal[i]) / 2 : 0.5)));
  const pageOfS = (si) => page(sentRows[si].s);
  const nodeSent = /* @__PURE__ */ new Map();
  for (const e of nodeList2) nodeSent.set(e.name, [...new Set(e.occ.map((o) => sentOf[o.k]).filter((x) => x >= 0))].sort((a, b) => a - b));
  const toneOfSet = (ss) => {
    let net = 0, charged = 0, ar = 0, tn = 0, sp = 0;
    for (const si of ss) {
      net += sVal[si] * sCh[si];
      charged += sCh[si];
      ar += sAroN[si];
      tn += sTen[si];
      sp += sSp[si] >= 0.3 ? 1 : 0;
    }
    const n = Math.max(1, ss.length);
    return { valence: charged ? Math.round(net / charged * 100) : 0, arousal: Math.round(ar / n), tension: Math.round(tn / n), spoken: round2(sp / n) };
  };
  const peakOf = (ss) => {
    if (!ss.length) return null;
    let best2 = ss[0];
    for (const si of ss) if (sTen[si] > sTen[best2]) best2 = si;
    return pageOfS(best2);
  };
  const trendOf = (ss, f) => {
    if (ss.length < 6) return 0;
    const t = Math.floor(ss.length / 3), m = (a) => a.reduce((x, y) => x + f(y), 0) / (a.length || 1);
    return m(ss.slice(-t)) - m(ss.slice(0, t));
  };
  const tension = { nodes: [], pairs: [], curve: [], peaks: [], chapters: [] };
  for (const e of nodeList2.slice(0, 60)) {
    const ss = nodeSent.get(e.name) ?? [];
    if (ss.length < 2) continue;
    const t = toneOfSet(ss), d = trendOf(ss, (si) => sVal[si]);
    const byCh = /* @__PURE__ */ new Map();
    for (const si of ss) {
      const c = chapterOfPage(pageOfS(si)) + 1;
      (byCh.get(c) ?? byCh.set(c, []).get(c)).push(si);
    }
    tension.nodes.push({ node: e.name, kind: e.kind, sentences: ss.length, ...t, trend: d < -0.08 ? "darkens" : d > 0.08 ? "brightens" : "steady", peak: peakOf(ss), byChapter: [...byCh].filter(([, v]) => v.length >= 2).sort((a, b) => a[0] - b[0]).map(([chapter, v]) => {
      const x = toneOfSet(v);
      return { chapter, valence: x.valence, tension: x.tension, sentences: v.length };
    }) });
  }
  {
    const names = tension.nodes.slice().sort((a, b) => b.sentences - a.sentences).slice(0, 30).map((x) => x.node), pairS = /* @__PURE__ */ new Map();
    for (let si = 0; si < nS; si++) {
      const here = (entSentE.get(si) ?? []).filter((n) => names.includes(n));
      if (!here.length) continue;
      const next = (entSentE.get(si + 1) ?? []).filter((n) => names.includes(n));
      for (const a of here) for (const b of [...here, ...next]) if (a < b) {
        const k = a + "\0" + b;
        (pairS.get(k) ?? pairS.set(k, /* @__PURE__ */ new Set()).get(k)).add(si);
      } else if (b < a && !here.includes(b)) {
        const k = b + "\0" + a;
        (pairS.get(k) ?? pairS.set(k, /* @__PURE__ */ new Set()).get(k)).add(si);
      }
    }
    for (const [k, set] of pairS) {
      if (set.size < 3) continue;
      const [a, b] = k.split("\0"), ss = [...set].sort((x, y) => x - y), t = toneOfSet(ss), d = trendOf(ss, (si) => sTen[si]);
      tension.pairs.push({ a, b, sentences: ss.length, pages: [pageOfS(ss[0]), pageOfS(ss[ss.length - 1])], ...t, trend: d > 6 ? "escalates" : d < -6 ? "eases" : "steady", peak: peakOf(ss), bond: t.tension >= 45 && t.valence <= -5 ? "hostile" : t.tension >= 40 ? "strained" : t.valence >= 5 ? "warm" : "calm" });
    }
    tension.pairs.sort((x, y) => y.sentences - x.sentences);
    tension.pairs = tension.pairs.slice(0, 80);
  }
  {
    const perPage = /* @__PURE__ */ new Map();
    for (let si = 0; si < nS; si++) {
      if (sW[si] < 3) continue;
      const pg = pageOfS(si), c = perPage.get(pg) ?? { s: 0, n: 0 };
      c.s += sTen[si];
      c.n++;
      perPage.set(pg, c);
    }
    const pgs = [...perPage.keys()].sort((a, b) => a - b), raw2 = pgs.map((pg) => perPage.get(pg).s / perPage.get(pg).n), sm = raw2.map((_, i) => ((raw2[i - 1] ?? raw2[i]) + raw2[i] + (raw2[i + 1] ?? raw2[i])) / 3);
    pgs.forEach((pg, i) => tension.curve.push({ page: pg, tension: Math.round(((raw2[i - 1] ?? raw2[i]) + raw2[i] + (raw2[i + 1] ?? raw2[i])) / 3) }));
    const mu = sm.reduce((a, b) => a + b, 0) / (sm.length || 1), sdv = Math.sqrt(sm.reduce((a, b) => a + (b - mu) ** 2, 0) / (sm.length || 1)) || 1;
    tension.peaks = pgs.filter((_, i) => i > 0 && i < sm.length - 1 && sm[i] >= sm[i - 1] && sm[i] >= sm[i + 1] && sm[i] > mu + sdv).sort((a, b) => sm[pgs.indexOf(b)] - sm[pgs.indexOf(a)]).slice(0, 6).sort((a, b) => a - b);
    const chT = chapters.map((c) => {
      const v = tension.curve.filter((x) => x.page >= c.pages[0] && x.page <= c.pages[1]).map((x) => x.tension);
      return v.length ? v.reduce((a, b) => a + b, 0) / v.length : 0;
    });
    const srt = [...chT].sort((a, b) => a - b);
    chapters.forEach((c, i) => {
      c.tension = chT.length > 1 ? Math.round(srt.filter((x) => x < chT[i]).length / (srt.length - 1) * 100) : 50;
      tension.chapters.push({ chapter: c.index, tension: c.tension });
    });
  }
  lap("LAYERS");
  const map4d = { layers: [], interactions: [], trajectories: [] };
  {
    const cells = /* @__PURE__ */ new Map();
    const rootSet = new Map(themeForest.map((t) => [t.root.toLowerCase(), t])), inter = /* @__PURE__ */ new Map();
    const kindOfName = new Map(nodeList2.map((e) => [e.name, e.kind]));
    const placeAtPage = (name, pg) => routes.find((r) => r.name === name)?.legs.find((l) => pg >= l.pages[0] && pg <= l.pages[1])?.place ?? null;
    for (let si = 0; si < sentRows.length; si++) {
      const names = (entSentE.get(si) ?? []).filter((n) => kindOfName.has(n));
      if (!names.length) continue;
      const r = sentRows[si], pg = page(r.s);
      const els = /* @__PURE__ */ new Set();
      for (let j = r.s; j <= r.e; j++) {
        const t = rootSet.get(toks[j].w.toLowerCase());
        if (t && !titleTok[j]) els.add(t.root.toLowerCase());
      }
      const ws = /* @__PURE__ */ new Set();
      for (let j = r.s; j <= r.e; j++) {
        const w = toks[j].w.toLowerCase();
        if (!titleTok[j] && wl(w) >= 3 && !stopSet.has(w) && !/\d/.test(w) && !charNameWords.has(w) && !kindOfName.has(toks[j].w)) ws.add(w);
      }
      const around = [...ws].sort((x, y) => idf(y) - idf(x)).slice(0, 5);
      const row = cells.get(pg) ?? cells.set(pg, /* @__PURE__ */ new Map()).get(pg);
      for (const nm of names) {
        const c = row.get(nm) ?? row.set(nm, { n: 0, with: /* @__PURE__ */ new Map(), around: /* @__PURE__ */ new Map(), elements: /* @__PURE__ */ new Map(), v: 0, t: 0 }).get(nm);
        c.n++;
        c.v += sVal[si];
        c.t += sTen[si];
        for (const o of names) if (o !== nm) c.with.set(o, (c.with.get(o) ?? 0) + 1);
        for (const w of around) c.around.set(w, (c.around.get(w) ?? 0) + 1);
        for (const el of els) if (el !== nm.toLowerCase()) {
          c.elements.set(el, (c.elements.get(el) ?? 0) + 1);
          const key2 = nm + "\0" + el;
          const it = inter.get(key2) ?? inter.set(key2, { sent: 0, pages: /* @__PURE__ */ new Set(), t: rootSet.get(el) }).get(key2);
          it.sent++;
          it.pages.add(pg);
        }
      }
    }
    const top = (m, k) => [...m].sort((a, b) => b[1] - a[1]).slice(0, k).map((x) => x[0]);
    for (const pg of [...cells.keys()].sort((a, b) => a - b)) {
      const row = cells.get(pg);
      map4d.layers.push({ page: pg, chapter: chapterOfPage(pg) + 1, nodes: [...row].sort((a, b) => b[1].n - a[1].n).slice(0, 10).map(([name, c]) => ({ name, kind: kindOfName.get(name), n: c.n, place: placeAtPage(name, pg), with: top(c.with, 4), around: top(c.around, 5), elements: top(c.elements, 4), tone: { valence: Math.round(c.v / c.n * 100), tension: Math.round(c.t / c.n) } })) });
    }
    const perNode = /* @__PURE__ */ new Map();
    for (const [pg, row] of cells) for (const [nm, c] of row) (perNode.get(nm) ?? perNode.set(nm, []).get(nm)).push({ pg, c });
    for (const [nm, list] of perNode) {
      list.sort((a, b) => a.pg - b.pg);
      if (list.length < 2) continue;
      const runs = [];
      for (const x of list) {
        const l = runs[runs.length - 1];
        if (l && x.pg - l.to <= 1) l.to = x.pg;
        else runs.push({ from: x.pg, to: x.pg, place: placeAtPage(nm, x.pg) });
      }
      let el = 0, ne = 0;
      for (let i = 1; i < list.length; i++) {
        const A = /* @__PURE__ */ new Set([...list[i - 1].c.with.keys(), ...list[i - 1].c.elements.keys()]), B = /* @__PURE__ */ new Set([...list[i].c.with.keys(), ...list[i].c.elements.keys()]);
        const u = /* @__PURE__ */ new Set([...A, ...B]);
        if (!u.size) continue;
        let sh = 0;
        for (const w of A) if (B.has(w)) sh++;
        el += 1 - sh / u.size;
        ne++;
      }
      const wm = /* @__PURE__ */ new Map();
      for (const x of list) for (const o of x.c.with.keys()) wm.set(o, (wm.get(o) ?? 0) + 1);
      map4d.trajectories.push({ node: nm, kind: kindOfName.get(nm), layers: list.length, first: list[0].pg, last: list[list.length - 1].pg, runs: runs.slice(0, 40), elasticity: ne ? round2(el / ne) : 0, mostWith: [...wm].sort((a, b) => b[1] - a[1]).slice(0, 5).map(([name, layers]) => ({ name, layers })) });
    }
    map4d.trajectories.sort((a, b) => b.layers - a.layers);
    const byNode = /* @__PURE__ */ new Map();
    for (const [key2, v] of inter) {
      const [node, element] = key2.split("\0");
      const pgs = [...v.pages].sort((a, b) => a - b);
      (byNode.get(node) ?? byNode.set(node, []).get(node)).push({ node, element, class: v.t.class, sentences: v.sent, pages: pgs.slice(0, 12), first: pgs[0], last: pgs[pgs.length - 1] });
    }
    for (const list of byNode.values()) map4d.interactions.push(...list.sort((a, b) => b.sentences - a.sentences).slice(0, 8));
  }
  lap("MORPHISMS");
  const parallels = [];
  {
    const sks = [];
    for (let ci = 0; ci < nCh; ci++) {
      const cnt = /* @__PURE__ */ new Map();
      for (const si of chSents[ci]) for (const n of entSentE.get(si) ?? []) cnt.set(n, (cnt.get(n) ?? 0) + 1);
      const nodes = [...cnt].sort((a, b) => b[1] - a[1]).slice(0, 5).map((x) => x[0]);
      if (nodes.length < 3) continue;
      const W = nodes.map(() => nodes.map(() => 0));
      for (const si of chSents[ci]) {
        const here = /* @__PURE__ */ new Set([...entSentE.get(si) ?? [], ...entSentE.get(si + 1) ?? []]);
        for (let a = 0; a < nodes.length; a++) for (let b = a + 1; b < nodes.length; b++) if (here.has(nodes[a]) && here.has(nodes[b])) {
          W[a][b]++;
          W[b][a]++;
        }
      }
      let mx = 0;
      for (const row of W) for (const v of row) mx = Math.max(mx, v);
      if (!mx) continue;
      for (const row of W) for (let q2 = 0; q2 < row.length; q2++) row[q2] = row[q2] / mx;
      if (W.flat().filter((v) => v > 0).length < 4) continue;
      sks.push({ chapter: ci, title: chapters[ci].title, nodes, W });
    }
    const perms = (n) => {
      if (n <= 1) return [[0]];
      const out = [];
      const rec = (cur, rest) => {
        if (!rest.length) {
          out.push(cur);
          return;
        }
        for (let i = 0; i < rest.length; i++) rec([...cur, rest[i]], rest.filter((_, j) => j !== i));
      };
      rec([], Array.from({ length: n }, (_, i) => i));
      return out;
    };
    const permCache = /* @__PURE__ */ new Map();
    for (let i = 0; i < sks.length; i++) for (let j = i + 1; j < sks.length; j++) {
      const A = sks[i], B = sks[j], m = Math.min(A.nodes.length, B.nodes.length);
      if (m < 3) continue;
      const ps = permCache.get(m) ?? permCache.set(m, perms(m)).get(m);
      let best2 = -1, bestMap = [];
      for (const p of ps) {
        if (p.some((q2, a) => placeNameSet.has(A.nodes[a]) !== placeNameSet.has(B.nodes[q2]))) continue;
        let diff = 0, tot = 0;
        for (let a = 0; a < m; a++) for (let b = a + 1; b < m; b++) {
          const x = A.W[a][b], y = B.W[p[a]][p[b]];
          diff += Math.abs(x - y);
          tot += Math.max(x, y);
        }
        const sim = tot ? 1 - diff / tot : 0;
        if (sim > best2) {
          best2 = sim;
          bestMap = p;
        }
      }
      const sa = new Set(A.nodes), sb = new Set(B.nodes);
      let inter = 0;
      for (const n of sa) if (sb.has(n)) inter++;
      const overlap = inter / (sa.size + sb.size - inter);
      if (best2 >= 0.8 && Math.abs(j - i) >= 2) parallels.push({ a: { chapter: A.chapter + 1, title: A.title }, b: { chapter: B.chapter + 1, title: B.title }, similarity: round2(best2), castOverlap: round2(overlap), mapping: bestMap.map((q2, a) => [A.nodes[a], B.nodes[q2]]), kind: overlap <= 0.34 ? "hidden parallel" : "echo" });
    }
    parallels.sort((x, y) => y.similarity * (y.kind === "hidden parallel" ? 1.2 : 1) * (1 - y.castOverlap * 0.3) - x.similarity * (x.kind === "hidden parallel" ? 1.2 : 1) * (1 - x.castOverlap * 0.3));
  }
  const canonOf = /* @__PURE__ */ new Map();
  for (const c of equivalence) for (const mem of c.members) canonOf.set(mem, c.representative);
  const canon = (n) => canonOf.get(n) ?? n;
  const learnedForms = [];
  const learnedEdges = [];
  {
    const castNames = new Set(castEnts.map((e) => e.name));
    const grams = /* @__PURE__ */ new Map();
    const base = /* @__PURE__ */ new Map();
    const narr = /* @__PURE__ */ new Map();
    const edged = /* @__PURE__ */ new Map();
    const tagCount = /* @__PURE__ */ new Map();
    let dlg = 0;
    const cut = /[,;:¡!¿?—–"«»“”()]/;
    const isNameWord = (w) => charNameWords.has(w);
    for (let si = 0; si < sentRows.length; si++) {
      const r = sentRows[si];
      let sp = 0, len = 0;
      for (let j = r.s; j <= r.e; j++) {
        len++;
        if (tmode[j] === 1) sp++;
      }
      if (!len) continue;
      const spoken = sp >= 3 || sp / len >= 0.3;
      let speaker = null;
      if (spoken) {
        let lastSp = -1;
        for (let j = r.e; j >= r.s; j--) if (tmode[j] === 1) {
          lastSp = j;
          break;
        }
        for (let j = lastSp + 1; j <= r.e && speaker === null; j++) {
          const c = claimed.get(j);
          if (c && castNames.has(c)) speaker = c;
        }
      }
      const names = spoken ? [...new Set([-3, -2, -1, 0, 1, 2, 3].flatMap((d) => entSentE.get(si + d) ?? []))].filter((n) => castNames.has(n) && n !== speaker) : [];
      if (spoken) {
        let fs = -1, ls = -1;
        for (let j = r.s; j <= r.e; j++) if (tmode[j] === 1) {
          if (fs < 0) fs = j;
          ls = j;
        }
        for (const j of [fs - 1, ls + 1]) if (j >= r.s && j <= r.e && tmode[j] !== 1 && !claimed.has(j)) {
          const w = toks[j].w.toLowerCase();
          tagCount.set(w, (tagCount.get(w) ?? 0) + 1);
        }
      }
      if (spoken) {
        dlg++;
        for (const n of names) base.set(n, (base.get(n) ?? 0) + 1);
      }
      const ws = [];
      for (let j = r.s; j <= r.e; j++) ws.push(toks[j].w.toLowerCase());
      const seen = /* @__PURE__ */ new Set();
      for (let n = 2; n <= 3; n++) for (let q2 = 0; q2 + n <= ws.length; q2++) {
        const g = ws.slice(q2, q2 + n);
        if (g.some(isNameWord) || g.some((w) => /\d/.test(w)) || g.every((w) => stopSet.has(w) || wl(w) < 3)) continue;
        const key2 = g.join(" ");
        if (seen.has(key2)) continue;
        seen.add(key2);
        let inside = true;
        for (let t = 0; t < n; t++) if (tmode[r.s + q2 + t] !== 1) {
          inside = false;
          break;
        }
        if (!spoken || !inside) {
          narr.set(key2, (narr.get(key2) ?? 0) + 1);
          continue;
        }
        const a = r.s + q2, b = a + n - 1;
        if (a > 0 && cut.test(raw.slice(toks[a - 1].end, toks[a].idx)) || b + 1 < toks.length && cut.test(raw.slice(toks[b].end, toks[b + 1].idx))) edged.set(key2, (edged.get(key2) ?? 0) + 1);
        (grams.get(key2) ?? grams.set(key2, []).get(key2)).push({ names, speaker });
      }
    }
    const minN = Math.max(5, Math.round(dlg / 500));
    const cands = [];
    for (const [form, occ] of grams) {
      if (occ.length < minN || occ.length < 0.8 * (occ.length + (narr.get(form) ?? 0))) continue;
      if ((edged.get(form) ?? 0) < 0.6 * occ.length || form.split(" ").some((w) => !stopSet.has(w) && (tagCount.get(w) ?? 0) >= Math.max(8, dlg / 200))) continue;
      const presence = /* @__PURE__ */ new Map();
      for (const o of occ) for (const nm of o.names) presence.set(nm, (presence.get(nm) ?? 0) + 1);
      const top = [...presence].sort((a, b) => b[1] - a[1])[0];
      if (!top) continue;
      const pA = top[1] / occ.length, baseA = (base.get(top[0]) ?? 0) / Math.max(1, dlg), lift = baseA > 0 ? pA / baseA : 0;
      const others = /* @__PURE__ */ new Set();
      for (const o of occ) {
        if (o.speaker && o.speaker !== top[0]) others.add(o.speaker);
        for (const nm of o.names) if (nm !== top[0]) others.add(nm);
      }
      const z = baseA > 0 && baseA < 0.99 ? (pA - baseA) / Math.sqrt(baseA * (1 - baseA) / occ.length) : baseA >= 0.99 && occ.length >= 12 ? 99 : 0;
      if (z >= 1.5 && pA >= 0.4 && (others.size >= 2 || occ.length >= 12)) cands.push({ form, toward: top[0], n: occ.length, lift: z, occ });
    }
    cands.sort((a, b) => b.n * b.lift - a.n * a.lift);
    const chosen = [];
    for (const c of cands) {
      if (chosen.length >= 12) break;
      if (chosen.some((x) => x.toward === c.toward && (x.form.includes(c.form) || c.form.includes(x.form)))) continue;
      chosen.push(c);
    }
    for (const c of chosen) {
      const speakers = /* @__PURE__ */ new Map();
      for (const o of c.occ) {
        const others = o.speaker && o.speaker !== c.toward ? [o.speaker] : o.names.filter((nm) => nm !== c.toward);
        for (const x of others) {
          speakers.set(x, (speakers.get(x) ?? 0) + 1 / others.length);
          learnedEdges.push({ from: x, to: c.toward, w: 1 / others.length });
        }
      }
      learnedForms.push({ form: c.form, toward: c.toward, times: c.n, speakers: [...speakers].sort((a, b) => b[1] - a[1]).slice(0, 5).map((x) => x[0]) });
    }
  }
  const defer = /* @__PURE__ */ new Map();
  for (const e of learnedEdges) {
    const f = canon(e.from), t = canon(e.to);
    if (f !== t) defer.set(`${f}>${t}`, (defer.get(`${f}>${t}`) ?? 0) + e.w);
  }
  for (const a of address) {
    const ref = a.to[0];
    if (!ref || ref.score <= 0) continue;
    const refN = canon(ref.node);
    const ci = chapterOfPage(a.page);
    if (ci < 0 || ci >= nCh) continue;
    const seg = chapters[ci].events.find((ev) => a.page >= ev.pages[0] && a.page <= ev.pages[1] && ev.actors.some((x) => canon(x) !== refN));
    const speaker = a.speaker ? canon(a.speaker) : seg?.actors.map(canon).find((x) => x !== refN);
    if (!speaker || speaker === refN) continue;
    const key2 = `${speaker}>${refN}`;
    defer.set(key2, (defer.get(key2) ?? 0) + 1);
  }
  const prec = /* @__PURE__ */ new Map();
  {
    const firstIn = /* @__PURE__ */ new Map();
    for (const e of castEnts) for (const o of e.occ) {
      const si = sentOf[o.k];
      if (si < 0) continue;
      const m = firstIn.get(si) ?? firstIn.set(si, /* @__PURE__ */ new Map()).get(si);
      const had = m.get(e.name);
      if (had === void 0 || o.k < had) m.set(e.name, o.k);
    }
    for (const m of firstIn.values()) {
      const names = [...m].sort((a, b) => a[1] - b[1]).map((x) => x[0]);
      for (let a = 0; a < names.length; a++) for (let b = a + 1; b < names.length; b++) {
        const k = `${names[a]}>${names[b]}`;
        prec.set(k, (prec.get(k) ?? 0) + 1);
      }
    }
  }
  const deferTo = /* @__PURE__ */ new Map(), deferFrom = /* @__PURE__ */ new Map(), precAsym = /* @__PURE__ */ new Map();
  for (const [k, n] of defer) {
    const [f, t] = k.split(">");
    deferTo.set(t, (deferTo.get(t) ?? 0) + n);
    deferFrom.set(f, (deferFrom.get(f) ?? 0) + n);
  }
  for (const [k, n] of prec) {
    const [a, b] = k.split(">");
    const back = prec.get(`${b}>${a}`) ?? 0;
    if (n + back >= 4) precAsym.set(a, (precAsym.get(a) ?? 0) + (n - back) / (n + back) / 2);
  }
  const above = /* @__PURE__ */ new Map(), notes = /* @__PURE__ */ new Map();
  {
    const names = /* @__PURE__ */ new Set();
    for (const k of defer.keys()) {
      const [f, t] = k.split(">");
      names.add(f);
      names.add(t);
    }
    const list = [...names];
    for (let i = 0; i < list.length; i++) for (let j = i + 1; j < list.length; j++) {
      const A = list[i], B = list[j], ab = defer.get(`${A}>${B}`) ?? 0, ba = defer.get(`${B}>${A}`) ?? 0, tot = ab + ba;
      if (tot < 2) continue;
      const asym = (ba - ab) / tot, w = Math.log(1 + tot);
      above.set(A, (above.get(A) ?? 0) + asym * w);
      above.set(B, (above.get(B) ?? 0) - asym * w);
      if (asym !== 0) {
        const hi = asym > 0 ? A : B, lo = asym > 0 ? B : A;
        (notes.get(hi) ?? notes.set(hi, []).get(hi)).push(`above ${lo} (${Math.max(ab, ba)}:${Math.min(ab, ba)})`);
      }
    }
  }
  const rankChars = castEnts.map((e) => {
    const sc = above.get(e.name) ?? 0, pa = precAsym.get(e.name) ?? 0, dt = deferTo.get(e.name) ?? 0;
    const score = sc + 0.8 * pa;
    const evidence = [...(notes.get(e.name) ?? []).slice(0, 3)];
    if (dt) evidence.push(`addressed with deference \xD7${dt}`);
    if (Math.abs(pa) >= 0.3) evidence.push(`${pa > 0 ? "named before" : "named after"} the others it shares sentences with`);
    return { node: e.name, kind: "character", score: round2(score), evidence };
  }).sort((a, b) => b.score - a.score);
  const topScore = Math.max(0, ...rankChars.map((r) => r.score));
  const characters = rankChars.slice(0, 30).map((r) => ({ ...r, level: r.score > 0 && r.score >= topScore * 0.6 ? 0 : r.score > 0 ? 1 : 2 }));
  const levelOf = (i, n) => i < n * 0.2 ? 0 : i < n * 0.5 ? 1 : 2;
  const placeRank = placeCasts.map((pc) => ({ node: pc.place, kind: "place", score: round2(pc.mentions * Math.log(1 + pc.cast.length)), evidence: [`${pc.mentions} character mentions`, `${pc.cast.length} characters`] })).sort((a, b) => b.score - a.score);
  const placeRanks = placeRank.map((r, i, a) => ({ ...r, level: levelOf(i, a.length) }));
  const containment = routePairs.filter((p) => p.kind === "node-node" && p.relation === "contained" && placeNameSet.has(p.a) && placeNameSet.has(p.b)).map((p) => {
    const ta = trackOf.get(p.a), tb = trackOf.get(p.b), big = ta.mentions >= tb.mentions ? ta : tb, small = big === ta ? tb : ta;
    return { outer: big.name, inner: small.name, share: round2(p.together / Math.max(1, small.present.filter(Boolean).length)) };
  });
  const ownership = affinity.flatMap((a) => a.elements.filter((x) => x.exclusivity >= 0.6 && x.lift >= 3 && x.count >= 3).map((x) => ({ element: x.word, owner: a.node, exclusivity: x.exclusivity, lift: x.lift }))).sort((a, b) => b.exclusivity - a.exclusivity || b.lift - a.lift).filter((x, i, arr) => arr.findIndex((y) => y.element === x.element) === i).slice(0, 40);
  const hierarchy = { forms: learnedForms, deference: [...defer].map(([k, times]) => {
    const [from, to] = k.split(">");
    return { from, to, times };
  }).sort((a, b) => b.times - a.times).slice(0, 20), characters, places: placeRanks, containment, ownership };
  const thematic = [];
  for (const t of themeForest) {
    if (t.branches.length < 2 || t.chapters.length < 4) continue;
    const words = [t.root, ...t.branches.map((b) => b.word)], ids = words.map((w) => elIdx.get(w)).filter((x) => x !== void 0);
    if (ids.length < 3) continue;
    const mid = t.chapters[Math.floor(t.chapters.length / 2)];
    const co2 = (inHalf) => {
      const m = /* @__PURE__ */ new Map();
      for (let ci = 0; ci < nCh; ci++) {
        if (!inHalf(ci + 1)) continue;
        for (const si of chSents[ci]) {
          const here = (perSent.get(si) ?? []).filter((x) => ids.includes(x));
          for (let a = 0; a < here.length; a++) for (let b = a + 1; b < here.length; b++) {
            const k = here[a] < here[b] ? `${here[a]}|${here[b]}` : `${here[b]}|${here[a]}`;
            m.set(k, (m.get(k) ?? 0) + 1);
          }
        }
      }
      return m;
    };
    const E = co2((c) => c <= mid), Lt = co2((c) => c > mid);
    const keys = /* @__PURE__ */ new Set([...E.keys(), ...Lt.keys()]);
    if (keys.size < 2) continue;
    const sumE = [...E.values()].reduce((a, b) => a + b, 0) || 1, sumL = [...Lt.values()].reduce((a, b) => a + b, 0) || 1;
    let mn = 0, mxv = 0;
    const kept = [], broken = [];
    for (const k of keys) {
      const x = (E.get(k) ?? 0) / sumE, y = (Lt.get(k) ?? 0) / sumL;
      mn += Math.min(x, y);
      mxv += Math.max(x, y);
      const [a, b] = k.split("|").map(Number);
      const pair = `${elCand[a].w}~${elCand[b].w}`;
      if (x > 0 && y > 0) kept.push(pair);
      else broken.push(pair);
    }
    const pres = mxv ? mn / mxv : 0;
    thematic.push({ root: t.root, early: [t.chapters[0], mid], late: [mid + 1, t.chapters[t.chapters.length - 1]], preservation: round2(pres), kept: kept.slice(0, 5), broken: broken.slice(0, 5), verdict: pres >= 0.35 ? "coherent" : "shifts" });
  }
  thematic.sort((a, b) => b.preservation - a.preservation);
  const morphisms = { parallels: parallels.slice(0, 12), hierarchy, thematic };
  lap("DOSSIERS");
  const lineAt = (k0) => {
    const si = sentOf[k0];
    if (si < 0) return "";
    const r = sentRows[si];
    return raw.slice(toks[r.s].idx, toks[r.e].end).replace(/[¶\f]/g, " ").replace(/\s+/g, " ").trim().slice(0, 220);
  };
  const dossiers = [];
  {
    const roots = forest.map((f) => f.root);
    const pool = nodeList2.filter((e) => e.kind === "character" || e.kind === "place");
    const knee = (kind) => {
      const list = pool.filter((e) => e.kind === kind).sort((x, y) => y.occ.length - x.occ.length), tot = list.reduce((a, e) => a + e.occ.length, 0);
      let acc = 0;
      const keep = [];
      for (const e of list) {
        if (acc >= 0.8 * tot && keep.length >= 3) break;
        if (e.occ.length < 4) break;
        keep.push(e.name);
        acc += e.occ.length;
      }
      return keep;
    };
    const chosen = [.../* @__PURE__ */ new Set([...roots, ...knee("character"), ...knee("place")])].map((n) => pool.find((e) => e.name === n)).filter((e) => !!e);
    const momentOf = (ci, ev) => ({ chapter: ci + 1, title: chapters[ci].title, pages: ev.pages, actors: ev.actors, place: ev.place, words: ev.words, charge: ev.charge });
    for (const e of chosen) {
      const occs = [...e.occ].sort((a, b) => a.k - b.k), pg = occs.map((o) => o.pg);
      const chs = [...new Set(occs.map((o) => chapterOfPage(o.pg)))].sort((a, b) => a - b);
      const f = forest.find((x) => x.root === e.name), aff = affinity.find((a) => a.node === e.name), cir = circles.find((c) => c.node === e.name);
      const arc = arcs.find((a) => a.node === e.name) ?? null, rt = routes.find((r) => r.name === e.name);
      const relations = routePairs.filter((p) => p.kind === "node-node" && (p.a === e.name || p.b === e.name)).sort((a, b) => rank(b) - rank(a)).slice(0, 6).map((p) => {
        const w = p.a === e.name ? p.b : p.a, pt = tension.pairs.find((x) => x.a === e.name && x.b === w || x.b === e.name && x.a === w);
        return { with: w, relation: p.relation, together: p.together, encounters: p.encounters.length, closest: p.closest ? p.closest.pages : null, trend: p.trend, sharedPlaces: p.sharedPlaces, tone: pt ? { valence: pt.valence, tension: pt.tension, bond: pt.bond, trend: pt.trend, peak: pt.peak } : null };
      });
      const scenes = [];
      chapters.forEach((c, ci) => c.events.forEach((ev) => {
        if (ev.actors.includes(e.name) || ev.place === e.name) scenes.push(momentOf(ci, ev));
      }));
      const keyMoments = [...scenes].sort((a, b) => Math.abs(b.charge) + 0.4 * b.words.length - (Math.abs(a.charge) + 0.4 * a.words.length)).slice(0, 5).sort((a, b) => a.pages[0] - b.pages[0]);
      const hot = [...new Set(scenes.map((m) => m.chapter))].sort((a, b) => chapters[b - 1].tone.arousal - chapters[a - 1].tone.arousal)[0];
      const climax = hot !== void 0 ? scenes.filter((m) => m.chapter === hot).sort((a, b) => Math.abs(b.charge) - Math.abs(a.charge))[0] ?? null : null;
      const n = nodeList.find((x) => x.name === e.name);
      const dos = {
        name: e.name,
        kind: e.kind === "place" ? "place" : "character",
        aliases: [...new Set(e.aliases)],
        rank: f?.rank ?? (chs.length >= nCh * 0.4 ? "primary" : "secondary"),
        presence: { mentions: occs.length, first: Math.min(...pg), last: Math.max(...pg), chapters: chs.map((c) => c + 1), share: round2(chs.length / Math.max(1, nCh)), density: density(e.occ) },
        voice: n?.voice ?? voiceOf(e),
        introduced: (() => {
          const o = occs.find((x) => lineAt(x.k)) ?? occs[0];
          return { page: o.pg, chapter: chapterOfPage(o.pg) + 1, line: lineAt(o.k) };
        })(),
        lastSeen: (() => {
          const o = [...occs].reverse().find((x) => lineAt(x.k)) ?? occs[occs.length - 1];
          return { page: o.pg, chapter: chapterOfPage(o.pg) + 1, line: lineAt(o.k) };
        })(),
        route: rt?.legs ?? [],
        home: (() => {
          const m = atPlace.get(e.name);
          if (!m) return null;
          const b = [...m].sort((x, y) => y[1] - x[1])[0];
          return b && homeOf(e.name, b[0]) >= 0.3 ? b[0] : null;
        })(),
        places: [...atPlace.get(e.name) ?? []].sort((x, y) => y[1] - x[1]).slice(0, 4).map(([pl]) => {
          const pc = placeCasts.find((c) => c.place === pl);
          return { place: pl, home: round2(homeOf(e.name, pl)), weight: pc?.cast.find((c) => c.name === e.name)?.weight ?? 0, role: roleOf(homeOf(e.name, pl)) };
        }),
        circle: { inner: cir?.inner ?? [], outer: cir?.outer ?? [], proper: cir?.proper ?? [] },
        traits: { elements: (aff?.elements ?? []).slice(0, 8).map((x) => x.word), actions: (aff?.actions ?? []).slice(0, 5).map((x) => x.word) },
        relations,
        tone: tension.nodes.find((x) => x.node === e.name) ?? null,
        generates: f?.generates ?? [],
        standing: (() => {
          const r = hierarchy.characters.find((x) => x.node === e.name);
          return r ? { level: r.level, score: r.score, evidence: r.evidence } : null;
        })(),
        owns: hierarchy.ownership.filter((o) => o.owner === e.name).map((o) => o.element).slice(0, 8),
        arc,
        keyMoments,
        climax,
        parallels: morphisms.parallels.filter((pp) => pp.mapping.some(([x, y]) => x === e.name || y === e.name)).slice(0, 4).map((pp) => ({ chapters: [pp.a.chapter, pp.b.chapter], kind: pp.kind, similarity: pp.similarity, becomes: pp.mapping.find(([x]) => x === e.name)?.[1] ?? pp.mapping.find(([, y]) => y === e.name)?.[0] ?? null })),
        themes: themeForest.filter((t) => t.chapters.filter((c) => chs.includes(c - 1)).length >= Math.max(1, chs.length / 3)).sort((a, b) => b.share - a.share).slice(0, 6).map((t) => ({ root: t.root, flow: t.flow, share: t.share })),
        sections: []
      };
      dos.sections = buildSections(dos);
      dossiers.push(dos);
    }
  }
  const injectivity = { entities: entityCount, mentions: claimed.size, collisions, keptApart: keptApart.sort((a, b) => b.similarity - a.similarity).slice(0, 8), refused: injRefused };
  const result = {
    reportPlan: void 0,
    completion: void 0,
    restructure: void 0,
    timings: {},
    map4d,
    tension,
    injectivity,
    routes,
    routePairs,
    placeCasts,
    affinity,
    circles,
    arcs,
    worldIdentity,
    morphisms,
    dossiers,
    language: lang,
    words: toks.length,
    layers: NP,
    pageMode: realPages ? "real-pages" : "words-per-page",
    elapsedMs: Date.now() - t0,
    catalogued: occL.size,
    locations: slugs.map((s) => ({ heading: `${s.ie} ${s.place}`, place: s.place, time: s.time, scene: s.id })),
    structuralWords,
    notNames,
    wordIndex,
    equivalenceClasses: equivalence,
    fields: semFields.map((f, i) => ({ id: f.id, label: f.label, size: f.members.length, valence: round2(fieldValence[i]) })),
    structure,
    sentences,
    forest,
    treeRelations: treeRelations.slice(0, 20),
    chapters,
    themeForest,
    themeRelations: themeRelations.slice(0, 20),
    knots,
    paratext,
    nodes: nodeList,
    wordNodes,
    places,
    links: links.slice(0, 60),
    fusions: fusions.slice(0, 60),
    address,
    timeAxis: { months: monthEvents, yearFirstPage }
  };
  lap("end");
  result.timings = timings;
  if (opts.keepPages) {
    const first = new Array(NP + 2).fill(-1);
    for (let k = 0; k < toks.length; k++) {
      const pg = page(k);
      if (first[pg] < 0) first[pg] = toks[k].idx;
    }
    result.pageText = Array.from({ length: NP }, (_, i) => {
      const a = first[i + 1] < 0 ? raw.length : first[i + 1];
      let b = raw.length;
      for (let q2 = i + 2; q2 <= NP; q2++) if (first[q2] >= 0) {
        b = first[q2];
        break;
      }
      return raw.slice(a, Math.max(a, b)).replace(/ ¶ /g, "\n").replace(/[¶\f]/g, " ").replace(/ +/g, " ").trim();
    });
  }
  result.reportPlan = buildReportPlan(result);
  result.completion = buildCompletionBrief(result);
  result.restructure = proposeRestructure(result);
  return result;
}

// src/lib/nodes/screenplay.ts
var TIMES = [
  [/\b(NOCHE|NIGHT|NACHT|NUIT)\b/i, "night"],
  [/\b(D[IÍ]A|DAY|TAG|JOUR|MA[ÑN]ANA|MORNING|TARDE|AFTERNOON|MEDIOD[IÍ]A|NOON)\b/i, "day"],
  [/\b(AMANECER|MADRUGADA|DAWN|SUNRISE|ALBA)\b/i, "dawn"],
  [/\b(ATARDECER|ANOCHECER|DUSK|SUNSET|EVENING|CREP[ÚU]SCULO)\b/i, "dusk"],
  [/\b(CONTINUO|CONTINUOUS|CONT'?D|SAME|MOMENTS? LATER|M[ÁA]S TARDE|LATER)\b/i, "continuous"]
];
var HEAD_RE = /^\s*(?:(\d+[A-Z]?)\s*[.\-–—)]?\s+)?(INT\.?\s*[\/\-]\s*EXT\.?|EXT\.?\s*[\/\-]\s*INT\.?|I\s*\/\s*E|INTERIOR\s*\/\s*EXTERIOR|INT|EXT|INTERIOR|EXTERIOR)\b\.?[\s.\-–—:]*(.*)$/i;
function parseHeading(line) {
  const raw = line.trim(), m = HEAD_RE.exec(raw);
  if (!m) return { raw, number: null, intExt: null, place: raw, subPlace: null, time: null, timeClass: null, flags: [] };
  const ie = m[2].toUpperCase().replace(/\s|\./g, ""), intExt = /\/|-|IE|I\/E/.test(ie) && /INT/.test(ie) && /EXT/.test(ie) || ie === "IE" ? "INT/EXT" : /^EXT/.test(ie) ? "EXT" : "INT";
  let rest = m[3].trim(), time = null, timeClass = null;
  const parts = rest.split(/\s*(?:[—–·|]|\s-\s|\s\/\s|\.\s+)\s*/).map((x) => x.trim().replace(/[.\s]+$/, "")).filter(Boolean);
  const kept = [];
  for (const p of parts) {
    const t = TIMES.find(([re]) => re.test(p));
    if (t && p.length <= 28 && !time) {
      time = p;
      timeClass = t[1];
    } else kept.push(p);
  }
  const flags = [];
  for (const f of ["FLASHBACK", "SUE[\xD1N]O", "DREAM", "MONTAGE", "MONTAJE", "CONTINUO", "CONTINUOUS"]) if (new RegExp(`\\b${f}\\b`, "i").test(rest)) flags.push(f.replace("[\xD1N]", "\xD1"));
  rest = kept.join(" \u2014 ");
  return { raw, number: m[1] ?? null, intExt, place: kept[0] ?? rest, subPlace: kept.length > 1 ? kept.slice(1).join(" \u2014 ") : null, time, timeClass, flags };
}
var LEX = [
  { kind: "shot", terms: ["EXTREME CLOSE-?UP", "EXTREME CLOSE UP", "CLOSE-?UP", "CLOSE UP", "CLOSE ON", "MEDIUM SHOT", "MEDIUM CLOSE", "WIDE SHOT", "WIDE ON", "ESTABLISHING SHOT", "ESTABLISHING", "TWO[- ]SHOT", "FULL SHOT", "LONG SHOT", "MASTER SHOT", "INSERT", "PRIMER PLANO", "PRIMER\xCDSIMO PRIMER PLANO", "PLANO DETALLE", "PLANO MEDIO", "PLANO GENERAL", "PLANO AMERICANO", "PLANO CONJUNTO", "PLANO ENTERO", "GRAN PLANO GENERAL", "PLANO SECUENCIA", "DETALLE", "INSERTO"] },
  { kind: "angle", terms: ["OVER THE SHOULDER", "OVER-THE-SHOULDER", "SOBRE EL HOMBRO", "POV", "P\\.O\\.V\\.", "PUNTO DE VISTA", "ANGLE ON", "\xC1NGULO", "LOW ANGLE", "HIGH ANGLE", "DUTCH ANGLE", "BIRD.?S EYE", "AERIAL", "PLANO ZENITAL", "PICADO", "CONTRAPICADO", "PLANO NADIR", "C\xC1MARA SUBJETIVA", "SUBJECTIVE"] },
  { kind: "movement", terms: ["PAN", "PANNING", "WHIP PAN", "PANOR\xC1MICA", "TILT UP", "TILT DOWN", "TILT", "ZOOM IN", "ZOOM OUT", "ZOOM", "DOLLY", "TRACKING", "TRAVELLING", "TRAVELING", "STEADICAM", "HANDHELD", "C\xC1MARA EN MANO", "CRANE", "GR\xDAA", "RACK FOCUS", "PULL BACK", "PUSH IN", "PUSHES IN", "C\xC1MARA LENTA", "SLOW MOTION", "TIME-?LAPSE", "FOLLOWS", "SIGUE A", "TRAVELLING DE"] },
  { kind: "transition", terms: ["CUT TO", "CORTE A", "SMASH CUT", "MATCH CUT", "JUMP CUT", "TIME CUT", "FADE IN", "FADE OUT", "FADE TO", "FUNDIDO A NEGRO", "FUNDIDO", "ENCADENADO", "DISSOLVE TO", "DISSOLVE", "WIPE TO", "IRIS", "INTERCUT", "SPLIT SCREEN", "FREEZE FRAME", "CONTINUOUS", "LATER", "M\xC1S TARDE"] },
  { kind: "sound", terms: ["V\\.?O\\.?", "O\\.?S\\.?", "O\\.?C\\.?", "VOZ EN OFF", "EN OFF", "OFF", "SFX", "FX", "SONIDO", "MUSIC", "M\xDASICA", "SCORE", "SOUND OF", "SILENCE", "SILENCIO", "SUPER", "TITLE", "T\xCDTULO", "SUBTITLES", "SUBT\xCDTULOS"], acronym: true },
  { kind: "effect", terms: ["FLASHBACK", "FLASH-?FORWARD", "MONTAGE", "MONTAJE", "SERIES OF SHOTS", "DREAM SEQUENCE", "SECUENCIA DE SUE\xD1O", "BLACK", "NEGRO", "FILTRO", "FILTER", "SPLIT", "DESENFOCADO", "OUT OF FOCUS"] }
];
var ACRONYMS = /* @__PURE__ */ new Set(["V.O", "VO", "O.S", "OS", "O.C", "OC", "FX", "POV", "SFX"]);
var lexRes = LEX.map((g) => ({ kind: g.kind, items: g.terms.map((t) => ({ label: t.replace(/\\\./g, ".").replace(/\.\?/g, "").replace(/[-.]?\?/g, " ").replace(/\\/g, ""), re: new RegExp(`(?<![\\p{L}\\p{N}])(${t})(?![\\p{L}\\p{N}])`, ACRONYMS.has(t.replace(/\\\.|\.\?/g, "").toUpperCase()) || t.length <= 3 ? "u" : "iu") })) }));
var wordsOf = (t) => (t.match(/[\p{L}\p{N}'’]+/gu) ?? []).length;
var EXT_RE = /\(\s*(V\.?O\.?|O\.?S\.?|O\.?C\.?|CONT'?D|CONT|OFF|SUPER|FILTRO|FILTER)[^)]*\)/i;
function analyzeScreenplay(text, opts = {}) {
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  const pageOfLine = [];
  {
    let p = 1;
    for (const l of lines) {
      p += (l.match(/\f/g) ?? []).length;
      pageOfLine.push(p);
    }
  }
  const hasFF = pageOfLine[pageOfLine.length - 1] > 1;
  const clean = lines.map((l) => l.replace(/\f/g, "").replace(/^(\s*\p{Lu}[\p{Lu}\p{N} .'’\-]*?\s*)\(\s*(v\.?o\.?|o\.?s\.?|o\.?c\.?|cont'?d?|off|super|filtro|filter)([^)]*)\)\s*$/iu, (_m, a, b, c) => `${a}(${String(b).toUpperCase()}${c})`));
  const els = parseScript(clean.join("\n"), isSlugline);
  const pageAt = (ln) => hasFF ? pageOfLine[ln] : Math.floor(ln / 55) + 1;
  const heads = els.filter((e) => e.type === "scene_heading");
  const scenes = [];
  const bounds = heads.map((h) => h.line);
  const termHits = /* @__PURE__ */ new Map();
  const hit = (term, kind, scene, sample) => {
    const k = kind + "|" + term.toUpperCase();
    const c = termHits.get(k) ?? { term: term.toUpperCase(), kind, count: 0, scenes: [], sample: sample.trim().slice(0, 120) };
    c.count++;
    if (!c.scenes.includes(scene)) c.scenes.push(scene);
    termHits.set(k, c);
  };
  const charMap = /* @__PURE__ */ new Map();
  const chr = (n) => charMap.get(n) ?? charMap.set(n, { name: n, cues: 0, dialogueLines: 0, words: 0, share: 0, parentheticals: [], extensions: {}, firstScene: 0, lastScene: 0, scenes: 0 }).get(n);
  const sceneSeen = /* @__PURE__ */ new Map();
  const transitionsAll = /* @__PURE__ */ new Map();
  const capsInAction = /* @__PURE__ */ new Map();
  const sliceFor = (si) => {
    const from = bounds[si], to = si + 1 < bounds.length ? bounds[si + 1] - 1 : lines.length - 1;
    return [from, to];
  };
  heads.forEach((h, si) => {
    const [from, to] = sliceFor(si), inScene = els.filter((e) => e.line >= from && e.line <= to);
    const sc = { index: si + 1, heading: parseHeading(h.text), lines: [from, to], pages: [pageAt(from), pageAt(to)], cast: [], actionBlocks: 0, dialogueLines: 0, parentheticals: 0, speechWords: 0, actionWords: 0, dialogueShare: 0, camera: [], transitions: [], tension: null };
    let prevAction = false;
    const cast = /* @__PURE__ */ new Set();
    for (const e of inScene) {
      if (e.type === "action") {
        if (!prevAction) sc.actionBlocks++;
        sc.actionWords += wordsOf(e.text);
      }
      if (e.type === "dialogue") {
        sc.dialogueLines++;
        const w = wordsOf(e.text);
        sc.speechWords += w;
        if (e.speaker) {
          const c = chr(e.speaker);
          c.dialogueLines++;
          c.words += w;
        }
      }
      if (e.type === "character" && e.speaker) {
        const base = e.speaker.replace(EXT_RE, "").trim(), c = chr(base);
        c.cues++;
        cast.add(base);
        const x = EXT_RE.exec(e.text);
        if (x) {
          const k = x[1].toUpperCase().replace(/\./g, "");
          c.extensions[k] = (c.extensions[k] ?? 0) + 1;
        }
        if (!(sceneSeen.get(base) ?? sceneSeen.set(base, /* @__PURE__ */ new Set()).get(base)).has(si + 1)) {
          sceneSeen.get(base).add(si + 1);
        }
      }
      if (e.type === "parenthetical") {
        sc.parentheticals++;
        if (e.speaker) chr(e.speaker.replace(EXT_RE, "").trim()).parentheticals.push({ text: e.text.replace(/^\(|\)$/g, "").trim(), scene: si + 1 });
      }
      if (e.type === "transition") sc.transitions.push(e.text);
      prevAction = e.type === "action";
      if (e.type !== "dialogue" && e.type !== "character" && e.type !== "scene_heading") {
        const found = [];
        for (const g of lexRes) for (const it of g.items) {
          const m = it.re.exec(e.text);
          if (m) found.push({ term: m[1], kind: g.kind, a: m.index + m[0].indexOf(m[1]), b: m.index + m[0].indexOf(m[1]) + m[1].length });
        }
        for (const f of found) if (!found.some((o) => o !== f && o.a <= f.a && o.b >= f.b && o.b - o.a > f.b - f.a)) {
          hit(f.term, f.kind, si + 1, e.text);
          if (!sc.camera.includes(f.term.toUpperCase())) sc.camera.push(f.term.toUpperCase());
        }
      }
      if (e.type === "action" || e.type === "insert") for (const m of e.text.matchAll(/(?<![\p{L}])(\p{Lu}[\p{Lu}'’-]{2,}(?:\s+\p{Lu}[\p{Lu}'’-]{2,}){0,3})(?![\p{L}])/gu)) {
        const t = m[1].trim();
        const c = capsInAction.get(t) ?? { n: 0, sample: e.text.trim().slice(0, 120) };
        c.n++;
        capsInAction.set(t, c);
      }
    }
    sc.cast = [...cast];
    sc.dialogueShare = sc.speechWords + sc.actionWords ? Math.round(sc.speechWords / (sc.speechWords + sc.actionWords) * 100) / 100 : 0;
    scenes.push(sc);
  });
  for (const e of els) if (e.type === "transition") {
    const k = e.text.toUpperCase().replace(/[:.]+$/, "");
    transitionsAll.set(k, (transitionsAll.get(k) ?? 0) + 1);
  }
  const totalWords = [...charMap.values()].reduce((a, c) => a + c.words, 0) || 1;
  for (const c of charMap.values()) {
    const sc = [...sceneSeen.get(c.name) ?? []].sort((a, b) => a - b);
    c.scenes = sc.length;
    c.firstScene = sc[0] ?? 0;
    c.lastScene = sc[sc.length - 1] ?? 0;
    c.share = Math.round(c.words / totalWords * 100) / 100;
  }
  const characters = [...charMap.values()].filter((c) => c.cues >= 1 && /\p{L}{2}/u.test(c.name)).sort((a, b) => b.words - a.words);
  const placeMap = /* @__PURE__ */ new Map();
  const timeOfDay = {};
  for (const sc of scenes) {
    const k = sc.heading.place.toUpperCase();
    const p = placeMap.get(k) ?? placeMap.set(k, { place: sc.heading.place, scenes: [], intExt: [], times: {}, subPlaces: [] }).get(k);
    p.scenes.push(sc.index);
    if (sc.heading.intExt && !p.intExt.includes(sc.heading.intExt)) p.intExt.push(sc.heading.intExt);
    if (sc.heading.timeClass) {
      p.times[sc.heading.timeClass] = (p.times[sc.heading.timeClass] ?? 0) + 1;
      timeOfDay[sc.heading.timeClass] = (timeOfDay[sc.heading.timeClass] ?? 0) + 1;
    }
    if (sc.heading.subPlace && !p.subPlaces.includes(sc.heading.subPlace)) p.subPlaces.push(sc.heading.subPlace);
  }
  const known = new Set([...termHits.values()].map((t) => t.term)), names = new Set(characters.map((c) => c.name.toUpperCase()));
  const learnedTerms = [...capsInAction].filter(([t, c]) => c.n >= 2 && !known.has(t) && !names.has(t) && !/^(INT|EXT|THE|AND|DE|LA|EL)$/.test(t) && !t.split(" ").every((w) => names.has(w))).sort((a, b) => b[1].n - a[1].n).slice(0, 20).map(([term, c]) => ({ term, count: c.n, sample: c.sample }));
  const engine = analyzeNodes(text, { language: opts.language });
  const NPe = Math.max(1, engine.layers), totalLines = Math.max(1, lines.length);
  for (const sc of scenes) {
    const a = Math.max(1, Math.min(NPe, Math.ceil(sc.lines[0] / totalLines * NPe))), b = Math.max(a, Math.min(NPe, Math.ceil(sc.lines[1] / totalLines * NPe))), v = engine.tension.curve.filter((x) => x.page >= a && x.page <= b).map((x) => x.tension);
    sc.tension = v.length ? Math.round(v.reduce((x, y) => x + y, 0) / v.length) : null;
  }
  const acts = [];
  {
    const tot = scenes.reduce((a, s) => a + (s.lines[1] - s.lines[0] + 1), 0) || 1;
    let acc = 0, start = 1;
    const cuts = [0.25, 0.5, 0.75, 1], names2 = ["I", "IIa", "IIb", "III"];
    scenes.forEach((s, i) => {
      acc += s.lines[1] - s.lines[0] + 1;
      const ci = acts.length;
      if (ci < 4 && (acc / tot >= cuts[ci] - 1e-9 || i === scenes.length - 1)) {
        const seg = scenes.slice(start - 1, i + 1), peak = seg.filter((x) => x.tension !== null).sort((a, b) => (b.tension ?? 0) - (a.tension ?? 0))[0];
        acts.push({ part: names2[ci], scenes: [start, i + 1], peakScene: peak?.index ?? null });
        start = i + 2;
      }
    });
  }
  const speech = scenes.reduce((a, s) => a + s.speechWords, 0), action = scenes.reduce((a, s) => a + s.actionWords, 0), pages = hasFF ? pageOfLine[pageOfLine.length - 1] : Math.max(1, Math.round(totalLines / 55));
  const classified = els.filter((e) => e.type !== "blank" && e.type !== "action").length / Math.max(1, els.filter((e) => e.type !== "blank").length);
  const confidence = Math.round(Math.min(1, (scenes.length >= 1 ? 0.5 : 0) + Math.min(0.3, characters.length * 0.05) + Math.min(0.2, classified)) * 100) / 100;
  return {
    isScreenplay: scenes.length >= 1 && characters.length >= 1,
    confidence,
    scenes,
    characters,
    places: [...placeMap.values()].sort((a, b) => b.scenes.length - a.scenes.length),
    timeOfDay,
    camera: [...termHits.values()].sort((a, b) => b.count - a.count),
    learnedTerms,
    transitions: [...transitionsAll].map(([text2, count]) => ({ text: text2, count })).sort((a, b) => b.count - a.count),
    stats: { pages, minutes: pages, scenes: scenes.length, dialogueShare: speech + action ? Math.round(speech / (speech + action) * 100) / 100 : 0, speakers: characters.length, avgSceneLines: scenes.length ? Math.round(scenes.reduce((a, s) => a + (s.lines[1] - s.lines[0] + 1), 0) / scenes.length) : 0 },
    acts,
    engine
  };
}

// src/lib/lenses/cinema/screenplay-rhythm.ts
var screenplay_rhythm_exports = {};
__export(screenplay_rhythm_exports, {
  novelDirectivesFor: () => novelDirectivesFor,
  pageBudget: () => pageBudget,
  parseScenes: () => parseScenes,
  rhythmBriefForBlock: () => rhythmBriefForBlock,
  targetWordsForScenes: () => targetWordsForScenes
});
var HEADING_RE = /^\s*(INT\.|EXT\.|INT\/EXT|EXT\/INT|ESC\.|ESCENA|SCENE)\b.*$/i;
var CUE_RE = /^\s*[A-ZÁÉÍÓÚÑ0-9][A-ZÁÉÍÓÚÑ0-9 .'()\-]{1,30}\s*$/;
var ALPHA = 14;
var BETA = 7;
var INTROSPECTION = 40;
function parseScenes(text) {
  const lines = text.split("\n");
  const scenes = [];
  let cur = null;
  for (const line of lines) {
    if (HEADING_RE.test(line.trim())) {
      if (cur) scenes.push(cur);
      cur = { heading: line.trim(), body: [] };
    } else if (cur) {
      cur.body.push(line);
    } else {
      cur = { heading: "", body: [line] };
    }
  }
  if (cur) scenes.push(cur);
  return scenes.map((s, i) => statsFor2(s.heading, s.body, i));
}
function statsFor2(heading, body, index) {
  let location = "", timeOfDay = "";
  const h = heading.replace(HEADING_RE, (m) => m).trim();
  if (heading.includes(" - ") || heading.includes(" \u2013 ")) {
    const parts = heading.split(/\s[–-]\s/);
    location = (parts[0] || "").replace(/^(INT\.|EXT\.|INT\/EXT|EXT\/INT|ESC\.|ESCENA|SCENE)\s*/i, "").trim();
    timeOfDay = (parts[1] || "").trim();
  } else {
    location = h.replace(/^(INT\.|EXT\.|INT\/EXT|EXT\/INT|ESC\.|ESCENA|SCENE)\s*/i, "").trim();
  }
  let actionLines = 0, dialogueLines = 0;
  let inDialogue = false;
  for (const raw of body) {
    const t = raw.trim();
    if (!t) {
      inDialogue = false;
      continue;
    }
    if (CUE_RE.test(t) && t.split(/\s+/).length <= 5 && t === t.toUpperCase()) {
      inDialogue = true;
      continue;
    }
    if (inDialogue) dialogueLines++;
    else actionLines++;
  }
  const totalLines = actionLines + dialogueLines;
  const estMinutes = totalLines / 50;
  const estNovelWords = Math.round(actionLines * ALPHA + dialogueLines * BETA + INTROSPECTION);
  const weight = Math.min(100, Math.round(totalLines * 1.6));
  return { index, heading, location, timeOfDay, actionLines, dialogueLines, estMinutes, estNovelWords, weight, text: [heading, ...body].join("\n") };
}
function novelDirectivesFor(s, language) {
  const d = [];
  if (s.actionLines > s.dialogueLines * 2) {
    d.push("Escena de ACCI\xD3N visual: expande masivamente entorno, cinem\xE1tica del movimiento y sensaciones f\xEDsicas. Descripciones largas, ralentiza el tiempo narrativo.");
  } else if (s.dialogueLines > s.actionLines * 2) {
    d.push("Escena de DI\xC1LOGO: ritmo r\xE1pido. Enf\xF3cate en el subtexto \u2014 lenguaje corporal, pausas y pensamientos entre l\xEDneas, no en describir el entorno.");
  } else {
    d.push("Escena MIXTA: equilibra descripci\xF3n y di\xE1logo, alternando acci\xF3n sensorial con subtexto.");
  }
  if (s.estMinutes < 0.3) {
    d.push("Dura pocos segundos en pantalla: tr\xE1tala como transici\xF3n r\xE1pida, un solo p\xE1rrafo fluido que conecte con lo siguiente.");
  } else if (s.estMinutes > 2.5) {
    d.push("Es una secuencia larga y de peso: desarr\xF3llala como un cap\xEDtulo/escena completa con profundidad.");
  }
  if (s.location || s.timeOfDay) {
    d.push(`Ambienta al inicio: ${s.location}${s.timeOfDay ? ` durante ${s.timeOfDay}` : ""} \u2014 describe c\xF3mo se siente la luz y la atm\xF3sfera de ese lugar/momento.`);
  }
  d.push(`Objetivo orientativo: ~${s.estNovelWords} palabras de prosa para esta escena (no es un l\xEDmite r\xEDgido).`);
  void language;
  return d;
}
function targetWordsForScenes(scenes) {
  return scenes.reduce((sum, s) => sum + s.estNovelWords, 0);
}
function rhythmBriefForBlock(scenes, language) {
  return scenes.map(
    (s) => `\xB7 Escena ${s.index + 1} [${s.location}${s.timeOfDay ? "/" + s.timeOfDay : ""}] acci\xF3n:${s.actionLines} di\xE1logo:${s.dialogueLines} ~${s.estMinutes.toFixed(1)}min \u2192 ${novelDirectivesFor(s, language).join(" ")}`
  ).join("\n");
}
function pageBudget(novelText, maxPages = 120) {
  const sourceWords = novelText.trim().split(/\s+/).filter(Boolean).length;
  const novelPages = sourceWords / 300;
  const targetPages = Math.min(maxPages, Math.max(20, Math.round(novelPages * 0.55)));
  const compressionRatio = Math.min(1, targetPages / Math.max(1, novelPages));
  const guidance = compressionRatio < 0.6 ? "COMPRESI\xD3N FUERTE: corta subtramas menores, fusiona escenas, convierte introspecci\xF3n larga en acci\xF3n visible y di\xE1logo con subtexto. Mant\xE9n solo lo que hace avanzar la trama." : "COMPRESI\xD3N MODERADA: condensa descripci\xF3n en acotaciones breves; conserva las escenas clave y los giros.";
  return {
    sourceWords,
    maxPages: targetPages,
    targetScreenMinutes: targetPages,
    // 1 page ≈ 1 minute
    compressionRatio: Math.round(compressionRatio * 100) / 100,
    guidance
  };
}
export {
  completion_exports as completion,
  emotion_arc_exports as emotionArc,
  lexicon_exports as lexicon,
  screenplay_rhythm_exports as rhythm,
  scene_splitter_exports as sceneSplitter,
  screenplay_exports as screenplay,
  script_parser_exports as scriptParser,
  text_metrics_exports as textMetrics
};
