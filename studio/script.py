"""Screenplay/prompt -> scene list -> 3s segments -> jsonl + eval config consumable by sample.py."""
import json
import math
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from studio.overlays import NEGATIVE_TEXT
from studio.profile import SEG, STAGES, style_prompt
from studio.story.pacing import dialogue_seconds

_DUR = re.compile(r"\s*[\[\(]\s*(\d+(?:\.\d+)?)\s*s(?:ec)?\s*[\]\)]\s*")
_HEAD = re.compile(r"^\s*(INT\.|EXT\.|INT/EXT\.)", re.I)


_SPEAK = re.compile(r"^\s*([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ .\-']{0,24}?)\s*(?:\([^)]*\))?\s*:\s*(.+)$")


@dataclass
class Scene:
    text: str
    seconds: float
    new_scene: bool
    neg: Optional[str] = None
    lines: List[tuple] = field(default_factory=list)  # [(character, dialogue)]
    emo: List[dict] = field(default_factory=list)     # parallel to lines (filled by the emotion step)
    tension: Optional[float] = None                   # 0-100, from the story reading


def parse_script(src: str, default_seconds: float, known: Optional[set] = None) -> List[Scene]:
    """Blocks separated by blank lines. Optional '[6s]' prefix sets duration; 'NEG: ...' line = negative prompt;
    INT./EXT. headings force a scene transition. Missing durations use the learned median shot length."""
    scenes: List[Scene] = []
    for block in re.split(r"\n\s*\n", src.strip()):
        neg, body, heading, lines = None, [], False, []
        for line in block.splitlines():
            if line.upper().startswith("NEG:"):
                neg = line[4:].strip()
            elif (sm := _SPEAK.match(line)) and not _HEAD.match(line) \
                    and (sm.group(1).isupper() or sm.group(1) in (known or ())):
                lines.append((sm.group(1).strip(), sm.group(2).strip()))
            else:
                heading = heading or bool(_HEAD.match(line))
                body.append(line.strip())
        text = " ".join(body).strip()
        if not text and not lines:
            continue
        m = _DUR.search(text)
        sec = float(m.group(1)) if m else default_seconds
        text = _DUR.sub(" ", text).strip()
        sec = max(sec, dialogue_seconds(lines))  # dialogue must fit its scene (no late lines downstream)
        scenes.append(Scene(text, sec, heading or not scenes, neg, lines))
    return scenes


def to_segments(scenes: List[Scene], style: str, cast: Optional[Dict[str, str]] = None):
    """One entry per 3-second segment (the model takes one text chunk per 3s).
    cast: {CHARACTER: visual description} learned from the corpus; injected so identity stays constant.
    Returns (segments, voices) where voices[i] lists (character, line) spoken in segment i (sidecar for the sound system:
    SceneDescription has no field for it)."""
    cast = {k.upper(): v for k, v in (cast or {}).items()}
    segs, voices = [], []
    for sc in scenes:
        n = max(1, math.ceil(sc.seconds / SEG - 1e-6))
        who = list(dict.fromkeys(c for c, _ in sc.lines))
        look = "; ".join(cast[c.upper()] for c in who if c.upper() in cast)
        base = sc.text.rstrip(" .") or ", ".join(f"{c} talking" for c in who)
        for k in range(n):
            mine = [j for j in range(len(sc.lines)) if j % n == k]
            feel = ", ".join(dict.fromkeys(f"{sc.lines[j][0].title()} looks {sc.emo[j]['word']}" for j in mine if j < len(sc.emo)))
            parts = [base] + ([look] if look else []) + ([feel] if feel else []) + [style]
            segs.append({"text": ", ".join(parts), "requires_scene_transition": sc.new_scene and k == 0,
                         "neg_text": f"{sc.neg}, {NEGATIVE_TEXT}" if sc.neg else NEGATIVE_TEXT})  # never draw text, logos or subtitles
            voices.append([sc.lines[j] + ((sc.emo[j],) if j < len(sc.emo) else ()) for j in mine])
    return segs, voices


def pack_videos(segs: List[dict], max_seconds: int) -> List[List[dict]]:
    """Split into videos no longer than the longest trained stage."""
    per = int(max_seconds // SEG)
    return [segs[i : i + per] for i in range(0, len(segs), per)]


def stage_for(n_segments: int, max_seconds: int) -> int:
    need = n_segments * SEG
    return next((s for s in STAGES if s >= need and s <= max_seconds), max_seconds)


def split_voices(voices: List[list], max_seconds: int) -> List[List[list]]:
    per = int(max_seconds // SEG)
    return [voices[i : i + per] for i in range(0, len(voices), per)]


def write_jsonl(videos: List[List[dict]], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for v in videos:
            f.write(json.dumps(v, ensure_ascii=False) + "\n")


def eval_overrides(stage_seconds: int, steps: int = 50) -> Dict[str, object]:
    """Values to patch into configs/eval/hypercartoon-*/<stage>s.toml (latent frames = 4*s + 1)."""
    return {"eval.sampling_num_frames": 4 * stage_seconds + 1, "eval.num_denoising_steps": steps,
            "guider.num_steps": steps, "model.video_length": f"{stage_seconds}sec"}


def segment_scene_index(scenes: List[Scene]) -> List[int]:
    """Scene index of each 3-second segment, in the order `to_segments` emits them."""
    out = []
    for i, sc in enumerate(scenes):
        out += [i] * max(1, math.ceil(sc.seconds / SEG - 1e-6))
    return out
