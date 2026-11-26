"""Stage B generative refinement of a finished stage-A video (GPU). docs/hires.md.

  torchrun --nproc_per_node=1 refine_video.py --job.config_file configs/eval/hyper-mlp/3s.toml --eval.input_file prompts.jsonl \
      --eval.num_denoising_steps=25 --refine.input base.mp4 --refine.output base_x2.mp4 --refine.scale 2 --refine.mode seam_aware \
      --refine.strength 0.35 --refine.lam 0.8

Loads the same model / VAE / T5 as sample.py, upsamples the base video, and refines it tile by tile in latent space (re-noising + regeneration
conditioned on the low-resolution video, tiles synchronised every step: hypercartoon/models/cogvideo/refine.py). The first video of the prompt
file provides the text. With `--refine.ttt_steps N > 0` it runs the EXPERIMENTAL guarded short test-time training (ttt_short.py): it is kept only
if the A/B metric improves, otherwise the original weights are restored.
IMPLEMENTED against the repo's own sampler / VAE APIs; NOT executed here (no GPU). Expect to tune strength / lam on your footage with `studio ab`."""
import os
import subprocess

import imageio
import numpy as np
import torch
from torch.distributed.elastic.multiprocessing.errors import record

from hypercartoon.infra.config_manager import JobConfig
from hypercartoon.infra.parallelisms import end_distributed
from hypercartoon.models.cogvideo.refine import DitRefineBackend
from hypercartoon.models.cogvideo.sampler import PromptManager, TextEncoder
from sample import VideoGenerationRunner
from studio.hires import GenerativeRefiner

ARGS = [
    ("--refine.input", dict(type=str, required=True, help="stage-A video (native resolution)")),
    ("--refine.output", dict(type=str, required=True)),
    ("--refine.scale", dict(type=float, default=2.0)),
    ("--refine.mode", dict(type=str, default="seam_aware", choices=["no_overlap", "seam_aware", "full_overlap"])),
    ("--refine.overlap_pixels", dict(type=int, default=None, help="feather (seam_aware) / minimum overlap (full_overlap)")),
    ("--refine.strength", dict(type=float, default=0.35, help="re-noising strength: 1 regenerates, small keeps stage A")),
    ("--refine.lam", dict(type=float, default=0.8, help="low-frequency consistency to the stage-A video")),
    ("--refine.window", dict(type=str, default="cosine", choices=["cosine", "gaussian"])),
    ("--refine.seed", dict(type=int, default=0)),
    ("--refine.ttt_steps", dict(type=int, default=0, help="EXPERIMENTAL guarded short test-time training steps (0 = off)")),
    ("--refine.ttt_kind", dict(type=str, default="hyper", choices=["hyper", "spatial_attention"])),
]


def build_backend(runner, job_config, prompts_file, frame_hw, use_tile_control):
    pos, neg, _, _, _ = PromptManager.get_prompts_with_mix(prompts_file)[0]
    dtype = runner.video_generator.dtype
    te = lambda p: TextEncoder.encode_text(runner.tokenizer, runner.t5_encoder, p, runner.device, job_config.eval.txt_maxlen, dtype)
    text_emb, neg_emb = te(pos), te([t or "" for t in neg])
    sampler = runner.video_generator.sampler.sampler                     # VPSDEDPMPP2MSampler
    return DitRefineBackend(sampler, runner.vae_model, text_emb, neg_emb, runner.device, dtype, frame_hw, use_tile_control)


def run_ttt(runner, backend, refiner, frames, args):
    """Guarded short TTT: optimise a few parameters on a denoising loss of the refined output; keep only if the A/B metric improves."""
    from hypercartoon.models.cogvideo import ttt_short as TS
    from studio import quality as Q

    params = TS.select_params(runner.model.dit, args.ttt_kind)
    clip = frames[:49]                                                    # a short held-out clip is the A/B arena
    base_up = None

    def metric():
        nonlocal base_up
        out = refiner.refine_video(clip, args.scale)
        if base_up is None:
            from studio.hires import _resize

            base_up = np.stack([_resize(f, (out.shape[2], out.shape[1])) for f in clip])
        m = Q.compare_to_baseline(out[:8], base_up[:8])
        return m["temporal_ratio"] + max(0.0, 40.0 - m["lowfreq_psnr_db"]) / 40.0        # flicker vs Lanczos + drift from stage A: lower is better

    def loss():
        torch.manual_seed(0)
        out = refiner.refine_video(clip, args.scale)                       # pseudo-target: the model's own refined clip
        i = len(backend._alphas) // 2
        x0 = backend.encode(torch.from_numpy(out[:49, :480, :720]))        # one native tile of the output
        a = float(backend._alphas[i])
        xt = a * x0 + (1 - a * a) ** 0.5 * torch.randn_like(x0)
        return ((backend.denoise(xt, i, (0, 0, 0.5, 0.5), grad=True) - x0) ** 2).mean()

    return TS.short_ttt(params, loss, metric, steps=args.ttt_steps)


@record
def main(job_config: JobConfig):
    a = job_config.refine
    runner = VideoGenerationRunner(job_config)
    frames = np.stack([np.asarray(f) for f in imageio.get_reader(a.input, "ffmpeg")])
    h, w = frames.shape[1:3]
    backend = build_backend(runner, job_config, job_config.eval.input_file, (h, w), getattr(job_config.model, "control_tile", False))
    refiner = GenerativeRefiner(backend, a.strength, a.lam, 4, a.mode, a.overlap_pixels, a.window, a.seed)
    if a.ttt_steps > 0:
        res = run_ttt(runner, backend, refiner, frames, a)
        print(f"[short TTT experimental] accepted={res.accepted} baseline={res.baseline:.4f} final={res.final:.4f} reason={res.reason}")
    out = refiner.refine_video(frames, a.scale, progress=lambda f: print(f"\rrefinando {f * 100:3.0f}%", end=""))
    mid = a.output + ".tmp.mp4"
    fps = imageio.get_reader(a.input, "ffmpeg").get_meta_data()["fps"]
    wr = imageio.get_writer(mid, fps=fps, codec="libx264", pixelformat="yuv420p", macro_block_size=1, ffmpeg_params=["-crf", "16"])
    for f in out:
        wr.append_data(f)
    wr.close()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", mid, "-i", a.input, "-map", "0:v", "-map", "1:a?", "-c:v", "copy", "-c:a", "aac", a.output], check=True)
    os.remove(mid)
    print(f"\n{a.output}: {out.shape[2]}x{out.shape[1]} · refinador {refiner.info}")
    end_distributed()


if __name__ == "__main__":
    config = JobConfig(eval_mode=True)
    for name, kw in ARGS:
        config.parser.add_argument(name, **kw)
    config.parse_args()
    main(config)
