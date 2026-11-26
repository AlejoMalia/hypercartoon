# Improving what the generator draws (and proving it)

Hypercartoon shares its generator with TTT-Video (CogVideoX-5B + Hyper layers). **Nothing here has been shown to make that generator
better**; what is new is (1) opt-in inference-time mechanisms and (2) a harness that lets you *measure* whether they help on your footage.

## Options reviewed (web research Nov 2026; check each licence)
| Option | What it is | In hypercartoon |
|---|---|---|
| [Enhance-A-Video](https://arxiv.org/html/2502.07508v3) (NUS-HPC-AI-Lab) | training-free: scales the attention output by the cross-frame intensity (mean of the non-diagonal temporal attention) times a temperature; reported to help CogVideoX; extreme weights distort | **Integrated, opt-in, adapted**: `hypercartoon/models/cogvideo/enhance.py`, `eval.enhance_weight` (0 = off). Their package targets diffusers pipelines (`inject_enhance_for_cogvideox(pipe.transformer)`) and cannot be injected into this custom DiT; this is an independent re-implementation of the description, computed per 3-second chunk. Unvalidated on GPU; the math is tested |
| [VEnhancer](https://github.com/Vchitect/VEnhancer) | generative refiner + super-resolution + frame interpolation for CogVideoX outputs | **Not integrated**: its README asks for at least an A100 80 GB for single-GPU inference (against the low-compute goal) and I could not confirm its licence. It can be attached as a `postprocess.json` step if you decide to run it |
| [cogvideox-controlnet](https://github.com/TheDenk/cogvideox-controlnet) | ControlNets (canny, hed found; no depth found) for the diffusers CogVideoX-5B pipeline, "raw version" per its card | **Not integrated**: weights target the diffusers base model, not this DiT. Hypercartoon's own route is `CharacterControl` / `FrameControl` (docs/capabilities.md), which needs training |
| [Video-T1](https://liuff19.github.io/Video-T1) | test-time scaling: search over noise trajectories with verifiers (Tree-of-Frames is the efficient variant); MIT per a mirror | **Partly, the cheap half**: best-of-N by selection (`python -m studio pick`) with CPU quality proxies as verifier. Tree-of-Frames (autoregressive branching with pruning) is not implemented |

Licence note that matters for any commercial use: the CogVideoX-5B transformer weights carry a custom licence (commercial use requires
registration with the publisher, per its LICENSE), independent of this repository's MIT code.

## The harness
```bash
python -m studio score out/prompt-0/000000.mp4                      # flicker, stutter, frame correlation, colour drift, sharpness
python -m studio ab runs/base runs/enhance2 --out ab.md             # paired A/B: same relative paths = same prompt + same seed
python -m studio pick runs/seed0 runs/seed1 runs/seed2 --out picked.json --link best/   # best candidate per prompt
```
`ab` reports the mean paired difference with a 95 % bootstrap interval per metric and says *B mejor / B peor / sin diferencia clara*, and
refuses a verdict under 5 pairs. Sharpness is informational only (sharper is not better by itself). The proxies are cheap and CPU-only
(stutter is measured on brightness-normalised frames so flicker is not mistaken for motion); they do **not** replace human review or VBench.

## A protocol that answers "does it beat the base?"
1. Fix 10-20 prompts and seeds. Generate them with the base config (`runs/base`).
2. Generate again changing one thing: `--eval.enhance_weight=1.5`, or `--eval.step_cache_threshold=...`, or a fused style, into `runs/variant`.
3. `python -m studio ab runs/base runs/variant`. Look at the videos too.
4. Keep only what is "B mejor" with a margin and looks better to you. Everything above is off by default until you decide.
