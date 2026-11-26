# Studio: learn from a folder, create from a script

```bash
python -m studio learn  MY_CARTOONS/              # analyse content + time, build profile, plan curriculum
bash studio_ws/make_segments.sh                   # 3s/16fps/480x720 segments (ffmpeg, CPU)
# GPU: data/precomp_video.py, data/precomp_text.py, then train the stages listed in studio_ws/plan.json
python -m studio create guion.txt                 # script -> scenes -> 3s segments -> prompts.jsonl + sample command
```

* `learn` is incremental (unchanged files are never re-analysed) and writes `manifest.json`, `profile.json`
  (shot length, cuts/min, motion, brightness, palette, learned style prompt), `plan.json`, `make_segments.sh`.
* Auto plan: a stage (3/9/18/30/63 s) is only trained if the data holds >= 32 clips of that length; `hyper_mlp` needs
  >= 80 GB, otherwise `hyper_linear`; steps scale with clip count.
* Script format: blank-line separated scenes; `[6s]` sets duration (default = learned median shot, snapped to 3 s);
  `NEG:` negative prompt; `INT.`/`EXT.` forces a scene transition. The learned style prompt is appended to every segment.
* `studio/regulate.py`: generate -> score (`hypercartoon.perception.coherence_report`) -> retry with new seed, escalating
  steps only on near-misses, bounded attempts; keeps the best. Not yet wired into `sample.py` (needs GPU to test).

## Multi-season corpus, characters and voices

```bash
python -m studio learn SHOW/ --characters     # SHOW/S01/E01.mp4, SHOW/Temporada 2/cap_3.mkv, 1x03.mp4 ... all understood
python -m studio characters                   # [id] name kind seconds episodes voice
python -m studio name 3 FOX                   # give a learned identity its script name
python -m studio create guion.txt             # FOX: Hola!  -> character look injected + voices.json sidecar for dubbing
```

* `corpus.py` infers series/season/episode from paths; `learn` is incremental, so adding season 2 later only
  processes the new episodes (`registry.json` remembers every absorbed file by size+mtime). More episodes = more clips per
  stage in `plan.json` and sharper character evidence. `profile.json` keeps a profile per season (style drift) and the
  typical chapter length.
* `characters.py`: online cosine clustering of per-track appearance vectors (cross-episode identity) and of voice
  vectors; a voice is assigned to a character by audio-visual *lift* (speaks while on screen, relative to how often it is
  on screen), accumulated across episodes so a character that is always on screen is not wrongly credited.
* Backends (lazy, **not validated here**): objects = YOLO-seg + ByteTrack, appearance = DINOv2 crops, voices =
  SpeechBrain ECAPA (`--voice ecapa`, default; `--voice logmel` is the weak numpy fallback), speech = energy VAD
  (swap for pyannote/silero on music-heavy cartoons), transcripts = faster-whisper (`studio/audio.py:transcribe`).
* Limits: the engine generates video only. Voices are recognised and mapped to characters, and dialogue goes to
  `voices.json`; regenerating the audio is done by the sound system (see [docs/sound.md](sound.md)). Cartoon characters that change outfit may split into several ids;
  `Registry.consolidate()` merges close ones and `studio name` lets you name both ids the same.
