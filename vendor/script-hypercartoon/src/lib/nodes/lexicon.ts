/**
 * lexicon.ts — the closed word lists the node engine reads. Letters only: no model,
 * no network. Every list is plain data so a language can be added without touching
 * the engine.
 */

export type NodesLang = 'es' | 'en' | 'auto';

export interface Lexicon {
  stop:        Set<string>;     // words that never open a node and carry no weight
  months:      string[];        // lower-case, index 0 = January
  joiners:     Set<string>;     // lower-case words allowed inside a name ("John de Bohême", "Bank of America")
  possessive:  RegExp;          // stripped from the end of a token ("Jobs's" → "Jobs")
  placeCues:   Set<string>;     // words that live in the orbit of a place
  personCues:  Set<string>;     // words that live in the orbit of a character (speech, body, kinship)
  speech:      Set<string>;     // speech verbs
  placePreps:  Set<string>;     // prepositions that precede a place
  preVerb:     Set<string>;     // small words that usually sit right before a verb (clitics, subject pronouns, negation)
  determiners: Set<string>;     // articles / possessives that open a noun phrase (a noun is what usually follows them)
  toolPreps:   Set<string>;     // prepositions that precede an instrument ("con la espada" / "with the sword")
  verbish:     RegExp;          // word endings that mark a verb form
  titles:      Set<string>;     // title words that can be glued to ONE name ("rey John")
  address:     Set<string>;     // forms of address ("mi señor", "Dios")
  addressPoss: Set<string>;     // words that make a lower-case address form count ("mi", "su")
  /** titles of sections that are NOT the story: matched against a heading with letters only, accents folded */
  sections:    { front: string[]; back: string[] };
  roleWords:   string[];        // role nouns whose link to a character is worth showing
  entityWords: Set<string>;     // common nouns that behave as characters (bestia, asesor…)
  sluglineWord: RegExp;         // INT / EXT
}

const ES_STOP = 'el la los las un una unos unas de del al a en por con y o u e que se su sus lo le les me te mi tu nos os mis tus como más muy no sí si ni sino pero mas para entre hasta desde hacia sobre tras ante bajo este esta esto estos estas ese esa eso esos esas aquel aquella aquello cuando donde quien quienes cual cuales cuyo todo toda todos todas otro otra otros otras mismo misma ya ahora entonces después antes siempre nunca también así aquí allí allá era eran fue fueron ser es son está están estaba había han ha he hay habían tiene tenía hace hacía puede podía dijo digo dice ver vi vio yo él ella ellos ellas nosotros usted ustedes mí ti qué cómo cuándo dónde quién tan tanto pues aun aún solo sólo cada algo nada alguien nadie uno dos tres ahí tal vez aunque porque mientras durante según cuyas sin hacer hizo van vamos voy vas'.split(' ');

const EN_STOP = 'the a an and or but of to in on at for from with by as is was were be been he she it they we you i his her its their our my your him them me us this that these those not no so if then than when while which who whom what where how there here had has have do did does would could should will can may might also just very more most some any all each other into out up down over under after before about against between through during again once only own same too said say says'.split(' ');

