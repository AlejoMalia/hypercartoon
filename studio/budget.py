"""Compute planner: spend GPU only where the picture needs it.

Everything except the video frames is CPU-cheap (story reading, emotion, voices, mouth tracks, mixing, planning).
For the frames the planner (1) skips anything already generated (cache keyed by prompt+config, with near-duplicate
retrieval so small script edits re-run only the changed videos), (2) gives each video only the denoising steps its tension
needs, (3) optionally drafts everything cheaply and refines only what fails the coherence gate.
Units are 'step-segments' (denoising steps x 3-second segments); pass a measured `sec_per_step_segment` to get GPU seconds."""
import hashlib
import json
import os
import re
from typing import Dict, List, Optional, Sequence

FULL = 50


def steps_for(tension: Optional[float], full: int = FULL) -> int:
    if tension is None:
        return int(full * 0.7)
    return 25 if tension < 35 else int(full * 0.7) if tension < 65 else full


def _tokens(texts: Sequence[str]) -> frozenset:
    return frozenset(re.findall(r"\w+", " ".join(texts).lower()))


def _key(texts: Sequence[str], cfg: str) -> str:
    return hashlib.sha1((cfg + "\n" + "\n".join(texts)).encode()).hexdigest()[:20]


class ShotCache:
    """Generated videos remembered by prompt + config. A hit needs >= the steps the new plan asks for."""

    def __init__(self, path: str, cfg: str = "default", near: float = 0.92):
        self.path, self.cfg, self.near = path, cfg, near
        self.e: Dict[str, dict] = json.load(open(path)) if os.path.exists(path) else {}

    def lookup(self, texts: Sequence[str], steps: int) -> Optional[dict]:
        k = _key(texts, self.cfg)
        if k in self.e and self.e[k]["steps"] >= steps:
            return dict(self.e[k], kind="exact")
        tk = _tokens(texts)
        for v in self.e.values():
            if v["cfg"] == self.cfg and v["steps"] >= steps and tk and len(tk & set(v["tokens"])) / len(tk | set(v["tokens"])) >= self.near:
                return dict(v, kind="near")
        return None

    def record(self, texts: Sequence[str], steps: int, video: str) -> None:
        self.e[_key(texts, self.cfg)] = {"tokens": sorted(_tokens(texts)), "steps": steps, "video": video, "cfg": self.cfg}
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        json.dump(self.e, open(self.path + ".tmp", "w"))
        os.replace(self.path + ".tmp", self.path)


def plan_compute(videos: List[List[dict]], tensions: Sequence[Optional[float]], cache: Optional[ShotCache] = None,
                 strategy: str = "adaptive", full: int = FULL, draft: int = 20, fail_rate: float = 0.25,
                 sec_per_step_segment: Optional[float] = None, step_cache_speedup: Optional[float] = None) -> Dict:
    items, baseline, planned = [], 0, 0
    for i, (v, t) in enumerate(zip(videos, tensions)):
        n = len(v)
        steps = full if strategy == "full" else draft if strategy == "draft" else steps_for(t, full)
        hit = cache.lookup([s["text"] for s in v], steps) if cache else None
        cost = 0 if hit else n * steps
        items.append({"video": i, "segments": n, "tension": t, "steps": steps, "cached": hit["kind"] if hit else None, "cost": cost})
        baseline += n * full
        planned += cost
    refine = int(round(fail_rate * sum(it["segments"] * full for it in items if not it["cached"]))) if strategy == "draft" else 0
    expected = planned + refine
    if step_cache_speedup and step_cache_speedup > 1.0:  # measured speed-up of eval.step_cache_threshold > 0 (never assumed)
        expected = int(round(expected / step_cache_speedup))
    k = sec_per_step_segment
    saved = 100.0 * (1 - expected / baseline) if baseline else 0.0
    hit_n = sum(1 for it in items if it["cached"])
    unit = f"{expected * k:.0f} s de GPU" if k else f"{expected} pasos×segmento"
    base_u = f"{baseline * k:.0f} s de GPU" if k else f"{baseline} pasos×segmento"
    return {"strategy": strategy, "videos": items, "baseline": baseline, "planned": planned, "refine_expected": refine,
            "expected": expected, "saving_pct": round(saved, 1),
            "runs": sorted({it["steps"] for it in items if not it["cached"]}),
            "summary_es": (f"Estrategia **{strategy}**: {unit} frente a {base_u} con todo a {full} pasos (ahorro {saved:.0f} %). "
                           f"{hit_n} de {len(items)} vídeos salen de la caché. Estimación por pasos×segmento; no es una medición de GPU. "
                           f"Todo lo demás (lectura del guion, emoción, voces guía, pistas de boca, mezcla) corre en CPU.")}


def select_refine(scores: Sequence[float], target: float = 0.75) -> List[int]:
    """After a draft pass: the videos whose coherence is below target are the only ones re-run at full steps."""
    return [i for i, s in enumerate(scores) if s != s or s < target]
