"""Tiling for high-resolution generation / refinement with a model of fixed window size (the DiT is tied to 480x720 by its RoPE grid).

Three planner modes with an exact, documented cost (1440x960 frame, 720x480 window):
  no_overlap    4 passes   tiles abut, nothing is shared: seams can only be softened afterwards (`smooth_seams`, exposure ramp)
  seam_aware    4.5 passes grid A (2x2) and grid B (5 tiles centred on A's seams) on alternate denoising steps  <- recommended
  full_overlap  9 passes   3x3 with 50 % overlap: maximum quality
`overlap_pixels` exists only where an overlap is possible: it is the feather (blend ramp) width in seam_aware and the MINIMUM overlap in full_overlap
(a fixed window cannot give less than 50 % with 3 tiles per axis); passing it to no_overlap is an error.
Also: normalised windows that sum to exactly 1 at every covered pixel (raised cosine / Gaussian), split / blend, per-step MultiTileSync,
exposure matching in overlaps, seam smoothing for abutting tiles, a seam-visibility metric with a threshold that raises, and the cost of a plan
(passes, step-segments, relative VRAM, latent state size)."""
import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import numpy as np


@dataclass(frozen=True)
class Tile:
    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def w(self) -> int:
        return self.x1 - self.x0

    @property
    def h(self) -> int:
        return self.y1 - self.y0

    def norm(self, frame: Tuple[int, int]) -> Tuple[float, float, float, float]:
        W, H = frame
        return (self.x0 / W, self.y0 / H, self.x1 / W, self.y1 / H)   # the `tile_pos` the model's TileControl takes


MODES = ("no_overlap", "seam_aware", "full_overlap")
ALIASES = {"exact": "no_overlap", "alternate": "seam_aware", "overlap": "full_overlap"}   # names used by the first version
SEAM_OK = 1.5                                    # seam_visibility()["ratio"] above this is a visible line


class SeamTooVisible(RuntimeError):
    pass


@dataclass
class TilePlan:
    frame: Tuple[int, int]
    tile: Tuple[int, int]
    mode: str
    grids: List[List[Tile]]                      # one grid per phase (seam_aware has two)
    overlap: Tuple[int, int] = (0, 0)            # px between neighbouring tiles of grid 0
    feather: int = 0                             # blend ramp width in px
    warnings: List[str] = field(default_factory=list)

    @property
    def passes_per_step(self) -> float:
        return float(np.mean([len(g) for g in self.grids]))

    def grid(self, step: int) -> List[Tile]:
        return self.grids[step % len(self.grids)]


def _even(x: float) -> int:
    return int(round(x / 2.0)) * 2


def _snap(x: float, align: int) -> int:
    return int(round(x / align)) * align


def axis_starts(length: int, tile: int, min_overlap: int = 0, align: int = 2) -> List[int]:
    """Uniformly spaced tile starts covering [0, length] with at least `min_overlap` px between neighbours (tile size fixed).
    Starts are multiples of `align` (use 16 when tiles must map onto the VAE / patch grid)."""
    if length <= tile:
        return [0]
    n = max(2, math.ceil((length - min_overlap) / (tile - min_overlap))) if tile > min_overlap else 2
    return sorted({min(length - tile, _snap(i * (length - tile) / (n - 1), align)) for i in range(n)})


def _grid(xs: Sequence[int], ys: Sequence[int], tw: int, th: int) -> List[Tile]:
    return [Tile(x, y, x + tw, y + th) for y in ys for x in xs]


