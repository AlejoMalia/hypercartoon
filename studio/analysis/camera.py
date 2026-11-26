"""Camera movement from the dominant (background) motion between frames.

Per frame pair we get block displacements (numpy block matching with sub-pixel refinement, or OpenCV's Farneback dense flow when
cv2 is installed), fit a similarity model  dx = tx + s*X - r*Y,  dy = ty + r*X + s*Y  (X, Y from the frame centre) with iterative outlier
rejection (moving characters are outliers if the background dominates), and classify the median over the shot.
Convention: the camera pans RIGHT when the content moves LEFT (dx < 0); it tilts UP when the content moves down (dy > 0);
zoom/dolly IN when the content expands from the centre (s > 0). Flow cannot tell zoom from dolly.
Limits: flat cartoon backgrounds have no texture (blocks are skipped: with too few left the answer is 'indeterminada'), and a
character that fills the frame can be mistaken for the background."""
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

PAN_T, TILT_T, ZOOM_T, STATIC_T, SHAKE_T = 0.03, 0.03, 0.03, 0.015, 0.05   # per second, in frame widths / heights / scale


def to_gray_small(frame: np.ndarray, max_side: int = 96) -> np.ndarray:
    f = np.asarray(frame)
    st = max(1, max(f.shape[:2]) // max_side)
    g = f[::st, ::st].astype(np.float32)
    g = g.mean(-1) if g.ndim == 3 else g
    return g / (255.0 if g.max() > 1.5 else 1.0)


def block_flow(prev: np.ndarray, cur: np.ndarray, grid: Tuple[int, int] = (4, 8), radius: int = 4, min_std: float = 0.02):
    """Block matching (MSE) with parabolic sub-pixel refinement. -> (points [N,2] block centres (x,y), flows [N,2] (dx,dy))."""
    h, w = prev.shape
    bh, bw = (h - 2 * radius) // grid[0], (w - 2 * radius) // grid[1]  # blocks live inside a margin of `radius`: every block can be searched in all directions
    pts, flows = [], []
    for gy in range(grid[0]):
        for gx in range(grid[1]):
            y0, x0 = radius + gy * bh, radius + gx * bw
            blk = prev[y0 : y0 + bh, x0 : x0 + bw]
            if blk.std() < min_std:
                continue  # flat block: motion is not observable there
            sad = np.full((2 * radius + 1, 2 * radius + 1), np.inf)
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    ys, xs = y0 + dy, x0 + dx
                    if ys < 0 or xs < 0 or ys + bh > h or xs + bw > w:
                        continue
                    sad[dy + radius, dx + radius] = ((cur[ys : ys + bh, xs : xs + bw] - blk) ** 2).mean()  # MSE: the parabola fit is unbiased for it
            mn = np.nanmin(np.where(np.isfinite(sad), sad, np.nan))
            ties = np.argwhere(sad <= mn * (1 + 1e-3) + 1e-9)               # aperture problem: an edge matches at many shifts -> take the smallest
            iy, ix = ties[np.argmin(((ties - radius) ** 2).sum(1))]
            fx, fy = float(ix - radius), float(iy - radius)
            if 0 < ix < sad.shape[1] - 1 and np.isfinite(sad[iy, ix - 1]) and np.isfinite(sad[iy, ix + 1]):
                a, b, c = sad[iy, ix - 1], sad[iy, ix], sad[iy, ix + 1]
                den = a - 2 * b + c
                fx += 0.5 * (a - c) / den if den > 1e-9 else 0.0
            if 0 < iy < sad.shape[0] - 1 and np.isfinite(sad[iy - 1, ix]) and np.isfinite(sad[iy + 1, ix]):
                a, b, c = sad[iy - 1, ix], sad[iy, ix], sad[iy + 1, ix]
                den = a - 2 * b + c
                fy += 0.5 * (a - c) / den if den > 1e-9 else 0.0
            pts.append((x0 + bw / 2, y0 + bh / 2))
            flows.append((fx, fy))
    return np.array(pts, float).reshape(-1, 2), np.array(flows, float).reshape(-1, 2)


def dense_flow_samples(flow: np.ndarray, step: int = 8):
    """Dense flow [H,W,2] (e.g. cv2.calcOpticalFlowFarneback) -> sample points + flows on a grid."""
    h, w = flow.shape[:2]
    ys, xs = np.mgrid[step // 2 : h : step, step // 2 : w : step]
    return np.stack([xs.ravel(), ys.ravel()], 1).astype(float), flow[ys, xs].reshape(-1, 2).astype(float)


def fit_similarity(pts: np.ndarray, flows: np.ndarray, size: Tuple[int, int], iters: int = 3) -> Optional[Dict[str, float]]:
    """Robust LS for (tx, ty, s, r) in pixels; None if fewer than 4 points."""
    if len(pts) < 4:
        return None
    w, h = size
    X, Y = pts[:, 0] - w / 2, pts[:, 1] - h / 2
    keep = np.ones(len(pts), bool)
    sol = np.zeros(4)
    for _ in range(iters):
        n = int(keep.sum())
        if n < 4:
            return None
        A = np.zeros((2 * n, 4))
        b = np.zeros(2 * n)
        A[0::2, 0], A[0::2, 2], A[0::2, 3] = 1, X[keep], -Y[keep]
        A[1::2, 1], A[1::2, 2], A[1::2, 3] = 1, Y[keep], X[keep]
        b[0::2], b[1::2] = flows[keep, 0], flows[keep, 1]
        sol, *_ = np.linalg.lstsq(A, b, rcond=None)
        pred = np.stack([sol[0] + sol[2] * X - sol[3] * Y, sol[1] + sol[3] * X + sol[2] * Y], 1)
        res = np.linalg.norm(flows - pred, axis=1)
        mad = np.median(res[keep]) * 1.4826
        new = res <= max(2.0 * mad, 0.35)
        if new.sum() < 4 or (new == keep).all():
            break
        keep = new
    return {"tx": float(sol[0]), "ty": float(sol[1]), "zoom": float(sol[2]), "rot": float(sol[3]), "inliers": int(keep.sum()), "n": len(pts)}


def pair_motion(prev: np.ndarray, cur: np.ndarray, use_cv2: bool = True) -> Optional[Dict[str, float]]:
    """Global motion of one frame pair in pixels of the analysis grid."""
    size = (prev.shape[1], prev.shape[0])
    if np.abs(cur - prev).mean() < 1e-4:
        return {"tx": 0.0, "ty": 0.0, "zoom": 0.0, "rot": 0.0, "inliers": 1, "n": 1}   # identical frames: no movement, nothing to estimate
    if use_cv2:
        try:
            import cv2

            flow = cv2.calcOpticalFlowFarneback((prev * 255).astype(np.uint8), (cur * 255).astype(np.uint8), None, 0.5, 3, 15, 3, 5, 1.2, 0)
            pts, fl = dense_flow_samples(flow)
            return fit_similarity(pts, fl, size)
        except Exception:
            pass
    pts, fl = block_flow(prev, cur)
    return fit_similarity(pts, fl, size)


def classify(pairs: Sequence[Optional[Dict[str, float]]], size: Tuple[int, int], fps_eff: float, min_pairs: int = 2) -> Dict:
    """pairs: per-pair motion (pixels) between frames separated by 1/fps_eff seconds -> shot-level camera description (Spanish labels)."""
    ok = [p for p in pairs if p]
    if len(ok) < min_pairs:
        return {"label": "indeterminada", "labels": ["indeterminada"], "reason": "poca textura o pocos pares de fotogramas", "pairs": len(ok)}
    w, h = size
    pan_cam = np.array([-p["tx"] / w * fps_eff for p in ok])      # camera right positive
    tilt_cam = np.array([p["ty"] / h * fps_eff for p in ok])      # camera up positive
    zoom = np.array([p["zoom"] * fps_eff for p in ok])            # >0 zoom/dolly in (scale change per second)
    pan, tilt, z = float(np.median(pan_cam)), float(np.median(tilt_cam)), float(np.median(zoom))
    shake = float(np.sqrt(np.var(pan_cam) + np.var(tilt_cam)))
    labels: List[str] = []
    if shake >= SHAKE_T and shake > 2.5 * max(abs(pan), abs(tilt)):
        pan = tilt = z = 0.0          # erratic jitter around no net movement is hand-held shake, not a pan
        labels = ["temblor / cámara en mano"]
    if not labels and abs(pan) >= PAN_T:
        labels.append("paneo derecha" if pan > 0 else "paneo izquierda")
    if not labels and abs(tilt) >= TILT_T or (labels and labels[0].startswith("paneo") and abs(tilt) >= TILT_T):
        labels.append("tilt arriba" if tilt > 0 else "tilt abajo")
    if (not labels or labels[0] != "temblor / cámara en mano") and abs(z) >= ZOOM_T:
        labels.append("zoom/dolly in" if z > 0 else "zoom/dolly out")
    if not labels:
        labels = ["fija"]
    mags = {"paneo": abs(pan) / PAN_T, "tilt": abs(tilt) / TILT_T, "zoom": abs(z) / ZOOM_T}
    return {"label": labels[0] if len(labels) == 1 else "+".join(labels), "labels": labels, "pan_w_per_s": pan, "tilt_h_per_s": tilt, "zoom_per_s": z,
            "shake": shake, "dominant": max(mags, key=mags.get) if labels[0] not in ("fija",) else "fija", "pairs": len(ok)}
