"""Control data on disk (numpy only, so the studio can build it without torch).

One `.npz` per video:  labels uint8 [T, Hp, Wp]  (0 background, k = character id)         - optional
                       feats  float16 [T, I+1, K] (per character per frame; slot 0 = bg)    - optional
                       frame_feats float16 [T, F]  (global per frame: see FRAME_FEATS)       - optional
                       tile_pos float16 [4]       (x0, y0, x1, y1 of this tile inside the full frame, 0..1) - optional
T = latent frames (4 per second, +1), Hp x Wp = the patch grid (30 x 45 for 480x720)."""
from typing import Dict, Optional, Sequence

import numpy as np

FRAME_FEATS = ("speech", "loudness", "valence", "arousal")   # frame_dim = 4
LATENT_FPS = 4.0                                              # 16 fps video, 4 pixel frames per latent frame


def latent_frames(seconds: float) -> int:
    return int(round(seconds * LATENT_FPS)) + 1


def labels_to_latent(labels: np.ndarray, t_latent: int, grid=(30, 45)) -> np.ndarray:
    """Pixel-frame label maps [Tpix, H, W] -> [T_latent, Hp, Wp] by nearest sampling (latent t <-> pixel frame 4t)."""
    tp, h, w = labels.shape
    ti = np.minimum(np.arange(t_latent) * 4, tp - 1)
    ys = np.minimum((np.arange(grid[0]) * h) // grid[0] + h // (2 * grid[0]), h - 1)
    xs = np.minimum((np.arange(grid[1]) * w) // grid[1] + w // (2 * grid[1]), w - 1)
    return labels[ti][:, ys][:, :, xs].astype(np.uint8)


def frame_feats_from_audio(wave: np.ndarray, sr: int, t_latent: int, speech: Sequence[tuple] = (), valence: Optional[np.ndarray] = None,
                           arousal: Optional[np.ndarray] = None, loudness_ref: Optional[float] = None) -> np.ndarray:
    """[T_latent, 4]: speech activity (0/1 from (start, end) intervals), loudness (RMS in a 0.25 s window / reference), valence,
    arousal (per-latent-frame series or 0). The same function serves real audio (training) and regenerated voices (generation)."""
    out = np.zeros((t_latent, len(FRAME_FEATS)), np.float32)
    half = int(0.125 * sr)
    rms = np.zeros(t_latent)
    for t in range(t_latent):
        c = int(t / LATENT_FPS * sr)
        seg = wave[max(0, c - half) : c + half]
        rms[t] = float(np.sqrt((seg.astype(np.float64) ** 2).mean())) if len(seg) else 0.0
        sec = t / LATENT_FPS
        out[t, 0] = 1.0 if any(a <= sec <= b for a, b in speech) else 0.0
    ref = loudness_ref or (np.percentile(rms, 95) + 1e-9)
    out[:, 1] = np.clip(rms / ref, 0, 1.5)
    if valence is not None:
        out[:, 2] = np.asarray(valence)[:t_latent]
    if arousal is not None:
        out[:, 3] = np.asarray(arousal)[:t_latent]
    return out


def character_feats(per_id: Dict[int, np.ndarray], max_characters: int, t_latent: int) -> np.ndarray:
    """per_id: {character id: array [T, K]} -> [T, I+1, K] (slot 0 = background, zeros)."""
    k = next(iter(per_id.values())).shape[1] if per_id else 1
    out = np.zeros((t_latent, max_characters + 1, k), np.float32)
    for cid, a in per_id.items():
        if 1 <= cid <= max_characters:
            out[: len(a), cid] = a[:t_latent]
    return out


def save_control(path: str, labels: Optional[np.ndarray] = None, feats: Optional[np.ndarray] = None, frame_feats: Optional[np.ndarray] = None,
                 tile_pos: Optional[np.ndarray] = None) -> None:
    import os

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    kw = {k: v for k, v in (("labels", labels), ("feats", feats), ("frame_feats", frame_feats), ("tile_pos", tile_pos)) if v is not None}
    if not kw:
        raise ValueError("nothing to save")
    np.savez_compressed(path + ".tmp.npz", **{k: (v.astype(np.uint8) if k == "labels" else v.astype(np.float16)) for k, v in kw.items()})
    os.replace(path + ".tmp.npz", path)


def load_control(path: str) -> Dict[str, np.ndarray]:
    with np.load(path) as z:
        return {k: (z[k].astype(np.int64) if k == "labels" else z[k].astype(np.float32)) for k in z.files}


def save_loss_mask(path: str, mask: np.ndarray) -> None:
    """mask float [T_latent, H, W] in {0, 1}; stored as uint8."""
    import os

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    np.savez_compressed(path, mask=(np.asarray(mask) > 0.5).astype(np.uint8))


def load_loss_mask(path: str) -> np.ndarray:
    with np.load(path) as z:
        return z["mask"].astype(np.float32)
