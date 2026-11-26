"""Prompt file parsing and style-embedding blending. Torch-free on purpose (testable anywhere).

A prompt file is JSON/JSONL: one video per entry, one object per 3-second segment:
  {"text", "requires_scene_transition", "neg_text", "alt_text", "mix"}
`alt_text` + `mix` (0..1) ask the sampler to encode both texts and interpolate the text embeddings
(emb = (1-mix)*emb(text) + mix*emb(alt_text)): this is how two animation styles are blended at generation time."""
import json
from dataclasses import dataclass
from typing import List, Optional, Tuple

SCENE_END_TOKEN = "<end_scene>"
SCENE_START_TOKEN = "<start_scene>"


@dataclass(frozen=False)
class SceneDescription:
    text: str
    requires_scene_transition: bool = False
    neg_text: Optional[str] = None
    alt_text: Optional[str] = None   # same segment described in the second style
    mix: float = 0.0                 # 0 = only `text`, 1 = only `alt_text`
    control: Optional[str] = None    # path of a control .npz for the whole video (see control_data.py)


def insert_special_tokens(scenes: List[SceneDescription]) -> None:
    for i, scene in enumerate(scenes):
        if i == 0:
            scene.requires_scene_transition = False  # no scene-start token on the first scene
        if scene.requires_scene_transition:
            scenes[i - 1].text += SCENE_END_TOKEN
            scenes[i].text = SCENE_START_TOKEN + scenes[i].text
            if scenes[i - 1].alt_text is not None:
                scenes[i - 1].alt_text += SCENE_END_TOKEN
            if scenes[i].alt_text is not None:
                scenes[i].alt_text = SCENE_START_TOKEN + scenes[i].alt_text


def load_prompts(path: str) -> List[List[SceneDescription]]:
    is_jsonl = str(path).endswith(".jsonl")
    assert is_jsonl or str(path).endswith(".json"), "Invalid prompt file format. Expected .jsonl or .json"
    with open(path, "r", encoding="utf-8") as f:
        vids = [json.loads(line) for line in f.readlines() if line.strip()] if is_jsonl else json.load(f)
    out = []
    for v in vids:
        scenes = [SceneDescription(**obj) for obj in v]
        insert_special_tokens(scenes)
        out.append(scenes)
    return out


def blend_embeddings(a, b, mix: float):
    """Linear interpolation of two text embeddings (tensors or arrays of the same shape)."""
    if not 0.0 <= mix <= 1.0:
        raise ValueError("mix must be in [0, 1]")
    return a * (1.0 - mix) + b * mix if mix > 0 else a


def split_video(scenes: List[SceneDescription]) -> Tuple[List[str], List[Optional[str]], Optional[List[str]], float]:
    """-> (texts, neg_texts, alt_texts or None, mix). A video has one mix (the mean of its segments' mixes)."""
    alts = [s.alt_text for s in scenes]
    has_alt = all(a is not None for a in alts) and any(s.mix > 0 for s in scenes)
    mix = sum(s.mix for s in scenes) / len(scenes) if has_alt else 0.0
    return [s.text for s in scenes], [s.neg_text for s in scenes], (alts if has_alt else None), mix
