"""Two-stage high resolution: stage A (the DiT at its native 480x720, untouched) -> stage B (upsample, refine in native-size tiles, blend).

Refiners are SEPARATE and declare the stage they belong to (`REFINERS`):
  identity          stage B  the Lanczos-upsampled crop (baseline)
  esrgan            stage B  post-process: a super-resolution network on the LOW-RES region of every tile (tiled Real-ESRGAN)
  generative        stage B  re-noising + regeneration conditioned on the low-res video, in latent space, tiles synchronised every step
                             (hypercartoon/models/cogvideo/refine.py; needs the DiT + GPU: run through refine_video.py)
  enhance_a_video   stage A  NOT a refiner of a finished video: it acts inside the base generation (`--eval.enhance_weight`); `stage_a_flags()`
Planner modes (studio/tiling.py): no_overlap (4 passes), seam_aware (~4.5, recommended for the generative refiner), full_overlap (9).
For post-process refiners there is no denoising loop to alternate grids over, so `seam_aware` composes the union of both grids (= the 3x3 set).
Blending uses normalised windows; exposure matching is mandatory (an exposure ramp across the seams for no_overlap); a seam gate raises
SeamTooVisible before the whole video is written unless `allow_visible_seams`."""
import os
import subprocess
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from studio import tiling as T


class StageError(ValueError):
    """A refiner was asked to run in the wrong stage."""


@dataclass(frozen=True)
class RefinerSpec:
    kind: str
    stage: str
    summary: str


REFINERS: Dict[str, RefinerSpec] = {
    "identity": RefinerSpec("identity", "B", "Lanczos-upsampled crop (baseline, no network)"),
    "esrgan": RefinerSpec("esrgan", "B", "post-process Real-ESRGAN on the low-res region of each tile"),
    "generative": RefinerSpec("generative", "B", "re-noising + regeneration conditioned on the low-res video (DiT, latent space, GPU)"),
    "enhance_a_video": RefinerSpec("enhance_a_video", "A", "attention enhancement inside the BASE generation (eval.enhance_weight), not a post refiner"),
}


def stage_a_flags(weight: float = 2.0) -> List[str]:
    """Flags to add to the stage-A generation command to use Enhance-A-Video-style enhancement."""
    if weight <= 0:
        raise ValueError("enhance weight debe ser > 0")
    return [f"--eval.enhance_weight={weight:g}"]


class IdentityRefiner:
    name = "identity"

    def refine(self, lr: np.ndarray, up: np.ndarray, tile: T.Tile, frame_index: int) -> np.ndarray:
        return up[tile.y0 : tile.y1, tile.x0 : tile.x1]


class UpscalerRefiner:
    """Super-resolves the low-res region that corresponds to the tile (so it sees real source pixels, not an interpolation)."""

    def __init__(self, upscaler, scale: float):
        self.up, self.scale, self.name = upscaler, scale, "esrgan"

    def refine(self, lr: np.ndarray, up: np.ndarray, tile: T.Tile, frame_index: int) -> np.ndarray:
        s = self.scale
        region = lr[int(tile.y0 / s) : int(round(tile.y1 / s)), int(tile.x0 / s) : int(round(tile.x1 / s))]
        out = np.asarray(self.up.upscale(region, s))
        if out.shape[:2] != (tile.h, tile.w):
            from PIL import Image

            out = np.asarray(Image.fromarray(out).resize((tile.w, tile.h), Image.LANCZOS))
        return out


def _resize(frame: np.ndarray, size) -> np.ndarray:
    from PIL import Image

    return np.asarray(Image.fromarray(frame).resize(size, Image.LANCZOS))