def plan_tiles(frame: Tuple[int, int], tile: Tuple[int, int], mode: str = "seam_aware", overlap_pixels: Optional[int] = None, align: int = 2) -> TilePlan:
    """mode: no_overlap | seam_aware | full_overlap (aliases exact / alternate / overlap). overlap_pixels: see the module docstring."""
    mode = ALIASES.get(mode, mode)
    (W, H), (tw, th) = frame, tile
    if mode not in MODES:
        raise ValueError(f"mode: {' | '.join(MODES)}")
    warn: List[str] = []
    if mode == "no_overlap" and overlap_pixels:
        raise ValueError("no_overlap no tiene solape: overlap_pixels solo vale en seam_aware (anchura del degradado) y full_overlap (solape mínimo)")
    if overlap_pixels is not None and overlap_pixels < 0:
        raise ValueError("overlap_pixels debe ser >= 0")
    if mode == "full_overlap":
        ov = overlap_pixels if overlap_pixels is not None else min(tw, th) // 2
        if ov >= min(tw, th) * 0.9:
            raise ValueError("overlap_pixels demasiado grande para la ventana")
        xs, ys = axis_starts(W, tw, min(ov, tw - 1), align), axis_starts(H, th, min(ov, th - 1), align)
    else:
        xs, ys = axis_starts(W, tw, 0, align), axis_starts(H, th, 0, align)
    grids = [_grid(xs, ys, tw, th)]
    if mode == "seam_aware":
        seam = lambda a, t, L: [max(0, min(L - t, _snap(b - t / 2, align))) for b in (s + t for s in a[:-1])]   # tile centred on every interior seam
        xs_s, ys_s = seam(xs, tw, W), seam(ys, th, H)
        b = {(x, y) for x in xs_s for y in ys} | {(x, y) for x in xs for y in ys_s} | {(x, y) for x in xs_s for y in ys_s}
        grids.append([Tile(x, y, x + tw, y + th) for x, y in sorted(b, key=lambda p: (p[1], p[0]))])
        warn.append("la cuadrícula B deja sin actualizar las esquinas en los pasos impares (conservan el valor anterior)")
    g0 = grids[0]
    real = (max(0, g0[0].x1 - g0[1].x0) if len(xs) > 1 else 0, max(0, g0[0].y1 - g0[len(xs)].y0) if len(ys) > 1 else 0) if len(g0) > 1 else (0, 0)
    if mode == "full_overlap" and (overlap_pixels or 0) < real[0]:
        warn.append(f"con ventana fija {tw}x{th} el solape mínimo posible con {len(xs)}x{len(ys)} piezas es {real[0]}x{real[1]} px (pediste {overlap_pixels or 0})")
    if mode == "no_overlap" and (W % tw or H % th):
        warn.append("el marco no es múltiplo de la ventana: las últimas piezas se solapan con las anteriores")
    feather = 0 if mode == "no_overlap" else (overlap_pixels if (mode == "seam_aware" and overlap_pixels) else max(8, (tw // 2 if mode == "seam_aware" else real[0] // 2)))
    return TilePlan((W, H), (tw, th), mode, grids, real, int(min(feather, tw // 2)), warn)


def tile_window(tile: Tile, frame: Tuple[int, int], feather: int, kind: str = "cosine") -> np.ndarray:
    """Raw 2-D weight [h, w]: a ramp of `feather` px on the sides that face another tile (raised cosine or Gaussian), 1 on frame-border sides."""
    W, H = frame
    if kind not in ("cosine", "gaussian"):
        raise ValueError("window: cosine | gaussian")

    def axis(n: int, lo_edge: bool, hi_edge: bool) -> np.ndarray:
        r = np.ones(n)
        if feather > 0:
            u = np.clip((np.arange(n) + 0.5) / feather, 0, 1)
            ramp = 0.5 - 0.5 * np.cos(np.pi * u) if kind == "cosine" else 1 - np.exp(-((np.arange(n) + 0.5) / (feather / 2.5)) ** 2)
            if not lo_edge:
                r = np.minimum(r, ramp)
            if not hi_edge:
                r = np.minimum(r, ramp[::-1])
        return np.maximum(r, 1e-4)

    return np.outer(axis(tile.h, tile.y0 == 0, tile.y1 == H), axis(tile.w, tile.x0 == 0, tile.x1 == W))


def normalized_windows(grid: Sequence[Tile], frame: Tuple[int, int], feather: int, kind: str = "cosine") -> List[np.ndarray]:
    """One weight map per tile such that the weights of all tiles sum to EXACTLY 1 at every pixel the grid covers (0 elsewhere)."""
    W, H = frame
    raw = [tile_window(t, (W, H), feather, kind) for t in grid]
    tot = np.zeros((H, W))
    for t, w in zip(grid, raw):
        tot[t.y0 : t.y1, t.x0 : t.x1] += w
    return [w / tot[t.y0 : t.y1, t.x0 : t.x1] for t, w in zip(grid, raw)]


def split(frame: np.ndarray, tiles: Sequence[Tile]) -> List[np.ndarray]:
    return [frame[t.y0 : t.y1, t.x0 : t.x1] for t in tiles]


def blend(parts: Sequence[np.ndarray], tiles: Sequence[Tile], frame_hw: Tuple[int, int], feather: int = 16,
          fallback: Optional[np.ndarray] = None, kind: str = "cosine") -> np.ndarray:
    """Normalised-window blend of tile images [h,w,C] into the full frame [H,W,C]; pixels no tile covers keep `fallback` (or 0)."""
    H, W = frame_hw
    c = parts[0].shape[2:] if parts[0].ndim > 2 else ()
    out = np.zeros((H, W) + c, np.float64)
    cover = np.zeros((H, W), bool)
    for p, t, w in zip(parts, tiles, normalized_windows(tiles, (W, H), feather, kind)):
        out[t.y0 : t.y1, t.x0 : t.x1] += p * (w[..., None] if c else w)
        cover[t.y0 : t.y1, t.x0 : t.x1] = True
    if fallback is not None:
        out = np.where(cover[(...,) + (None,) * len(c)], out, fallback)
    return out


def blend_batch(parts: Sequence[np.ndarray], tiles: Sequence[Tile], frame_hw: Tuple[int, int], feather: int = 16, kind: str = "cosine") -> np.ndarray:
    """`blend` for a whole video at once: parts[k] is [T, h, w, C]; windows are computed once. -> [T, H, W, C] float."""
    H, W = frame_hw
    T_, C = parts[0].shape[0], parts[0].shape[3]
    out = np.zeros((T_, H, W, C), np.float64)
    for p, t, w in zip(parts, tiles, normalized_windows(tiles, (W, H), feather, kind)):
        out[:, t.y0 : t.y1, t.x0 : t.x1] += p * w[None, :, :, None]
    return out


class MultiTileSync:
    """Per-step synchronisation of tiles during denoising: tiles -> one full latent (blended) -> tiles of the NEXT phase grid."""

    def __init__(self, plan: TilePlan, feather: int = 16):
        self.plan, self.feather, self.state = plan, feather, None

    def sync(self, tile_latents: Sequence[np.ndarray], step: int) -> np.ndarray:
        W, H = self.plan.frame
        self.state = blend(tile_latents, self.plan.grid(step), (H, W), self.feather, fallback=self.state)
        return self.state

    def tiles_for(self, step: int) -> List[np.ndarray]:
        return split(self.state, self.plan.grid(step))


def match_exposure(parts: Sequence[np.ndarray], tiles: Sequence[Tile], ridge: float = 1e-3, max_samples: int = 4000, seed: int = 0):
    """Per-tile, per-channel gain/bias so that overlapping tiles agree (the usual tile artefact: a step in exposure at the seam).
    Tile 0 is the anchor. -> (list of corrected tiles, list of (gain[C], bias[C]))."""
    n = len(parts)
    c = parts[0].shape[-1] if parts[0].ndim == 3 else 1
    P = [p.reshape(p.shape[0], p.shape[1], c).astype(np.float64) for p in parts]
    rng = np.random.default_rng(seed)
    gains, biases = np.ones((n, c)), np.zeros((n, c))
    for ch in range(c):
        rows, rhs = [], []
        for i in range(n):
            for j in range(i + 1, n):
                x0, y0, x1, y1 = max(tiles[i].x0, tiles[j].x0), max(tiles[i].y0, tiles[j].y0), min(tiles[i].x1, tiles[j].x1), min(tiles[i].y1, tiles[j].y1)
                if x1 <= x0 or y1 <= y0:
                    continue
                a = P[i][y0 - tiles[i].y0 : y1 - tiles[i].y0, x0 - tiles[i].x0 : x1 - tiles[i].x0, ch].ravel()
                b = P[j][y0 - tiles[j].y0 : y1 - tiles[j].y0, x0 - tiles[j].x0 : x1 - tiles[j].x0, ch].ravel()
                idx = rng.choice(len(a), min(len(a), max_samples), replace=False)
                for xa, xb in zip(a[idx], b[idx]):
                    r = np.zeros(2 * n)
                    r[i], r[n + i], r[j], r[n + j] = xa, 1.0, -xb, -1.0
                    rows.append(r)
                    rhs.append(0.0)
        if not rows:
            continue
        A, y = np.array(rows), np.array(rhs)
        theta0 = np.concatenate([np.ones(n), np.zeros(n)])
        lam = np.full(2 * n, ridge * len(A))
        lam[[0, n]] = 1e6 * len(A)                     # anchor tile 0
        sol = np.linalg.solve(A.T @ A + np.diag(lam), A.T @ y + lam * theta0)
        gains[:, ch], biases[:, ch] = sol[:n], sol[n:]
    out = [np.clip(p * g + b, 0, 255 if parts[0].dtype == np.uint8 or parts[0].max() > 1.5 else 1.0).reshape(parts[k].shape) for k, (p, g, b) in enumerate(zip(P, gains, biases))]
    return out, list(zip(gains, biases))


def seam_positions(plan: TilePlan) -> Tuple[List[int], List[int]]:
    """Interior x / y coordinates where tiles of the first grid meet or overlap (centre of the overlap)."""
    W, H = plan.frame
    g = plan.grids[0]
    xs = sorted({(a.x1 + b.x0) // 2 for a in g for b in g if b.x0 > a.x0 and b.x0 <= a.x1 and a.y0 == b.y0} | {t.x1 for t in g if 0 < t.x1 < W and plan.overlap[0] == 0})
    ys = sorted({(a.y1 + b.y0) // 2 for a in g for b in g if b.y0 > a.y0 and b.y0 <= a.y1 and a.x0 == b.x0} | {t.y1 for t in g if 0 < t.y1 < H and plan.overlap[1] == 0})
    return xs, ys


def smooth_seams(frame: np.ndarray, xs: Sequence[int], ys: Sequence[int], band: int = 24) -> np.ndarray:
    """For ABUTTING tiles (no_overlap): nothing is shared, so the only thing that can be fixed is the exposure step across each seam. The step (beyond
    the local gradient) is measured SEPARATELY for every stretch of a seam between two crossing seams (neighbouring tiles can disagree in opposite
    directions along one line) and removed with a linear ramp over `band` px on both sides. It cannot fix a structural mismatch."""
    f = np.asarray(frame, np.float64).copy()
    H, W, C = f.shape[0], f.shape[1], f.shape[2] if f.ndim == 3 else 1
    f = f.reshape(H, W, C)
    mean = lambda a: a.reshape(-1, C).mean(0)
    ramp = lambda k: 1.0 - k / band
    row_edges, col_edges = [0] + sorted(ys) + [H], [0] + sorted(xs) + [W]
    for p in xs:                                                           # vertical seams, one correction per row stretch
        if not 2 <= p <= W - 2:
            continue
        for r0, r1 in zip(row_edges[:-1], row_edges[1:]):
            c = lambda k: mean(f[r0:r1, k])
            d = (c(p) - c(p - 1)) - 0.5 * ((c(p + 1) - c(p)) + (c(p - 1) - c(p - 2)))
            for k in range(band):
                if p + k < W:
                    f[r0:r1, p + k] -= 0.5 * d * ramp(k)
                if p - 1 - k >= 0:
                    f[r0:r1, p - 1 - k] += 0.5 * d * ramp(k)
    for p in ys:                                                           # horizontal seams, one correction per column stretch
        if not 2 <= p <= H - 2:
            continue
        for c0, c1 in zip(col_edges[:-1], col_edges[1:]):
            r = lambda k: mean(f[k, c0:c1])
            d = (r(p) - r(p - 1)) - 0.5 * ((r(p + 1) - r(p)) + (r(p - 1) - r(p - 2)))
            for k in range(band):
                if p + k < H:
                    f[p + k, c0:c1] -= 0.5 * d * ramp(k)
                if p - 1 - k >= 0:
                    f[p - 1 - k, c0:c1] += 0.5 * d * ramp(k)
    return f.reshape(np.asarray(frame).shape)


def check_seams(result: dict, threshold: float = SEAM_OK) -> dict:
    """Raise SeamTooVisible when seam_visibility(...)['ratio'] exceeds the threshold (automatic gate for pipelines and tests)."""
    if result.get("ratio", 1.0) > threshold:
        raise SeamTooVisible(f"costura visible: razón {result['ratio']:.2f} > umbral {threshold}")
    return result


def seam_visibility(frames: np.ndarray, xs: Sequence[int], ys: Sequence[int], guard: int = 3) -> dict:
    """Is there a visible line at the seams? Ratio of the mean pixel step across a seam to the mean step elsewhere (1 = invisible,
    > 1.5 visible). frames [T,H,W,C] or [H,W,C]."""
    f = np.asarray(frames, np.float64)
    f = f[None] if f.ndim == 3 else f
    t, H, W = f.shape[:3]
    dx = np.abs(np.diff(f, axis=2)).mean(axis=(0, 1, 3))    # [W-1]: step between column x and x+1
    dy = np.abs(np.diff(f, axis=1)).mean(axis=(0, 2, 3))    # [H-1]
    out = {}
    for name, d, pos in (("vertical", dx, xs), ("horizontal", dy, ys)):
        if not len(pos):
            continue
        near = np.zeros(len(d), bool)
        for p in pos:
            near[max(0, p - 1 - guard) : p + guard] = True
        base = d[~near].mean() if (~near).any() else d.mean()
        out[name] = float(np.mean([d[min(len(d) - 1, p - 1)] for p in pos]) / (base + 1e-9))
    out["ratio"] = max(out.values()) if out else 1.0
    return out


def cost(plan: TilePlan, seconds: float, steps: int, segment_s: float = 3.0, base_vram_gb: Optional[float] = None, batch_tiles: int = 1,
         fps: int = 16, latent_channels: int = 16, vae_stride: int = 8, bytes_per_el: int = 2) -> dict:
    """Cost of stage B in tile passes. One pass of a tile costs the same as one base pass (same window). Tiles run sequentially unless
    `batch_tiles` > 1 (then wall time / batch, VRAM x batch). `base_vram_gb` is YOUR measured peak of one base pass; nothing is assumed.
    `state_gb` is the full-frame latent the synchronisation keeps (all latent frames x channels x H/8 x W/8)."""
    seg = seconds / segment_s
    pps = plan.passes_per_step
    t_lat = int(round(seconds * 4)) + 1                        # 4 latent frames per second (+1) at 16 fps
    W, H = plan.frame
    return {"mode": plan.mode, "tiles": [len(g) for g in plan.grids], "passes_per_step": pps, "relative_to_base": pps, "total_tile_passes": pps * steps,
            "step_segments": pps * steps * seg, "base_step_segments": steps * seg, "wall_relative": pps / max(1, batch_tiles),
            "vram_gb": None if base_vram_gb is None else base_vram_gb * max(1, batch_tiles),
            "state_gb": t_lat * latent_channels * (H // vae_stride) * (W // vae_stride) * bytes_per_el / 1e9}
