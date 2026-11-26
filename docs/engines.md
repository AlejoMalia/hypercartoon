# Local generation engines — no paid platform

The studio can generate the episode with **your own engine** (Hypercartoon: CogVideoX + test-time-training, trained on your show) or
with open-source video models run locally through Hugging Face diffusers. Nothing here calls a paid API; weights are downloaded once
from the hub and cached.

```bash
python -m studio engines                         # what this machine can run, and the catalogue
python -m studio create guion.txt                # prompts with the learned style, characters and a no-text negative prompt
python -m studio render --dry                    # the clips and the work, loading no model
python -m studio render --engine auto            # the best engine that fits this machine
python -m studio render --engine wan22-ti2v-5b --lora MiEstilo.safetensors
python -m studio render --engine hypercartoon    # prints the sample.py commands of your own engine
python -m studio export-lora --engine ltx-video --out lora_ltx/    # teach a third-party engine your show (prompt.txt + videos.txt)
```

| Engine | Params | VRAM (min / comfortable) | Native | Licence | Continues a scene from its last frame |
|---|---|---|---|---|---|
| **hypercartoon** (your engine) | 5B + TTT | H100 / ≥ 24 GB | 720×480 · 16 fps · up to 63 s | MIT; CogVideoX weights have their own licence | native (one pass up to 63 s) |
| `wan22-ti2v-5b` | 5B | 12 / 24 GB | 1280×704 · 24 fps · 5 s | Apache-2.0 | no (hard cut) |
| `ltx-video` | 2B | 8 / 16 GB | 704×480 · 24 fps · 6.7 s | LTX community licence (free below a revenue threshold) | yes (`LTXImageToVideoPipeline`) |
| `hunyuan-video-1.5` | 8.3B | 14 / 32 GB | 1280×720 · 24 fps · 5 s | Tencent licence (restrictions) | no |
| `cogvideox-5b` / `-2b` | 5B / 2B | 8 / 24 · 6 / 12 GB | 720×480 · 8 fps · 6 s | custom / Apache-2.0 | yes (`…ImageToVideoPipeline`) |
| `mochi-1` | 10B | 20 / 40 GB | 848×480 · 30 fps · 2.8 s | Apache-2.0 | no |
| `longcat-video` | 13.6B | 40 / 80 GB | 832×480 · 15 fps · 6 s | MIT | its own repository, not in diffusers |

How `render` works: the 3-second segments of `prompts.jsonl` are grouped by scene (a scene transition starts a new one) into clips of
at most the engine's length; clips are rendered (resumable; finished clips are kept), a scene longer than the engine's limit continues from
the last frame when the engine has an image-to-video pipeline (otherwise the report counts the hard cuts), clips are joined at
`--size`/`--fps-out` and the regenerated dialogue (`sound/video_*.wav`) is put on top. The learned style, characters and the
negative text (no subtitles / logos / watermarks) are already in the prompts.

## Your show in a third-party engine

Those engines do not know your cartoon. `export-lora` writes the learned material in the layout used by the diffusers / finetrainers
LoRA trainers: `prompt.txt` (one caption per sample, with the style token, sanitised of any mention of text), `videos.txt` (matching
lines) and `make_videos.sh` (ffmpeg cuts at the engine's size and rate). These engines have **no loss mask**, so burned-in logos are
removed with ffmpeg's `delogo` and windows with title cards or more than 10 % subtitle / logo are left out (`docs/overlays.md`).
Train with the trainer for your engine (this repository does not run it; see https://github.com/huggingface/finetrainers) and pass the LoRA
with `--lora`.

## What was verified

Run with `tests/test_engines_real.py` (needs torch, diffusers, peft and the hub; skipped otherwise):

* **All five diffusers engines were run through the wrapper as REAL diffusers pipeline classes with tiny random weights, on CPU**:
  `LTXPipeline` and `WanPipeline` (public tiny test repos), `CogVideoXPipeline` and `MochiPipeline` (tiny models built from their configs the
  way diffusers' own tests do), and `HunyuanVideo15Pipeline` (public tiny repo + tokenizers + guider; guidance really goes through `pipe.guider`).
  That checks call arguments, frame rules, guidance conventions and the output conversion. `LTXImageToVideoPipeline` was run to continue a clip
  from its last frame, and an episode was rendered end to end (clips, join, audio) with a real pipeline.
* **LoRA**: `studio train-lora` (built-in, LTX-Video) trained on a set in the `export-lora` layout with a real LTX pipeline class: the loss fell
  (2.65 → 2.21 in 30 steps on four tiny clips), the LoRA was saved, loaded through `--lora` (adapter active) and changed the render.
* Planning, chunking, joining, dialogue on top, resuming, the hardware advisor, the disk guard, the LoRA export and the CLI are covered
  by the regular tests.

## What cannot be verified on a small machine, and the numbers

Real weights are big. Measured on the hub (diffusers components, default precision) — **what `from_pretrained` downloads**:

| Engine | Download |
|---|---|
| cogvideox-2b | 13.8 GB |
| cogvideox-5b | 21.5 GB |
| ltx-video | 28.4 GB |
| wan22-ti2v-5b | 34.2 GB |
| hunyuan-video-1.5 | 53.4 GB |
| mochi-1 | 90.6 GB |

`studio engines` shows these next to your free disk, and the engine **refuses to start a download that would not fit** (keeping 3 GB
free) instead of filling the disk half-way; point the cache to another drive with `export HF_HOME=/Volumes/DISK/hf`.
The development machine (Apple M4, 16 GB, a nearly full disk) could therefore not run any real weights: **no real model has generated
a real frame here, and no GPU run was made.** Quality, speed and VRAM figures are from the model cards (approximate) and unverified.
Wan 2.2 TI2V needs diffusers from `main`; the Wan pipeline also needs `ftfy`.
Install: `pip install torch git+https://github.com/huggingface/diffusers transformers accelerate sentencepiece ftfy peft imageio-ffmpeg`.
