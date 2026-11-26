# Style fusion

Give it two (or more) learned projects, get an intermediate one.

```bash
python -m studio fuse proj_A proj_B --weights 0.7 0.3 --out proj_AB          # concept + embedding recipe
python -m studio --workdir proj_AB create guion.txt                          # prompts carry alt_text + mix
python -m studio fuse-weights --ckpt A.safetensors:0.5 B.safetensors:0.5 --out AB.safetensors            # model soup
python -m studio fuse-weights --base base.safetensors --ckpt A.safetensors:0.7 B.safetensors:0.4 --out AB.safetensors  # task arithmetic
```

## Three levels
1. **Concept (CPU, tested)** — `studio/fusion.py`: pacing (shot length, cuts/min) blended in log space (the "middle" of 1.5 s and
   6 s shots is 3 s, not 3.75 s), motion and brightness linearly, palette mixed in **linear light**, mouth convention
   (hold, levels, lead), cast and voice banks united (ids shifted; a name present in both gets a `_SOURCE` suffix), training
   plan recomputed on the union. The result is a normal project: `create`, `sound`, the terminal panel all work on it.
2. **Embedding (sampler, not run on GPU)** — every 3-second segment is written twice (style A, style B) and the sampler
   interpolates the T5 text embeddings: `emb = (1-mix)·emb(A) + mix·emb(B)` (`hypercartoon/models/cogvideo/prompts.py`,
   `sample.py`). With more than two sources the two heaviest are used.
3. **Weights (not run on GPU)** — `merge_state_dicts`: weighted average of two fine-tunes of the same base, or task arithmetic
   `base + Σ wᵢ(θᵢ − base)`. Needs consolidated `.safetensors` / `.pt` state dicts (not distributed-checkpoint folders).

## What you must know
* Levels 2 and 3 only produce a believable in-between if the model **knows both styles**: fine-tune on both, and give each
  source its own style token in the captions (the recipe `fusion.json` lists the style prompts that are used).
* Interpolation can fall off the manifold: values like 0.3-0.7 may give a blend, a flicker between styles, or artefacts.
  Try several mix values on a short clip first (`prompts` accept any `mix` in 0..1).
* Level 1 changes how the studio plans (pacing, mouth, palette hints, cast); it does not by itself redraw anything.
* Style here means the measured statistics (rhythm, motion, colour, mouth conventions) plus text/embedding/weight
  interpolation; nothing measures line quality, character design or "feel", so it can't tell you whether the blend looks good.
