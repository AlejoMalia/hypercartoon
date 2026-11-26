# How much material is enough, and how long things take

```bash
python -m studio check --workdir PROJECT    # verdict per capability + what is missing (REQUISITOS.md, requirements.json)
python -m studio bench --out bench_out      # timing catalog on this machine (TIEMPOS.md, timings.json); --resolution W H = your footage
```
The terminal learning panel runs the check as a phase and shows the verdict in the completion box.

## Content needed (verdict: insuficiente < mínimo < bueno < óptimo)
| Capability | Mínimo | Bueno | Óptimo | Basis |
|---|---|---|---|---|
| Total material | 20 min | 2 h | 7 h | the original TTT-Video trained on ≈7 h of Tom and Jerry in 3-s annotated segments (arXiv 2504.05298) |
| Episodes | 2 | 10 | 26 | ≥2 to recognise a character across episodes |
| Shots analysed | 30 | 150 | 500 | statistics of pacing / style |
| Pacing precision (±95 % bootstrap CI of median shot length) | 25 % | 12 % | 6 % | data-driven: depends on how variable the show is |
| Clips per stage (3/9/18/30/63 s) | 32 | 25 % of reference | reference (7 h / stage length) | 32 = planner minimum; reference = original scale |
| Dialogue | 5 min | 30 min | 2 h | feeds voices, voice emotion, mouths, story |
| Characters ≥30 s on screen | 1 | 3 | 6 | needs the vision stage |
| Clean voice reference (least-heard voice) | 5 s | 15 s | 30 s | cloning models quote 3-5 s; more, from several scenes, generalises better |
| Voice-emotion baseline segments | 5 | 30 | 100 | baseline needs ≥5 |
| Frames with speech for the mouth convention | 300 | 3,000 | 15,000 | ~12 s / 2 min / 10 min at 24 fps |
| Ambience beds | 1 | 3 | 6 | |

**These thresholds are engineering heuristics, not measured optima**; only the 7 h anchor, the 32-clip minimum and the 3-5 s voice figure come
from outside. The report states "faltan N clips (≈ M min de material)" for each unmet level. For example, a 3-s stage at *óptimo* is 8,400 clips.

## Time catalog
`bench` builds synthetic shows of several sizes, runs every CPU phase and fits `seconds = fixed + per_minute × content_minutes` per phase
(and per dialogue line for episode creation), then projects to 10 min / 1 h / 7 h. Real footage decodes slower than the synthetic frames
(use `--resolution`), and phases that need a GPU or optional packages (vision, VLM captions, transcription, video generation, training)
are **not measured**: generation is a formula in step-segments that becomes seconds when you pass `--sec-per-step-segment`. Reference: the
original training run took the equivalent of 50 h on 256 H100 for its whole curriculum (paper).
