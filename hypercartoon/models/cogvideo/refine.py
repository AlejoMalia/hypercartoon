"""Generative refinement of an upsampled stage-A video, tile by tile, inside the latent space (stage B of docs/hires.md).

SDEdit-style re-noising + regeneration conditioned on the low-resolution video:
  1. encode the Lanczos-upsampled stage-A video tile by tile (VAE) -> `ref`, the full-frame latent;
  2. re-noise it to the noise level given by `strength` (strength 1 = regenerate from scratch, small = keep stage A almost intact);
  3. denoise with the DiT from that level on, tile by tile, with the same DPM-Solver++(2M) update the base sampler uses; at EVERY step the
     tiles' x0 predictions are blended with normalised windows into one full-frame x0 (MultiDiffusion-style synchronisation; with two grids,
     they alternate between steps so seams move);
  4. condition on the low-res video: the LOW FREQUENCIES of every x0 prediction are pulled back to the reference (range-null / low-pass
     consistency, strength `lam`), so composition, motion and identity stay those of stage A and the model only adds fine detail;
  5. optionally the DiT knows where each tile sits (TileControl, `tile_pos`).
Pure torch, no import of the heavy model code: the DiT enters through `denoise_tile`. `DitRefineBackend` adapts the repo's sampler / VAE.
Verified on CPU only with stand-in denoisers (algorithm, shapes, determinism, projection, synchronisation); NOT run with the real DiT / on GPU."""
import math
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import torch
import torch.nn.functional as F


def lowpass(x: torch.Tensor, factor: int) -> torch.Tensor:
    """Spatial low-pass of [..., h, w]: average-pool by `factor` then bilinear back up."""
    h, w = x.shape[-2:]
    y = F.avg_pool2d(x.reshape(-1, 1, h, w), factor, ceil_mode=True)
    return F.interpolate(y, size=(h, w), mode="bilinear", align_corners=False).reshape(x.shape)


def project_low_frequency(x0_pred: torch.Tensor, x_ref: torch.Tensor, lam: float = 0.8, factor: int = 4) -> torch.Tensor:
    """Replace a fraction `lam` of the prediction's low frequencies by the reference's (detail comes from the model, structure from stage A)."""
    if lam <= 0:
        return x0_pred
    return x0_pred + lam * (lowpass(x_ref, factor) - lowpass(x0_pred, factor))


def start_step(n_steps: int, strength: float) -> int:
    """Index in the noisy->clean schedule where refinement starts. strength 1 -> 0 (full regeneration), 0 -> n_steps (nothing to do)."""
    if not 0.0 <= strength <= 1.0:
        raise ValueError("strength debe estar en [0, 1]")
    return int(round((1.0 - strength) * n_steps))


def dpmpp2m_step(x: torch.Tensor, x0: torch.Tensor, old_x0: Optional[torch.Tensor], a: float, a_next: float, a_prev: Optional[float],
                 generator: Optional[torch.Generator] = None) -> torch.Tensor:
    """DPM-Solver++(2M) update for the VP discretisation, mirroring VPSDEDPMPP2MSampler.sampler_step. a = sqrt(alpha_cumprod) of the current /
    next / previous level (ascending: noisy -> clean). The last step (a_next == 1) returns the denoised estimate exactly."""
    if a_next >= 1.0 - 1e-7:
        return x0
    ab, abn = a * a, a_next * a_next
    lamb, lamb_n = 0.5 * math.log(ab / (1 - ab)), 0.5 * math.log(abn / (1 - abn))
    h = lamb_n - lamb
    mult0 = math.sqrt((1 - abn) / (1 - ab)) * math.exp(-h)
    mult1 = math.expm1(-2 * h) * a_next
    noise_scale = math.sqrt(1 - abn) * math.sqrt(1 - math.exp(-2 * h))
    noise = torch.randn(x.shape, generator=generator, device=x.device, dtype=x.dtype)
    if old_x0 is None or a_prev is None:
        return mult0 * x - mult1 * x0 + noise_scale * noise
    abp = a_prev * a_prev
    r = (lamb - 0.5 * math.log(abp / (1 - abp))) / h
    d = (1 + 1 / (2 * r)) * x0 - (1 / (2 * r)) * old_x0
    return mult0 * x - mult1 * d + noise_scale * noise


Rect = Tuple[int, int, int, int]     # x0, y0, x1, y1 in latent pixels


