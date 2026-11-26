"""Frame/object/motion coherence metrics on label maps. Pure numpy, O(T*H*W), no model calls."""
from typing import Dict

import numpy as np


def _centroids_areas(labels: np.ndarray, oid: int):
    T = labels.shape[0]
    cen = np.full((T, 2), np.nan)
    area = np.zeros(T)
    ys, xs = np.mgrid[0 : labels.shape[1], 0 : labels.shape[2]]
    for t in range(T):
        m = labels[t] == oid
        a = m.sum()
        area[t] = a
        if a:
            cen[t] = (ys[m].mean(), xs[m].mean())
    return cen, area


def coherence_report(labels: np.ndarray) -> Dict[str, float]:
    """labels: uint8[T,H,W]. Returns scores in [0,1] (1 = perfectly coherent) plus raw counts.

    - temporal_iou:   mean IoU of each object's mask between consecutive frames (shape/position continuity)
    - persistence:    1 - fragmentation (objects that vanish and reappear break identity)
    - id_churn:       fraction of ids born after frame 0 (new identities appearing = drift/hallucination)
    - motion_smooth:  1 / (1 + mean |acceleration| / mean |velocity|) of centroids (jitter / teleporting)
    """
    T = labels.shape[0]
    ids = [int(i) for i in np.unique(labels) if i != 0]
    if T < 3 or not ids:
        return {"n_objects": len(ids), "coherence": float("nan")}

    ious, gaps, births, smooth = [], 0, 0, []
    for oid in ids:
        pres = (labels == oid).reshape(T, -1)
        has = pres.any(1)
        first = int(np.argmax(has))
        births += first > 0
        gaps += int(np.sum(np.diff(has[first:].astype(int)) == 1))  # re-appearances after a vanish
        both = has[1:] & has[:-1]
        inter = (pres[1:] & pres[:-1]).sum(1)
        union = (pres[1:] | pres[:-1]).sum(1)
        ious.extend((inter[both] / np.maximum(union[both], 1)).tolist())
        cen, _ = _centroids_areas(labels, oid)
        v = np.diff(cen, axis=0)
        acc = np.diff(v, axis=0)
        ok = ~np.isnan(acc).any(1)
        if ok.sum():
            speed = np.nanmean(np.linalg.norm(v[~np.isnan(v).any(1)], axis=1)) + 1e-6
            smooth.append(1.0 / (1.0 + np.linalg.norm(acc[ok], axis=1).mean() / speed))

    rep = {
        "n_objects": len(ids),
        "temporal_iou": float(np.mean(ious)) if ious else 0.0,
        "persistence": float(max(0.0, 1.0 - gaps / len(ids))),
        "id_churn": float(births / len(ids)),
        "motion_smooth": float(np.mean(smooth)) if smooth else 1.0,
    }
    rep["coherence"] = float(
        np.mean([rep["temporal_iou"], rep["persistence"], 1.0 - rep["id_churn"], rep["motion_smooth"]])
    )
    return rep
