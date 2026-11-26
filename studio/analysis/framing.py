"""Framing, subject position and occupied space from detections (any detector: blobs, YOLO, Grounding DINO + SAM 2).

An element is {label, score, bbox [x0,y0,x1,y1] normalised 0..1, area (fraction of the frame; from the mask when there is one),
mask (optional bool [h,w])}. Shot type is a HEURISTIC from the height of the main subject relative to the frame (editable thresholds)."""
from typing import Dict, List, Optional, Sequence

import numpy as np

CHARACTER_LABELS = {"person", "people", "character", "man", "woman", "boy", "girl", "child", "animal", "cat", "dog", "mouse", "bird", "horse", "persona"}
# (min subject height / frame height, label): the subject fills most of the frame -> closer shot
SHOT_TYPES = [(0.85, "primer plano"), (0.55, "plano medio"), (0.28, "plano completo"), (0.0, "plano general")]
THIRDS_X, THIRDS_Y = ("izquierda", "centro", "derecha"), ("arriba", "medio", "abajo")
POWER_POINTS = [(1 / 3, 1 / 3), (2 / 3, 1 / 3), (1 / 3, 2 / 3), (2 / 3, 2 / 3)]


def shot_type(height_ratio: Optional[float]) -> str:
    if height_ratio is None:
        return "plano de ambiente (sin personaje)"
    return next(name for thr, name in SHOT_TYPES if height_ratio >= thr)


def third_cell(cx: float, cy: float) -> Dict[str, str]:
    col = min(2, max(0, int(cx * 3)))
    row = min(2, max(0, int(cy * 3)))
    return {"horizontal": THIRDS_X[col], "vertical": THIRDS_Y[row], "cell": f"{THIRDS_Y[row]}-{THIRDS_X[col]}"}


def power_point_distance(cx: float, cy: float) -> float:
    """Distance (frame diagonal units) to the nearest rule-of-thirds intersection; < 0.1 reads as 'on a third'."""
    return float(min(np.hypot(cx - px, cy - py) for px, py in POWER_POINTS) / np.hypot(1, 1))


def box_area(b: Sequence[float]) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def describe(e: Dict) -> Dict:
    x0, y0, x1, y1 = e["bbox"]
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return {"label": e["label"], "score": float(e.get("score", 1.0)), "bbox": [float(v) for v in e["bbox"]], "area_pct": 100.0 * float(e.get("area", box_area(e["bbox"]))),
            "height_pct": 100.0 * (y1 - y0), "width_pct": 100.0 * (x1 - x0), "center": [cx, cy], **third_cell(cx, cy),
            "power_point_distance": power_point_distance(cx, cy)}


def occupancy_grid(elements: Sequence[Dict], grid: int = 3, res: int = 60) -> np.ndarray:
    """Fraction of each grid cell covered by any element (masks if present, else boxes). [grid, grid]."""
    cov = np.zeros((res, res), bool)
    for e in elements:
        m = e.get("mask")
        if m is not None:
            mh, mw = m.shape
            ys = (np.arange(res) * mh // res)
            xs = (np.arange(res) * mw // res)
            cov |= m[np.ix_(ys, xs)].astype(bool)
        else:
            x0, y0, x1, y1 = e["bbox"]
            cov[int(y0 * res) : max(int(y0 * res) + 1, int(np.ceil(y1 * res))), int(x0 * res) : max(int(x0 * res) + 1, int(np.ceil(x1 * res)))] = True
    step = res // grid
    return np.array([[cov[r * step : (r + 1) * step, c * step : (c + 1) * step].mean() for c in range(grid)] for r in range(grid)])


def union_coverage(elements: Sequence[Dict], res: int = 60) -> float:
    if not elements:
        return 0.0
    g = occupancy_grid(elements, grid=1, res=res)
    return float(g[0, 0])


def composition(elements: Sequence[Dict], subject_label_hint: Optional[Sequence[str]] = None) -> Dict:
    """Shot-level framing from the elements of one keyframe. The main subject is the largest character-like element
    (labels in CHARACTER_LABELS or in `subject_label_hint`); if none, the largest element of an unlabeled detector, else 'ambiente'."""
    labels = {l.lower() for l in CHARACTER_LABELS} | {l.lower() for l in (subject_label_hint or [])}
    desc = [describe(e) for e in elements]
    chars = [d for d in desc if d["label"].lower() in labels]
    unlabeled = [d for d in desc if d["label"] in ("elemento", "object", "blob")]
    pool = chars or (unlabeled if unlabeled and len(unlabeled) == len(desc) else [])
    subject = max(pool, key=lambda d: d["area_pct"]) if pool else None
    grid = occupancy_grid(elements)
    ys, xs = np.mgrid[0:3, 0:3]
    mass = grid.sum()
    com = [float((grid * (xs + 0.5) / 3).sum() / mass), float((grid * (ys + 0.5) / 3).sum() / mass)] if mass > 0 else None
    return {"shot_type": shot_type(subject["height_pct"] / 100 if subject else None), "subject": subject, "n_characters": len(chars),
            "subject_source": "personajes detectados" if chars else ("elemento más grande (sin etiquetas)" if subject else "ninguno"),
            "coverage_pct": 100.0 * union_coverage(elements), "free_space_pct": 100.0 * (1 - union_coverage(elements)),
            "occupancy_3x3": grid.round(3).tolist(), "center_of_mass": com, "elements": desc}
