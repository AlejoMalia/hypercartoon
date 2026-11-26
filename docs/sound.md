# Sound system (internal)

Everything about the soundtrack lives in `studio/sound/`: what is on it, which voice belongs to which character,
regeneration of dialogue, and the mix. Nothing here depends on the video model.

```bash
python -m studio learn SHOW/ --characters     # also builds studio_ws/bank/: voice references + ambience beds
python -m studio create guion.txt             # FOX: Hola!  ->  voices.json (who says what, per 3 s segment)
python -m studio sound --speaker scratch      # guide dialogue + ducked ambience  -> studio_ws/sound/video_000.wav
python -m studio sound --speaker chatterbox --video out.mp4   # cloned voices, muxed into the generated video
```

## Pieces
| Module | Job | Dependencies |
|---|---|---|
| `analyze.py` | soundtrack timeline (speech / music / ambient / silence), f0, clip quality | numpy |
| `bank.py` | one decode per episode -> VAD, classifier, voice vectors, best clean reference clips per voice, ambience beds; speech segments the classifier calls music are dropped | numpy + ffmpeg |
| `speak.py` | `ScratchVoice` (built-in guide voice at the character's measured pitch, gives real line durations), `ChatterboxSpeaker` (zero-shot cloning from the reference clip) | none / `chatterbox-tts` |
| `mix.py` | timeline placement, late-line report, looped ambience with crossfades, side-chain ducking, loudness normalisation, WAV + ffmpeg mux | numpy + ffmpeg |
| `separate.py` | dialogue vs rest with Demucs (clean references when music sits under the dialogue) | `demucs` |
| `tagger.py` | AudioSet tags (527 classes: rain, door, crowd...) for richer ambience labels | `panns-inference` |

Recognition of *who* speaks is in `studio/characters.py` (voice clusters + audio-visual lift) and feeds the bank.

## What the research suggests (checked Nov 2026; licences are secondhand, **verify each repo's LICENSE before shipping**)
* Voice cloning: Chatterbox (zero-shot from ~5 s, reported MIT or MPL-2.0 depending on source) and the Qwen3 voice model
  (reported Apache-2.0, ~3 s reference) look usable commercially; F5 and Fish Speech weights are reported
  non-commercial. CosyVoice/IndexTTS terms were not confirmed. OpenVoice V2 (MIT) is the candidate for *voice conversion*
  (re-voicing an existing line with the character's timbre) rather than synthesis.
* Separation: BS-RoFormer / Mel-RoFormer beat HT-Demucs on MUSDB18-HQ (reported 9.8 vs 7.5 dB SDR) but are music
  stem models; no dialogue/music/effects model was found. Demucs is wired because it is stable and simple.
* Effects and ambience generation from the picture: HunyuanVideo-Foley (Tencent community licence, excluded in
  EU/UK/South Korea) and MMAudio (licence not confirmed). Not wired; the ambience bank reuses sound from the corpus instead.
* Tagging: PANNs / BEATs on AudioSet. Diarization: pyannote 3.1; VAD: silero-vad (not confirmed in the searches).

## Honest limits
* The built-in classifier is a heuristic calibrated on synthetic signals only; recalibrate thresholds on a few real
  episodes, or use `tagger.py`. Music with strong vocals, sung lines and speech over loud effects are the hard cases.
* `ScratchVoice` is a guide track, not a voice. Real quality needs `ChatterboxSpeaker` (GPU, validate) or another speaker.
* A 3-second segment fits roughly 8-10 syllables; longer lines are reported as `late_lines` instead of being squeezed.
* Emotion, lip-sync and sound effects tied to on-screen events are not modelled.
