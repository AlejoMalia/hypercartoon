"""Any script-like text -> structured Doc -> studio script. Accepts: screenplay (sluglines + CUE lines), 'NAME: line',
and prose with dash dialogue. Heuristics are deliberately simple; the point is that nothing has to be hand-formatted."""
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from studio.story.pacing import scene_seconds

_HEAD = re.compile(r"^\s*(?:\d+[A-Z]?[.\-)]?\s+)?(INT\.?\s*[/\-]\s*EXT\.?|EXT\.?\s*[/\-]\s*INT\.?|I\s*/\s*E|INTERIOR|EXTERIOR|INT|EXT|ESC\.?|ESCENA)\b\.?[\s.\-–—:]*(.*)$", re.I)
_TRANS = re.compile(r"^\s*(CUT TO|FADE (IN|OUT|TO)|DISSOLVE TO|CORTE A|FUNDIDO|SMASH CUT)\b.*:?\s*$", re.I)
_CUE = re.compile(r"^[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ0-9 .'\-]{0,28}(\s*\((V\.?O\.?|O\.?S\.?|CONT'?D|OFF)\))?$")
_NAMECOLON = re.compile(r"^\s*([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ .'\-]{0,24}?)\s*(?:\([^)]*\))?\s*:\s*(.+)$")
_DASH = re.compile(r"^\s*[—–]\s*(.+)$")
_ATTR = re.compile(r"[—–-]\s*(?:dijo|preguntó|pregunto|respondió|respondio|exclamó|exclamo|gritó|grito|susurró|susurro|said|asked|shouted|whispered)\s+(?:el |la |the )?([A-ZÁÉÍÓÚÑ][\wáéíóúñ]+)", re.I)
_TIME = re.compile(r"\b(NOCHE|NIGHT|D[IÍ]A|DAY|AMANECER|DAWN|ATARDECER|DUSK|TARDE|MA[ÑN]ANA|MORNING)\b", re.I)


@dataclass
class DocScene:
    heading: str = ""
    place: str = ""
    time: str = ""
    int_ext: str = ""
    action: List[str] = field(default_factory=list)
    lines: List[Tuple[str, str]] = field(default_factory=list)   # (CHARACTER, text)
    cues: List[str] = field(default_factory=list)                # parentheticals ("en voz baja")
    neg: Optional[str] = None
    requested: float = 0.0
    tension: Optional[float] = None

    @property
    def action_text(self) -> str:
        return " ".join(self.action).strip()

    @property
    def action_words(self) -> int:
        return len(self.action_text.split())


@dataclass
class Doc:
    scenes: List[DocScene]
    fmt: str


def _heading(line: str):
    m = _HEAD.match(line)
    if not m:
        return None
    rest = m.group(2).strip()
    t = _TIME.search(rest)
    place = re.split(r"\s+[-–—·]\s+|\s*,\s*", rest)[0].strip() if rest else ""
    return m.group(1).upper().replace(".", ""), place, (t.group(1).lower() if t else ""), line.strip()


def parse_doc(text: str) -> Doc:
    lines = [ln.rstrip() for ln in text.replace("\r", "").split("\n")]
    scenes: List[DocScene] = []
    cur: Optional[DocScene] = None
    fmt = "prose"
    i, last_speakers = 0, []

    def scene() -> DocScene:
        nonlocal cur
        if cur is None:
            cur = DocScene()
            scenes.append(cur)
        return cur

    while i < len(lines):
        ln = lines[i].strip()
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        h = _heading(ln) if ln else None
        if not ln:
            # blank line closes a scene only in the simple block format (no sluglines in the whole text)
            if fmt in ("blocks",) and cur is not None and (cur.action or cur.lines):
                cur = None
            i += 1
            continue
        if _TRANS.match(ln):
            i += 1
            continue
        if h:
            fmt = "screenplay"
            cur = DocScene(heading=h[3], int_ext=h[0], place=h[1], time=h[2])
            scenes.append(cur)
            i += 1
            continue
        if ln.startswith("NEG:"):
            scene().neg = ln[4:].strip()
            i += 1
            continue
        m = re.match(r"^[\[\(]\s*(\d+(?:\.\d+)?)\s*s(?:ec)?\s*[\]\)]\s*(.*)$", ln, re.I)
        if m:
            scene().requested = float(m.group(1))
            ln = m.group(2).strip()
            if not ln:
                i += 1
                continue
        # screenplay cue: UPPERCASE line followed by dialogue
        if _CUE.match(ln) and nxt and not _heading(nxt) and not _TRANS.match(nxt) and fmt != "blocks" and not ln.endswith(":"):
            name = re.sub(r"\s*\(.*?\)", "", ln).strip()
            i += 1
            while i < len(lines) and lines[i].strip():
                t = lines[i].strip()
                if t.startswith("("):
                    scene().cues.append(t.strip("() "))
                else:
                    scene().lines.append((name, t))
                i += 1
            last_speakers = ([name] + [s for s in last_speakers if s != name])[:2]
            fmt = "screenplay" if fmt == "prose" else fmt
            continue
        nc = _NAMECOLON.match(ln)
        if nc and (nc.group(1).isupper() or len(nc.group(1).split()) <= 2) and not _heading(ln):
            if fmt == "prose" and not scenes:
                fmt = "blocks"
            if fmt == "prose":
                fmt = "blocks"
            scene().lines.append((nc.group(1).strip().upper(), nc.group(2).strip()))
            last_speakers = ([nc.group(1).strip().upper()] + [s for s in last_speakers if s != nc.group(1).strip().upper()])[:2]
            i += 1
            continue
        d = _DASH.match(ln)
        if d:
            body = d.group(1)
            a = _ATTR.search(body)
            who = a.group(1).upper() if a else (last_speakers[1] if len(last_speakers) > 1 else (last_speakers[0] if last_speakers else "NARRADOR"))
            said = re.sub(r"\s+([.,;:!?])", r"\1", _ATTR.sub("", body)).strip(" —–-")
            scene().lines.append((who, said))
            last_speakers = ([who] + [s for s in last_speakers if s != who])[:2]
            i += 1
            continue
        scene().action.append(ln)
        i += 1
    # block format: a heading-less first line of a block is the scene description; nothing more to do
    scenes = [s for s in scenes if s.action or s.lines]
    return Doc(scenes, fmt)


def doc_to_script(doc: Doc, default_seconds: float = 0.0) -> str:
    """Studio script text. Durations come from pacing (dialogue fits inside its scene)."""
    blocks = []
    for s in doc.scenes:
        sec = scene_seconds(s.action_words, s.lines, max(s.requested, default_seconds))
        head = s.heading or ""
        desc = s.action_text or (head and "") or ""
        first = f"{head} [{int(sec)}s] {desc}".strip() if head else f"[{int(sec)}s] {desc or ', '.join(sorted({c for c, _ in s.lines})) + ' talking'}"
        rows = [first] + [f"{c}: {t}" for c, t in s.lines] + ([f"NEG: {s.neg}"] if s.neg else [])
        blocks.append("\n".join(rows))
    return "\n\n".join(blocks) + "\n"
