"""Cheap, CPU-only video quality proxies, a paired A/B comparison and best-of-N selection.

Why: claims like "this setting makes the generator better" must be tested on the same seeds. This gives the harness: generate the same
prompts with the same seeds under two settings (e.g. enhance_weight 0 vs 2, step cache on/off, a fused style), then `ab` tells you if the
difference is larger than the noise. These proxies are NOT human judgement and not VBench: they only see temporal flicker, motion
regularity, frame-to-frame correlation, colour drift and sharpness. Selection among candidates of one prompt (a small Video-T1-style
test-time search: more seeds, keep the best) uses relative z-scores of the directional metrics."""
import json
import os
from typing import Dict, List, Optional, Sequence

import numpy as np

# metric -> direction: +1 higher is better, -1 lower is better, 0 informational only (over-sharpening is not "better")
DIRECTION = {"flicker": -1, "stutter": -1, "frame_corr": +1, "color_drift": -1, "sharpness": 0}
LABEL = {"flicker": "parpadeo de brillo", "stutter": "irregularidad del movimiento", "frame_corr": "correlación entre fotogramas",
         "color_drift": "deriva de color", "sharpness": "nitidez (solo informativa)"}


def load_frames(path: str, max_side: int = 160, max_frames: Optional[int] = None) -> np.ndarray:
    """Decoded RGB frames [T,H,W,3] float32 in 0..1, downsampled by striding so the longest side is ~max_side."""
    import imageio

    r = imageio.get_reader(path, "ffmpeg")
    out = []
    for i, f in enumerate(r):
        if max_frames and i >= max_frames:
            break
        st = max(1, max(f.shape[:2]) // max_side)
        out.append(f[::st, ::st].astype(np.float32) / 255.0)
    r.close()
    return np.stack(out) if out else np.zeros((0, 1, 1, 3), np.float32)


def metrics(frames: np.ndarray) -> Dict[str, float]:
    t = len(frames)
    if t < 4:
        raise ValueError("hacen falta al menos 4 fotogramas")
    g = frames.mean(-1)                                           # luminance proxy [T,H,W]
    lum = g.reshape(t, -1).mean(1)
    flicker = float(np.abs(np.diff(lum, 2)).mean() / (lum.mean() + 1e-6))   # high-frequency global brightness change
    gn = g / (lum[:, None, None] + 1e-6)                              # remove per-frame gain so brightness flicker does not masquerade as motion
    e = np.abs(np.diff(gn, 1, axis=0)).reshape(t - 1, -1).mean(1)    # motion energy per frame step
    stutter = float(e.std() / e.mean()) if e.mean() > 1e-4 else 0.0   # coefficient of variation: steady motion ~0, bursts / repeated frames high
    a, b = g[:-1].reshape(t - 1, -1), g[1:].reshape(t - 1, -1)
    a, b = a - a.mean(1, keepdims=True), b - b.mean(1, keepdims=True)
    corr = (a * b).sum(1) / (np.sqrt((a ** 2).sum(1) * (b ** 2).sum(1)) + 1e-9)
    mean_rgb = frames.reshape(t, -1, 3).mean(1)
    drift = float((mean_rgb.std(0) / (mean_rgb.mean(0) + 1e-6)).max())
    lap = (-4 * g[:, 1:-1, 1:-1] + g[:, :-2, 1:-1] + g[:, 2:, 1:-1] + g[:, 1:-1, :-2] + g[:, 1:-1, 2:])
    return {"flicker": flicker, "stutter": stutter, "frame_corr": float(corr.mean()), "color_drift": drift, "sharpness": float(lap.var(axis=(1, 2)).mean())}


def score_video(path: str, **kw) -> Dict[str, float]:
    return metrics(load_frames(path, **kw))


def bootstrap_ci(d: np.ndarray, n: int = 4000, seed: int = 0):
    rng = np.random.default_rng(seed)
    means = np.array([rng.choice(d, len(d)).mean() for _ in range(n)])
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def compare(a: Sequence[Dict[str, float]], b: Sequence[Dict[str, float]], min_pairs: int = 5) -> Dict[str, dict]:
    """Paired comparison: a[i] and b[i] are the SAME prompt+seed under settings A and B. Per metric: mean(B-A), 95 % bootstrap CI, verdict."""
    if len(a) != len(b) or not a:
        raise ValueError("A y B deben tener el mismo número (>0) de pares")
    out = {}
    for m, dirn in DIRECTION.items():
        d = np.array([y[m] - x[m] for x, y in zip(a, b)])
        lo, hi = bootstrap_ci(d) if len(d) > 1 else (float(d[0]), float(d[0]))
        if len(d) < min_pairs:
            v = f"insuficiente (n={len(d)} < {min_pairs})"
        elif dirn == 0:
            v = "informativa"
        elif lo > 0 or hi < 0:
            v = "B mejor" if (d.mean() * dirn) > 0 else "B peor"
        else:
            v = "sin diferencia clara"
        out[m] = {"mean_diff": float(d.mean()), "ci95": [lo, hi], "verdict": v, "n": len(d), "label": LABEL[m]}
    return out


def pick_best(cands: Sequence[Dict[str, float]]) -> int:
    """Index of the best candidate of ONE prompt: mean of directional z-scores across candidates (needs >=2; ties -> first)."""
    if len(cands) < 2:
        return 0
    z = np.zeros(len(cands))
    for m, dirn in DIRECTION.items():
        if dirn == 0:
            continue
        x = np.array([c[m] for c in cands])
        if x.std() < max(1e-8, 1e-3 * abs(x.mean())):
            continue  # all candidates equal on this metric: no information (and dividing by ~0 would only add noise)
        z += dirn * (x - x.mean()) / x.std()
    return int(np.argmax(z))


def report_es(cmp: Dict[str, dict], name_a: str = "A", name_b: str = "B") -> str:
    L = [f"# Comparación {name_a} → {name_b}", "", f"Pares (mismo prompt y semilla): {next(iter(cmp.values()))['n']}. Diferencia = {name_b} − {name_a}.", "",
         "| Métrica | Diferencia media | IC95 | Veredicto |", "|---|---|---|---|"]
    L += [f"| {v['label']} | {v['mean_diff']:+.4f} | [{v['ci95'][0]:+.4f}, {v['ci95'][1]:+.4f}] | {v['verdict']} |" for v in cmp.values()]
    L += ["", "Son proxies baratos (parpadeo, tirones, correlación, deriva de color, nitidez): no sustituyen a una revisión humana ni a VBench."]
    return "\n".join(L) + "\n"


def find_videos(root: str) -> Dict[str, str]:
    out = {}
    for dp, _, fs in os.walk(root):
        for f in fs:
            if f.lower().endswith(".mp4"):
                out[os.path.relpath(os.path.join(dp, f), root)] = os.path.join(dp, f)
    return out


# ---- temporal consistency by flow residual, and refinement vs the Lanczos baseline ----------------------------------------------------
def _gray(f: np.ndarray) -> np.ndarray:
    f = np.asarray(f, np.float32)
    return f.mean(-1) if f.ndim == 3 else f


def temporal_warp_error(frames: np.ndarray, max_side: int = 160, radius: int = 3) -> float:
    """Optical-flow residual: for every consecutive pair, estimate the flow cur->prev (block matching, nearest-filled to a dense field),
    warp prev onto cur and measure |cur - warped|. Lower = more temporally consistent (flicker and re-drawn detail raise it)."""
    from scipy.interpolate import NearestNDInterpolator
    from scipy.ndimage import map_coordinates

    from studio.analysis.camera import block_flow

    f = np.asarray(frames, np.float32)
    if f.max() > 1.5:
        f = f / 255.0
    st = max(1, max(f.shape[1:3]) // max_side)
    g = np.stack([_gray(x[::st, ::st]) for x in f])
    t, h, w = g.shape
    if t < 2:
        raise ValueError("hacen falta al menos 2 fotogramas")
    gy, gx = max(2, (h - 2 * radius) // 8), max(2, (w - 2 * radius) // 8)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    errs = []
    for a, b in zip(g[:-1], g[1:]):
        pts, fl = block_flow(b, a, grid=(gy, gx), radius=radius, min_std=0.005)    # where did each block of `b` come from in `a`?
        if len(pts) >= 4:
            dense = NearestNDInterpolator(pts, fl)(np.stack([xx.ravel(), yy.ravel()], 1)).reshape(h, w, 2)
        else:
            dense = np.zeros((h, w, 2))
        warped = map_coordinates(a, [yy + dense[..., 1], xx + dense[..., 0]], order=1, mode="nearest")
        errs.append(float(np.abs(b - warped).mean()))
    return float(np.mean(errs))


def _down(f: np.ndarray, k: int) -> np.ndarray:
    h, w = f.shape[:2]
    return f[: h // k * k, : w // k * k].reshape(h // k, k, w // k, k, *f.shape[2:]).mean((1, 3))


def compare_to_baseline(refined: np.ndarray, baseline: np.ndarray, factor: int = 4) -> Dict[str, float]:
    """Refined high-res frames [T,H,W,3] (0..255 or 0..1) vs the Lanczos-upsampled stage-A baseline of the same size:
      lowfreq_psnr_db      did the refinement stay faithful to stage A (PSNR of both at 1/factor resolution; > 30 dB is close)
      temporal_ratio       temporal_warp_error(refined) / temporal_warp_error(baseline): > 1.15 means it flickers more than Lanczos
      sharpness_ratio      Laplacian variance refined / baseline (> 1 = more fine detail; informational)"""
    r, b = (np.asarray(x, np.float32) / (255.0 if np.asarray(x).max() > 1.5 else 1.0) for x in (refined, baseline))
    if r.shape != b.shape:
        raise ValueError("refined y baseline deben tener el mismo tamaño")
    mse = float(np.mean([(_down(x, factor) - _down(y, factor)) ** 2 for x, y in zip(r, b)]))
    sh = lambda a: float(np.mean([(-4 * _gray(x)[1:-1, 1:-1] + _gray(x)[:-2, 1:-1] + _gray(x)[2:, 1:-1] + _gray(x)[1:-1, :-2] + _gray(x)[1:-1, 2:]).var() for x in a]))
    te_r, te_b = temporal_warp_error(r), temporal_warp_error(b)
    return {"lowfreq_psnr_db": float(10 * np.log10(1.0 / max(mse, 1e-12))), "temporal_ratio": te_r / max(te_b, 1e-9), "temporal_error_refined": te_r,
            "temporal_error_baseline": te_b, "sharpness_ratio": sh(r) / max(sh(b), 1e-12)}
