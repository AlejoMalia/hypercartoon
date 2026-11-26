# Terminal version

```bash
python -m studio            # or: hypercartoon  |  python -m hypercartoon [VIDEO_OR_FOLDER] [--out DIR] [--script GUION] [--no-create]
```

1. It asks: **1) a video**, **2) a folder** (several videos / seasons; Tab completes paths) or **3) online** — URL, YouTube video / playlist / channel, `.txt` list, torrent or magnet (see [sources](sources.md)). Inputs can also be given as arguments, any number, mixed.
2. **Learning panel**: one row per phase with state, bar, %, elapsed time and ETA, plus a weighted overall bar.

   | # | Phase | What it produces |
   |---|---|---|
   | 1 | Scan and video analysis | shots, motion, palette, durations (`manifest.json`; unchanged files are never re-read) |
   | 2 | Seasons and episodes | `corpus.json` |
   | 3 | Style, rhythm and training plan | `profile.json`, `plan.json`, `make_segments.sh` |
   | 4 | Camera, framing, elements, colour and dialogue | `analysis/` (json, report, srt, colour pictures), `profile.json["cinematography"]` |
   | 5 | Characters, objects and voices | `registry.json` (needs `[perception]` for the visual part; voices always) |
   | 6 | Sound bank and voice emotion | `bank/`, `emotion_profile.json` |
   | 7 | Mouth convention | `mouth_style.json` |
   | 9 | Captions and training dataset | `dataset/` (clips, captions, `train_<N>s.jsonl`, control files, `COMANDOS.md`) |
   | 10 | Material sufficiency | `REQUISITOS.md` (verdict per capability, minutes missing) |
   | 11 | Episode package | `episode_kit.json`, `LEEME.md` |

3. A box says **PROCESO COMPLETADO** with total time and the folder. Phases that could not run (missing optional packages)
   are listed as *parcial/omitida* with the exact install hint; an error in one optional phase never loses the rest.
4. It offers to **create an episode** from a script or prompt: a second panel (script reading, emotion, prompts and compute
   plan, voices, mouth + mix, audio control, package) writes `episodes/episodio_NN/` with `prompts*.jsonl`, `voices.json`, `sound/*.wav`,
   mouth tracks, `story_report.md` (Spanish) and `episode.json` with the GPU commands for the video itself.

Not a TTY (pipes, CI)? It prints one progress line per 25 %. Everything is stdlib; no `rich`.
The pipelines are plain lists of `Phase(...)` in `studio/learning.py` and `studio/episode.py`; add a phase by adding one entry.
