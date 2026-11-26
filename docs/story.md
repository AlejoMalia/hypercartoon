# Story and compute planning

```bash
python -m studio story guion.txt          # read + validate + Spanish report (story_report.md), no generation
python -m studio create guion.txt         # story -> emotion -> prompts -> compute plan (prompts_s<steps>.jsonl)
python -m studio cache PROMPTS VIDEOS     # record generated videos so unchanged ones are never regenerated
```

## Reading any script (`studio/story/`)
* `convert.py` accepts screenplay (sluglines + CUE lines + parentheticals), `NAME: line` blocks and prose with dash
  dialogue ("—Vuelve —dijo Buho."), and turns it into the studio script. Nothing has to be pre-formatted.
* `pacing.py` makes dialogue fit its scene (about 4 syllables/s). A scene that asked for 3 s but needs 9 s is lengthened
  automatically, so the sound system never reports late lines.
* `native.py` reads scenes, characters, places, four-part arc, a tension curve and open threads (vanished characters,
  tension left high at the end) without any dependency.
* `script_engine.py` runs a small deterministic screenplay reader on plain Node >= 18 (no network, no paid API, no keys; vendored in
  `vendor/script-hypercartoon/`): scene headings, cast, camera vocabulary, dialogue/action shares, a pacing tension curve and simple open
  threads. It only enriches the native reading above and is never required. Its tension curve needs page-scale text; on short scripts it is
  flat and the native curve is used instead.
* `plan.py` validates (dialogue too long, scene longer than the trained stage, characters without a learned look, open
  threads) and writes the report **in Spanish** (`story_report.md`).

## Compute (`studio/budget.py`)
Only the video frames need a GPU. Everything else runs on CPU: story reading, emotion, guide voices, mouth tracks, mixing, planning.
For the frames:
1. **Cache**: videos are remembered by prompt + config (exact or >= 92 % token overlap, and at least the needed steps), so
   editing one scene of a script re-runs only the changed videos.
2. **Adaptive steps**: tension < 35 -> 25 steps, < 65 -> 35, else 50. One prompts file per step count (`sample.py` takes one per run).
3. **Draft then refine** (`--compute draft`): everything at 20 steps, then re-run at 50 only what fails the coherence gate
   (`budget.select_refine`, with `hypercartoon.perception` scores).

Savings are reported in step-segments (steps x 3 s segments) under stated assumptions (25 % refine rate in draft mode);
pass `--sec-per-step-segment` with a number you measured to get GPU seconds. No GPU numbers were measured here, and the
quality cost of fewer steps on this model is untested: check a draft before trusting it.
