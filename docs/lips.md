# Lip-sync

Three layers, all in `studio/lips/`:

* **Show convention** (`style.py`, `python -m studio lips`): from episodes, measures mouth activity in the video during
  speech and the voice envelope, then learns how the show animates: *hold* (how many frames a mouth shape is kept: animating
  "on 2s/3s"), the discrete mouth *levels*, the *lead* (the mouth moves before the sound) and the *gain*. Saved in
  `mouth_style.json`.
* **Mouth tracks for new dialogue** (`visemes.py`, `rhubarb.py`): backend priority is Rhubarb cues (audio-accurate, needs the `rhubarb` binary) > word-timed visemes (faster-whisper word timestamps) > text visemes. Each track records its `method`.
  Text path: text -> 10 cartoon mouth shapes (REST, AI, E, O, U, FV, L, MBP, WQ, ETC),
  durations time-warped to the loudness of the regenerated voice, then quantised/held/shifted with the learned style.
  `python -m studio sound` writes `sound/video_000_mouths.json` (per-line openness at the show's fps) for animators or an
  animatic overlay.
* **Sync with a generated video** (`sync.py`): `python -m studio sound --video out.mp4 --sync` measures the mouth activity
  of the generated video, re-times each voice line (+-0.6 s, lines never overlap) to maximise correlation with it and
  prints the score before/after.

Limits (read before trusting it):
* Mouth measurement from video is a classical cue (motion + dark-interior change in the lower face box), not landmarks.
  It needs a face box (or a close-up with one speaker). A landmark model should replace `mouth_series_from_video`
  for realistic faces; the rest of the pipeline only needs a 0..1 series.
* The video model generates picture only; there is no mouth inpainting. Sync is achieved by moving the *voice* to the
  mouths, or by giving animators the mouth track. Making the generated mouths follow a given voice would need audio
  conditioning in the DiT, which means retraining (GPU).
* Validated only on synthetic signals so far.