const ES: Lexicon = {
  stop: new Set(ES_STOP),
  months: ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'],
  joiners: new Set(['de', 'del', 'la', 'las', 'los', 'el']),
  possessive: /[’']s$/,
  placeCues: new Set('capital reino reinos pueblo poblado ciudad castillo aldea palacio muros alrededores frontera territorio tierra norte sur este oeste dirige dirigió dirigieron dirigían viaje camino llegó llegada llegaron marchó partió abandonó rumbo región provincia imperio condado puerto isla bosque montaña montañas río mar planeta aterrizar habitantes ejército gobernantes gobernante corona trono era eras apogeo acuerdo'.split(' ')),
  personCues: new Set('dijo preguntó respondió exclamó gritó susurró contestó añadió murmuró replicó comentó afirmó ordenó pidió secundó pensó sintió miró miraba sonrió asintió ojos mirada brazo brazos mano manos rostro cabeza voz hombre mujer joven padre madre hijo hija hermano amigo herido soldado rey reina señor majestad'.split(' ')),
  speech: new Set('dijo dijeron preguntó preguntaron respondió respondieron exclamó gritó susurró contestó añadió murmuró replicó comentó afirmó ordenó pidió secundó'.split(' ')),
  placePreps: new Set(['en', 'desde', 'hacia', 'hasta']),
  toolPreps: new Set(['con', 'mediante', 'sin']),
  preVerb: new Set('se lo la le les me te nos no que y ya él ella ellos ellas'.split(' ')),
  determiners: new Set('el la los las un una unos unas su sus mi mis tu tus del al este esta ese esa aquel aquella estos estas esos esas'.split(' ')),
  verbish: /(?:ó|aron|ieron|ió|ando|iendo|ían|aba|aban|ado|ido|ar|er|ir)$/,
  titles: new Set(['rey', 'reina', 'monarca', 'presidente', 'capitán', 'doctor', 'general', 'príncipe', 'duque', 'conde', 'emperador']),
  address: new Set(['señor', 'amo', 'majestad', 'maestro', 'capitán', 'dios']),
  addressPoss: new Set(['mi', 'su', 'nuestro', 'vuestro', 'oh']),
  sections: { front: ['introduccion', 'prologo', 'prefacio', 'prologodelautor', 'prologodeledicion', 'dedicatoria', 'epigrafe', 'notadelautor', 'notaalolector', 'advertencia', 'presentacion', 'indice', 'contenido', 'creditos', 'derechos', 'agradecimientos', 'sobreelautor', 'personajes'], back: ['agradecimientos', 'notas', 'bibliografia', 'fuentes', 'indiceanalitico', 'glosario', 'apendice', 'sobreelautor', 'posfacio', 'entrevistas'] },
  roleWords: ['rey', 'reina', 'monarca', 'majestad', 'bestia', 'monstruo', 'presidente', 'príncipe', 'asesor'],
  entityWords: new Set('rey monarca bestia monstruo asesor soldados soldado reina príncipe guardias criado sirviente'.split(' ')),
  sluglineWord: /\b(INT|EXT)\b/,
};

const EN: Lexicon = {
  stop: new Set(EN_STOP),
  months: ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december'],
  joiners: new Set(['of']),
  possessive: /[’']s$/,
  placeCues: new Set('capital kingdom kingdoms village town city castle palace walls outskirts border territory land north south east west headed traveled journey road arrived arrival left region province empire county port island forest mountain mountains river sea planet landed inhabitants army ruler crown throne era age headquarters campus office building'.split(' ')),
  personCues: new Set('said asked replied answered shouted whispered added murmured told thought felt looked smiled nodded eyes gaze arm arms hand hands face head voice man woman young father mother son daughter brother friend wounded soldier king queen lord majesty'.split(' ')),
  speech: new Set('said asked replied answered shouted whispered added murmured told exclaimed insisted explained recalled'.split(' ')),
  placePreps: new Set(['in', 'at', 'to', 'from', 'near', 'into', 'toward', 'towards', 'outside', 'inside']),
  toolPreps: new Set(['with', 'using', 'without']),
  preVerb: new Set('he she it they we i to not then and who'.split(' ')),
  determiners: new Set('the a an his her its their my your our this that these those'.split(' ')),
  verbish: /(?:ed|ing)$/,
  titles: new Set(['king', 'queen', 'monarch', 'president', 'captain', 'doctor', 'general', 'prince', 'duke', 'count', 'emperor', 'dr', 'mr', 'mrs']),
  address: new Set(['lord', 'master', 'majesty', 'sir', 'god']),
  addressPoss: new Set(['my', 'your', 'his', 'our', 'oh']),
  sections: { front: ['introduction', 'prologue', 'foreword', 'preface', 'dedication', 'epigraph', 'authorsnote', 'notetothereader', 'acknowledgments', 'acknowledgements', 'contents', 'tableofcontents', 'copyright', 'abouttheauthor', 'characters', 'cast', 'fromtheauthor'], back: ['notes', 'sources', 'bibliography', 'index', 'appendix', 'glossary', 'afterword', 'acknowledgments', 'acknowledgements', 'abouttheauthor', 'interviews', 'photocredits'] },
  roleWords: ['king', 'queen', 'monarch', 'majesty', 'beast', 'monster', 'president', 'prince', 'adviser'],
  entityWords: new Set('king monarch beast monster adviser soldiers soldier queen prince guards servant'.split(' ')),
  sluglineWord: /\b(INT|EXT)\b/,
};

/** Language-free fallback: no word lists at all — the engine derives its function words from the text itself. */
const AUTO: Lexicon = {
  stop: new Set(), months: [], joiners: new Set(), possessive: /[’']s$/,
  placeCues: new Set(), personCues: new Set(), speech: new Set(), placePreps: new Set(), toolPreps: new Set(), preVerb: new Set(), determiners: new Set(), verbish: /$^/,
  titles: new Set(), address: new Set(), addressPoss: new Set(), roleWords: [], entityWords: new Set(), sections: { front: [], back: [] }, sluglineWord: /\b(INT|EXT)\b/,
};

export const LEXICONS: Record<NodesLang, Lexicon> = { es: ES, en: EN, auto: AUTO };

/** Pick the language by counting which stop list the text hits more. */
export function detectLang(sample: string): NodesLang {
  const words = (sample.slice(0, 40000).toLowerCase().match(/[\p{L}]+/gu) ?? []);
  let es = 0, en = 0;
  for (const w of words) { if (ES.stop.has(w)) es++; if (EN.stop.has(w)) en++; }
  if (Math.max(es, en) < words.length * 0.08) return 'auto';       // neither list fits: any other language
  return es > en ? 'es' : 'en';
}