class GenerativeRefiner:
    """Stage B generative refinement. `backend` provides (see hypercartoon.models.cogvideo.refine.DitRefineBackend):
         vae_stride, latent_channels, schedule() -> [alphas_sqrt..., 1.0], encode(frames uint8 [T,h,w,3]) -> [T_lat,C,h/8,w/8],
         decode(latent) -> uint8 [T,H,W,3], denoise(x [T_lat,C,h,w], step_index, tile_pos_norm) -> x0
       Steps: pad time to 4k+1, Lanczos upsample, encode each tile of grid 0 and assemble the full-frame reference latent, re-noise at `strength`,
       denoise tile by tile with per-step synchronisation (grids alternate in seam_aware) and low-frequency consistency to the reference, decode
       each tile, blend with normalised windows, apply the exposure gains measured on the first frame."""

    name = "generative"
    video_level = True

    def __init__(self, backend, strength: float = 0.35, lam: float = 0.8, factor: int = 4, mode: str = "seam_aware", overlap_pixels: Optional[int] = None,
                 window: str = "cosine", seed: int = 0):
        self.backend, self.strength, self.lam, self.factor = backend, strength, lam, factor
        self.mode, self.overlap_pixels, self.window, self.seed = mode, overlap_pixels, window, seed
        self.info: Dict = {}

    def refine_video(self, lr_frames: np.ndarray, scale: float, progress: Optional[Callable] = None) -> np.ndarray:
        import torch

        from hypercartoon.models.cogvideo import refine as R

        be, n = self.backend, len(lr_frames)
        stride = be.vae_stride
        pad = (-(n - 1)) % 4
        frames = np.concatenate([lr_frames, np.repeat(lr_frames[-1:], pad, 0)]) if pad else lr_frames      # the VAE wants 4k+1 frames
        h, w = frames.shape[1:3]
        TW, TH = T._even(w * scale), T._even(h * scale)
        up = np.stack([_resize(f, (TW, TH)) for f in frames])
        align = 2 * stride                                                                                 # patch (2) x VAE stride: tiles land on the token grid
        plan = T.plan_tiles((TW, TH), (w, h), self.mode, self.overlap_pixels, align=align)
        Wl, Hl = TW // stride, TH // stride
        lat = lambda t: T.Tile(t.x0 // stride, t.y0 // stride, t.x1 // stride, t.y1 // stride)
        fe = max(1, plan.feather // stride)
        grids_px = plan.grids
        grids = []
        for g in grids_px:
            lg = [lat(t) for t in g]
            ws = T.normalized_windows(lg, (Wl, Hl), fe, self.window)
            grids.append([((t.x0, t.y0, t.x1, t.y1), torch.from_numpy(wt).float()[None, None]) for t, wt in zip(lg, ws)])
        # reference latent: encode every tile of grid 0 (they cover the frame) and blend
        g0 = grids_px[0]
        enc = [be.encode(torch.from_numpy(up[:, t.y0 : t.y1, t.x0 : t.x1])) for t in g0]
        ref = R.assemble(enc, [(lat(t).x0, lat(t).y0, lat(t).x1, lat(t).y1) for t in g0], [wt for _, wt in grids[0]], (Hl, Wl))
        alphas = be.schedule()
        gen = torch.Generator(device=ref.device).manual_seed(self.seed)

        def den(x, i, rect):
            return be.denoise(x, i, (rect[0] / Wl, rect[1] / Hl, rect[2] / Wl, rect[3] / Hl))

        out = R.refine_latent_tiled(ref, grids, den, alphas, self.strength, self.lam, self.factor, gen,
                                    callback=lambda k, tot: progress and progress(0.9 * k / max(tot, 1)))
        parts = [be.decode(out[..., t.y0 // stride : t.y1 // stride, t.x0 // stride : t.x1 // stride]).numpy().astype(np.float64) for t in g0]
        if len(g0) > 1:                                                                                    # exposure gains from the first frame, applied to the whole video
            _, gb = T.match_exposure([p[0] for p in parts], g0)
            parts = [np.clip(p * g + b, 0, 255) for p, (g, b) in zip(parts, gb)]
        video = np.clip(T.blend_batch(parts, g0, (TH, TW), max(8, plan.feather), self.window), 0, 255).astype(np.uint8)
        self.info = {"tiles": [len(g) for g in grids_px], "strength": self.strength, "lam": self.lam, "mode": plan.mode, "latent_frames": int(ref.shape[0])}
        return video[:n]


def make_refiner(kind: str, scale: float = 2.0, upscaler=None, backend=None, **opts):
    """Build a stage-B refiner. enhance_a_video is rejected here on purpose: it belongs to stage A."""
    if kind not in REFINERS:
        raise ValueError(f"refinador: {', '.join(REFINERS)}")
    if REFINERS[kind].stage == "A":
        raise StageError(f"{kind} actúa DENTRO de la generación base (fase A), no sobre un vídeo ya generado: añade {' '.join(stage_a_flags(opts.get('weight', 2.0)))} al comando de generación")
    if kind == "identity":
        return IdentityRefiner()
    if kind == "esrgan":
        if upscaler is None:
            raise ValueError("esrgan necesita un upscaler (studio.finish.RealESRGANUpscaler)")
        return UpscalerRefiner(upscaler, scale)
    if backend is None:
        raise ValueError("generative necesita un backend (hypercartoon.models.cogvideo.refine.DitRefineBackend) y GPU: usa refine_video.py")
    return GenerativeRefiner(backend, **opts)


def union_tiles(plan: T.TilePlan) -> List[T.Tile]:
    seen, out = set(), []
    for g in plan.grids:
        for t in g:
            if t not in seen:
                seen.add(t)
                out.append(t)
    return out


def hires_video(src: str, dst: str, scale: float = 2.0, mode: str = "seam_aware", overlap_pixels: Optional[int] = None, refiner=None,
                exposure_matching: bool = True, allow_visible_seams: bool = False, seam_threshold: float = T.SEAM_OK, window: str = "cosine",
                crf: int = 16, progress: Optional[Callable] = None, dry: bool = False, compare: bool = True, steps: int = 25,
                base_vram_gb: Optional[float] = None) -> Dict:
    """src (native resolution) -> dst at `scale` x, refined in native-size tiles. Returns a report with plan, cost and metrics."""
    import imageio

    from studio import quality as Q
    from studio.finish import _ffmpeg, probe

    if not exposure_matching and not allow_visible_seams:
        raise ValueError("exposure_matching=False deja costuras visibles: es obligatorio salvo allow_visible_seams=True")
    info = probe(src)
    W, H = info["width"], info["height"]
    TW, TH = T._even(W * scale), T._even(H * scale)
    refiner = refiner or IdentityRefiner()
    video_level = getattr(refiner, "video_level", False)
    plan = T.plan_tiles((TW, TH), (W, H), mode, overlap_pixels, align=16 if video_level else 2)
    post = not video_level
    tiles = plan.grids[0] if plan.mode != "seam_aware" or video_level else union_tiles(plan)
    warnings = list(plan.warnings)
    if plan.mode == "seam_aware" and post:
        warnings.append("seam_aware con un refinador de post-proceso no tiene bucle de pasos que alternar: se compone con la unión de ambas cuadrículas (= 3x3, 9 piezas)")
    eff_plan = plan if (video_level or plan.mode != "seam_aware") else T.TilePlan(plan.frame, plan.tile, plan.mode, [tiles], plan.overlap, plan.feather, plan.warnings)
    c = T.cost(eff_plan, info["duration"] or 1.0, steps, base_vram_gb=base_vram_gb)
    rep = {"src": src, "dst": dst, "source": [W, H], "target": [TW, TH], "mode": plan.mode, "tiles": [len(g) for g in plan.grids] if video_level else len(tiles),
           "overlap_px": list(plan.overlap), "feather_px": plan.feather, "warnings": warnings, "refiner": refiner.name, "stage": "B", "cost": c,
           "cost_vs_base_pass": c["relative_to_base"]}
    if dry:
        return rep
    t0 = time.time()
    os.makedirs(os.path.dirname(os.path.abspath(dst)) or ".", exist_ok=True)
    mid = dst + ".tmp.mp4"
    rd = imageio.get_reader(src, "ffmpeg")
    xs, ys = T.seam_positions(T.TilePlan(plan.frame, plan.tile, plan.mode, [tiles], plan.overlap, plan.feather))
    wr = imageio.get_writer(mid, fps=info["fps"], codec="libx264", pixelformat="yuv420p", macro_block_size=1, ffmpeg_params=["-crf", str(crf), "-preset", "medium"])
    n = max(1, int(round(info["duration"] * info["fps"]))) if info["duration"] else None
    keep_up, keep_out = [], []

    def gate(frame_u8):
        if not (xs or ys):
            return {"ratio": 1.0}
        res = T.seam_visibility(frame_u8, xs, ys)
        if not allow_visible_seams:
            T.check_seams(res, seam_threshold)          # raises SeamTooVisible BEFORE the rest of the video is written
        return res

    seam = None
    if video_level:
        lr = np.stack([np.asarray(f) for f in rd])
        out_frames = refiner.refine_video(lr, scale, progress)
        for i, out in enumerate(out_frames):
            if i == 0:
                seam = gate(out)
            wr.append_data(out)
            if i < 8:
                keep_up.append(_resize(lr[i], (TW, TH)))
                keep_out.append(out)
    else:
        for i, frame in enumerate(rd):
            lr = np.asarray(frame)
            up = _resize(lr, (TW, TH))
            parts = [np.asarray(refiner.refine(lr, up, t, i), np.float64) for t in tiles]
            if plan.mode == "no_overlap":
                full = T.blend(parts, tiles, (TH, TW), 0, kind=window)
                full = T.smooth_seams(full, xs, ys, band=max(8, W // 8)) if exposure_matching else full
            else:
                if exposure_matching and len(tiles) > 1:
                    parts, _ = T.match_exposure(parts, tiles)
                full = T.blend(parts, tiles, (TH, TW), max(8, plan.feather), kind=window)
            out = np.clip(full, 0, 255).astype(np.uint8)
            if i == 0:
                seam = gate(out)
            wr.append_data(out)
            if i < 8:
                keep_up.append(up)
                keep_out.append(out)
            if progress and n:
                progress(min(0.98, (i + 1) / n))
    wr.close()
    rd.close()
    subprocess.run([_ffmpeg(), "-v", "error", "-y", "-i", mid, "-i", src, "-map", "0:v", "-map", "1:a?", "-c:v", "copy", "-c:a", "aac", dst], check=True)
    os.remove(mid)
    rep["seam_visibility"] = seam or {"ratio": 1.0}
    if compare and len(keep_out) >= 2:
        rep["metrics_vs_lanczos"] = Q.compare_to_baseline(np.stack(keep_out), np.stack(keep_up))
    rep["seconds"] = time.time() - t0
    progress and progress(1.0)
    return rep
