"""Group shots ('tomas') into scenes ('escenas'): consecutive shots that share a visual world (colour palette + brightness).
A shot joins the scene of the most similar of the previous few shots (so shot / reverse-shot dialogue stays in one scene) if it is similar
enough; otherwise it starts a new scene. Heuristic: tune `threshold`, or replace by a model; scene = location/time is not read from the picture."""
from typing import Dict, List, Sequence

import numpy as np


def palette_distance(a: Sequence[Sequence[int]], b: Sequence[Sequence[int]]) -> float:
    """Symmetric mean nearest-colour distance between two palettes, 0..1 (RGB, divided by the cube diagonal)."""
    if not a or not b:
        return 1.0
    A, B = np.asarray(a, float), np.asarray(b, float)
    d = np.linalg.norm(A[:, None] - B[None], axis=-1) / (255 * np.sqrt(3))
    return float((d.min(1).mean() + d.min(0).mean()) / 2)


def shot_distance(s1: Dict, s2: Dict) -> float:
    return 0.8 * palette_distance(s1.get("palette", []), s2.get("palette", [])) + 0.2 * abs(s1.get("brightness", 0.5) - s2.get("brightness", 0.5))


def group_scenes(shots: Sequence[Dict], threshold: float = 0.16, lookback: int = 3) -> List[int]:
    """-> scene index (0-based) per shot."""
    scene: List[int] = []
    for i, s in enumerate(shots):
        best, best_d = None, 1e9
        for j in range(max(0, i - lookback), i):
            d = shot_distance(shots[j], s)
            if d < best_d:
                best, best_d = j, d
        if best is not None and best_d <= threshold:
            scene.append(scene[best])
        else:
            scene.append((max(scene) + 1) if scene else 0)
    return scene
