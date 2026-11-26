# High resolution in two stages (480x720 base -> 960x1440)

Frame sizes are width x height: the base is 720x480 (the project's 480x720), the target 1440x960.

```
Stage A  the DiT at its native size, 16 fps, up to 63 s   global composition, motion, long context (unchanged; Enhance-A-Video lives HERE)
Stage B  upsample x2 -> refine native-size tiles -> normalised-window blend -> exposure matching -> seam gate -> (optional) finishing
```
```bash
python -m studio hires base.mp4 --dry                              # plan, tiles, cost per mode (passes x steps x memory)
python -m studio hires base.mp4 --refiner esrgan --mode full_overlap --model anime-video      # post-process tiled Real-ESRGAN
python -m studio hires base.mp4 --refiner generative --mode seam_aware --strength 0.35        # prints the GPU command for refine_video.py
python -m studio hires base.mp4 --refiner enhance_a_video --enhance-weight 2                   # prints the STAGE-A flags (it is not a post refiner)
python -m studio create guion.txt --enhance-weight 2               # the generation commands already carry --eval.enhance_weight=2
```

## Planner modes (`studio/tiling.py`), cost for a 1440x960 frame and a 720x480 window
| Mode | Tiles | Passes / denoising step | What it is |
|---|---|---|---|
| `no_overlap` | 2x2 | 4 | tiles abut, nothing is shared: seams can only be softened afterwards (per-seam exposure ramp) |
| `seam_aware` (recommended) | A: 2x2, B: 5 tiles centred on A's seams | 4.5 (alternating) | a seam of one step is the interior of a tile at the next; corners are not updated on grid-B steps |
| `full_overlap` | 3x3, 50 % overlap | 9 | maximum quality |
A fixed window cannot give a small overlap: 10-20 % with four native tiles is impossible. `overlap_pixels` exists only where an overlap exists: the **feather width**
in `seam_aware`, the **minimum overlap** in `full_overlap` (asking 100 px still gives 360 px with 3x3; 400 px needs more tiles; > 90 % of the window is rejected);
in `no_overlap` it is an error. `studio.tiling.cost(plan, seconds, steps, base_vram_gb=..., batch_tiles=...)` returns passes, total tile passes, step-segments,
wall time relative to a base pass, VRAM (your measured base peak x batch) and the full-frame latent state kept for synchronisation (~0.17 GB for 63 s at 1440x960).
For post-process refiners there is no denoising loop to alternate grids over, so `seam_aware` composes the union of both grids (= the 3x3 set) and says so.

## Fusion (correctness)
* **Windows that sum to exactly 1** at every covered pixel (`normalized_windows`, raised cosine or Gaussian); identical tiles reconstruct the frame to 1e-9.
* **Exposure matching is mandatory**: per-tile, per-channel gain/bias solved on the overlaps (`match_exposure`); for abutting tiles `smooth_seams` removes the step
  across every seam stretch (neighbouring tiles can disagree in opposite directions along one line). Turning it off needs `allow_visible_seams=True`.
* **Seam metric and gate**: `seam_visibility` = mean pixel step across a seam / mean step elsewhere (1 = invisible, > 1.5 visible). `hires_video` evaluates the first frame and
  raises `SeamTooVisible` BEFORE writing the rest of the video; the tests fail on the same threshold. `no_overlap` cannot fix structural mismatches and the gate says so.
* **Metrics against the Lanczos baseline** (`studio/quality.py`): `temporal_warp_error` (optical-flow residual), `compare_to_baseline` -> low-frequency PSNR (did stage B stay
  faithful to stage A?), temporal ratio (flickers more than Lanczos if > 1.15), sharpness ratio. They are in every `hires` report.

## Refiners are separate (`REFINERS`, `studio/hires.py`)
| `--refiner` | Stage | What it does |
|---|---|---|
| `enhance_a_video` | **A** | rescales attention inside the BASE generation (`eval.enhance_weight`); rejected as a post refiner with `StageError` and the flags to use |
| `identity` | B | the Lanczos baseline |
| `esrgan` | B | post-process: Real-ESRGAN on the LOW-RES region of every tile (tiled ESRGAN) |
| `generative` | B | re-noising + regeneration conditioned on the low-res video (below) |

## The generative refiner (`hypercartoon/models/cogvideo/refine.py`, `refine_video.py`)
SDEdit-style, in latent space, tiled:
1. encode the Lanczos-upsampled stage-A video tile by tile (VAE) and blend into the full-frame reference latent;
2. re-noise it to the level of `strength` (1 = regenerate from scratch, ~0.35 = keep stage A almost intact);
3. denoise with the DiT from there, tile by tile, with the same DPM-Solver++(2M) update the base sampler uses; at EVERY step the tiles' x0 predictions are blended with
   normalised windows into one full-frame estimate (MultiDiffusion-style synchronisation; in `seam_aware` the two grids alternate);
4. **conditioned on the low-res video**: the low frequencies of every x0 prediction are pulled back to the reference (`lam`), so composition, motion and identity stay stage A's
   and the model only adds fine detail; optionally the DiT also knows where each tile sits (`TileControl`);
5. decode each tile, blend with normalised windows, apply the exposure gains measured on the first frame.
Status: the algorithm, shapes, determinism, projection, per-step synchronisation, grid alternation, time padding to 4k+1 and the sampler call convention are tested on CPU with stand-in
denoisers; `DitRefineBackend` and `refine_video.py` are written against this repository's sampler/VAE APIs and **have not been run with the real DiT on a GPU**. Quality depends on
`strength` / `lam` and, best, on a DiT fine-tuned for refinement with real high-resolution footage (see below); compare against stage A + Lanczos / Real-ESRGAN with `studio ab`.

## TileControl: exact coordinate system (`hypercartoon/models/cogvideo/conditioning.py`)
* `tile_pos` [B, 4] = (x0, y0, x1, y1): the tile's rectangle in the FULL frame, **normalised to [0, 1]** (x / W, y / H; origin top-left, y down). `Tile.norm(frame)` makes it.
* Tokens = the tile's patch grid flattened (frame, row, column). The token at (r, c) of an Hp x Wp grid sits at its patch centre: gx = x0 + (c + 0.5) / Wp * (x1 - x0), gy likewise.
* Features: Fourier features of gx and gy at octave frequencies 2^k * pi (k < 6), sin and cos -> 24 values, plus the tile extent (2) -> a zero-initialised MLP -> an offset added to every
  token, identical for every frame of the tile.
* `control_tile = false` (default): `build_control_stack` returns `None` -> no module, no parameters, no new state-dict keys, the forward is untouched (`maybe_apply_control` returns the same
  tensor object). Enabled but untrained it is exactly the identity. Both are tested; the full DiT forward cannot be imported on a Mac, so the equality is shown at the module boundary.

## Experimental, optional: guarded short test-time training (`ttt_short.py`, `--refine.ttt_steps N`)
The Hyper layers already run an inner test-time-training loop at inference. This is an OUTER fine-tune of a few parameters on the model's own refined output, so it can amplify
artefacts: it measures an A/B metric before (temporal ratio vs Lanczos + drift from stage A on a held-out clip), re-measures every few steps, stops early when it worsens or stalls, and
**restores the original weights unless the metric improved by `min_gain`**. Off by default. Tested with toy models; never run on the real model.

## Cost and what it would take
Stage B adds 4 (no_overlap), 4.5 (seam_aware) or 9 (full_overlap) base passes per step on top of stage A; e.g. 63 s at 25 steps is 525 step-segments per base pass.
For a trained generative refiner: real high-resolution footage (not upsampled 480p, or it learns to invent texture), pairs (HR crop, the same crop degraded like stage-A output),
`model.control_tile = true` and conditioning on the upsampled tile, then A/B on the same seeds. The original training took ~50 h on 256 H100 for 480p.
