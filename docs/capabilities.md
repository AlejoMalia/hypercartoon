# Model capabilities beyond CogVideoX + TTT

The base model is still CogVideoX-5B with the Hyper (test-time-training) layers: 480x720, 16 fps, up to 63 s, one global text
prompt per 3-second segment. What hypercartoon adds is **control**: optional, zero-initialised adapters in the DiT
(`hypercartoon/models/cogvideo/conditioning.py`) that let the model take extra inputs it never had.

| Adapter | Input | What it gives (once trained) |
|---|---|---|
| `CharacterControl` | label map `[T,30,45]` (0 = background, k = persistent character id, the ids `hypercartoon/perception` produces) | identity + layout control: every token knows which character it belongs to; one learned embedding per id |
| `CharacterControl` features | `[T, ids+1, K]` per character per frame (mouth openness, emotion...) | per-character signals gathered through the label map (a mouth that follows *that* character's voice) |
| `TileControl` | `tile_pos` (x0,y0,x1,y1 of the tile in the full frame, normalised 0..1) | global coordinates for every token (exact definition in docs/hires.md): tiled / cascaded high-resolution generation |
| `FrameControl` | `[T, F]` global per frame: speech, loudness, valence, arousal | audio/emotion conditioning when no layout is known |

Why this is safe to add: every output layer starts at **exactly zero**, so a model with the adapters enabled is bit-identical to the base
model until they are trained (tested: `tests/test_control.py`). `init_model_parameters` leaves them alone (the model is built on the
meta device and randomly initialised otherwise; tested). Checkpoints that predate the adapters still load: the missing `.control.`
keys are skipped and the adapters keep their zeros (`hypercartoon/infra/state_load.py`, tested with fakes). Disabled (default) they cost nothing.

## Use
```toml
[model]
control_max_characters = 8   # CharacterControl on (needs label maps)
control_feat_dim = 3         # per-character features
control_frame_dim = 4        # FrameControl on: speech, loudness, valence, arousal
```
* **Training data**: `python -m studio dataset` already writes `control/<episode>/<clip>.npz` (speech + loudness from the real audio, per
  latent frame) and a `control` field in every `train_<N>s.jsonl` row (`PreembeddingDataset` loads it; all rows must have it, or none).
  Label maps / per-character features use the same file format (`control_data.py`); producing them needs the vision stage (GPU).
* **Generation**: `python -m studio create` writes `episodes/<n>/control/video_*.npz` from the regenerated voices and references it in the
  prompt files; `sample.py` loads it and the sampler passes it to both the conditional and unconditional pass. A model without adapters ignores it.
* Valence/arousal columns are zeros unless you pass `control_emotion=True` *and* trained with them (real footage has no per-line emotion).

## Honest status
* Tested on CPU: module behaviour (zero-init identity, per-character gathering, frame broadcast, shape errors), data builders, checkpoint
  fallback logic, init. **Not run**: the DiT with the adapters inside a real forward/backward, any training of the adapters, any generation.
* Whether it helps is an empirical question: adapter training on your material, then A/B against the base on the same seeds.
* Not changed: resolution, fps, maximum length, base visual quality, number of denoising steps. Bigger leaps (a newer backbone, higher
  resolution, few-step distillation) are model work, not framework work.
* Not done: reference-image identity (a photo of the character as input) and the layout/mouth data pipeline for real footage.