def refine_latent_tiled(ref: torch.Tensor, grids: Sequence[Sequence[Tuple[Rect, torch.Tensor]]], denoise_tile: Callable, alphas_sqrt: Sequence[float],
                        strength: float = 0.35, lam: float = 0.8, factor: int = 4, generator: Optional[torch.Generator] = None,
                        callback: Optional[Callable] = None) -> torch.Tensor:
    """ref [T,C,H,W] full-frame latent of the upsampled stage-A video. grids: one list of (rect, weight[h,w]) per phase (windows must sum to 1
    where the grid covers; phases alternate every step). denoise_tile(x_tile [T,C,h,w], step_index, rect) -> x0 estimate for that tile.
    alphas_sqrt: ascending sqrt(alpha_cumprod) per step plus a final 1.0 (as VPSDEDPMPP2MSampler builds it)."""
    n = len(alphas_sqrt) - 1
    i0 = start_step(n, strength)
    if i0 >= n:
        return ref.clone()
    a0 = float(alphas_sqrt[i0])
    x = a0 * ref + math.sqrt(1 - a0 * a0) * torch.randn(ref.shape, generator=generator, device=ref.device, dtype=ref.dtype)
    old_x0, x0_state = None, ref.clone()
    for i in range(i0, n):
        acc, wsum = torch.zeros_like(x), torch.zeros(1, 1, *x.shape[-2:], device=x.device, dtype=x.dtype)
        for (rx0, ry0, rx1, ry1), w in grids[(i - i0) % len(grids)]:
            pred = denoise_tile(x[..., ry0:ry1, rx0:rx1], i, (rx0, ry0, rx1, ry1))
            acc[..., ry0:ry1, rx0:rx1] += pred * w
            wsum[..., ry0:ry1, rx0:rx1] += w
        x0 = torch.where(wsum > 0, acc / wsum.clamp_min(1e-12), x0_state)      # pixels no tile updated this step keep the previous estimate
        x0 = project_low_frequency(x0, ref, lam, factor)
        x = dpmpp2m_step(x, x0, old_x0, a=float(alphas_sqrt[i]), a_next=float(alphas_sqrt[i + 1]), a_prev=float(alphas_sqrt[i - 1]) if i > i0 else None, generator=generator)
        old_x0, x0_state = x0, x0
        if callback:
            callback(i - i0 + 1, n - i0)
    return x


def assemble(tiles: Sequence[torch.Tensor], rects: Sequence[Rect], weights: Sequence[torch.Tensor], full_hw: Tuple[int, int]) -> torch.Tensor:
    """Blend tile tensors [T,C,h,w] into the full frame [T,C,H,W] with windows that sum to 1 (used to build `ref` from per-tile encodings)."""
    H, W = full_hw
    t = tiles[0]
    acc, ws = torch.zeros(t.shape[0], t.shape[1], H, W, dtype=t.dtype, device=t.device), torch.zeros(1, 1, H, W, dtype=t.dtype, device=t.device)
    for x, (x0, y0, x1, y1), w in zip(tiles, rects, weights):
        acc[..., y0:y1, x0:x1] += x * w
        ws[..., y0:y1, x0:x1] += w
    return acc / ws.clamp_min(1e-12)


class DitRefineBackend:
    """Adapter from the repo's sampler / VAE to what `refine_latent_tiled` and studio.hires.GenerativeRefiner need. Duck-typed (written against
    VPSDEDPMPP2MSampler.denoise / prepare_sampling_loop and VideoAutoencoderInferenceWrapper.encode/decode_first_stage; not run here).
    Latents are [T_lat, C, h, w]; the model wants [1, T_lat, C, h, w]."""

    vae_stride = 8
    latent_channels = 16

    def __init__(self, sampler, vae, text_emb: torch.Tensor, neg_emb: torch.Tensor, device: str = "cuda", dtype=torch.bfloat16,
                 frame_hw: Optional[Tuple[int, int]] = None, use_tile_control: bool = False):
        self.sampler, self.vae, self.text_emb, self.neg_emb = sampler, vae, text_emb, neg_emb
        self.device, self.dtype, self.frame_hw, self.use_tile_control = device, dtype, frame_hw, use_tile_control
        self._alphas, self._timesteps = None, None

    def schedule(self) -> List[float]:
        x = torch.zeros(1, 1, self.latent_channels, 2, 2, device=self.device)
        _, _, alphas, _, _, _, timesteps = self.sampler.prepare_sampling_loop(x, {"crossattn": self.text_emb}, {"crossattn": self.neg_emb})
        self._alphas, self._timesteps = alphas, timesteps
        return [float(a) for a in alphas.detach().cpu()]

    def encode(self, frames: "torch.Tensor") -> torch.Tensor:
        """uint8 frames [T,h,w,3] -> model-space latent [T_lat, C, h/8, w/8] (T must be 4k+1: the caller pads)."""
        x = frames.to(self.device).float().permute(3, 0, 1, 2)[None] / 127.5 - 1.0           # [1,3,T,h,w] in [-1,1]
        z = self.vae.encode_first_stage(x.to(self.dtype), unregularized=False, multiply_by_scale_factor=True)
        return z[0].permute(1, 0, 2, 3).float()

    def decode(self, latent: torch.Tensor) -> torch.Tensor:
        out = self.vae.decode_first_stage(latent.permute(1, 0, 2, 3)[None].to(self.dtype))    # [1,3,T,H,W] in [-1,1]
        return ((out[0].float().clamp(-1, 1) + 1) * 127.5).round().byte().permute(1, 2, 3, 0).cpu()

    def denoise(self, x: torch.Tensor, i: int, tile_pos: Optional[Tuple[float, float, float, float]] = None, grad: bool = False) -> torch.Tensor:
        with torch.set_grad_enabled(grad):
            return self._denoise(x, i, tile_pos)

    def _denoise(self, x: torch.Tensor, i: int, tile_pos: Optional[Tuple[float, float, float, float]]) -> torch.Tensor:
        cond, uc = {"crossattn": self.text_emb}, {"crossattn": self.neg_emb}
        if self.use_tile_control and tile_pos is not None:
            ctrl = {"tile_pos": torch.tensor([tile_pos], device=self.device, dtype=torch.float32)}
            cond["control"], uc["control"] = ctrl, ctrl
        a = x.new_ones([1]) * float(self._alphas[i])
        num_steps = len(self._alphas) - 1
        out = self.sampler.denoise(x[None].float(), a, cond, uc, self._timesteps[-(i + 1)], num_steps - i)      # same call as sampler_step
        return out[0].float()
