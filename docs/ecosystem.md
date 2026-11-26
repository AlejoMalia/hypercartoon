# Ecosystem: what was found, what is integrated

Research done Nov 2026 with web search (licences are secondhand: **read each repo's LICENSE**). "Integrated" = code in this
repository with tests on CPU; nothing marked GPU was executed here.

| Need | Repo | Status |
|---|---|---|
| Denoising speed-up without retraining | [ali-vilab/TeaCache](https://github.com/ali-vilab/TeaCache) (CVPR 2025, has CogVideoX support) | **Integrated, opt-in**: `hypercartoon/infra/step_cache.py` + hook in `DiffusionTransformer.forward`, `eval.step_cache_threshold` (0 = off). Without TeaCache's fitted rescaling polynomial the threshold is in raw units: tune on a short clip. GPU-unvalidated |
| CFG-level cache | Vchitect/FasterCache (ICLR 2025; CFG-Cache reuses cond/uncond differences) | Not integrated: needs per-layer feature caches in the DiT. The cache here already keeps one residual per CFG stream |
| Cartoon mouth shapes from audio | DanielSWolf/rhubarb-lip-sync (shapes A-F + extended G/H/X, JSON export) | **Integrated**: `studio/lips/rhubarb.py`; used first by `mouth_for_clip` when the `rhubarb` binary exists (`HYPERCARTOON_RHUBARB` or PATH) |
| Word timestamps / diarization | m-bain/whisperX (word alignment, pyannote diarization) | Word timing via faster-whisper (`studio.audio.transcribe_words`) feeds `viseme_track_words`; WhisperX not wired (diarization needs an HF token) |
| Better shot detection | Breakthrough/PySceneDetect (AdaptiveDetector) | **Integrated, optional**: `studio/ingest.py` uses it when installed (not confirmed by the searches, API from its docs) |
| Captions for training | Qwen2.5-VL (used as re-captioner in ViMix-14M), VC4VG study of captioners for CogVideoX | **Integrated**: `studio/dataset.py` (`QwenVLCaptioner`, GPU, unvalidated) + a CPU heuristic captioner; builds `train_<N>s.jsonl`, `text_input.json` for `data/precomp_text.py`, clip scripts, `COMANDOS.md` |
| Lip-sync of generated video | bytedance/LatentSync (Apache-2.0 per third parties), TMElyralab/MuseTalk (licence unclear) | **Hook only**: `studio/postprocess.py` runs commands you declare in `postprocess.json`; I did not hard-code their CLIs |
| Cartoon in-betweening | ToonCrafter (SIGGRAPH Asia 2024; two keyframes -> 16 frames at 512x320) | Not integrated: fixed resolution, unreliable success rate; possible later for "keyframes + in-betweens" to cut compute |
| Evaluation | Vchitect/VBench (subject consistency, motion smoothness, ...) | Not integrated (own environment and datasets); `hypercartoon/perception` has comparable cheap metrics |
| Voice cloning / separation | Chatterbox, Demucs, PANNs | Already in `docs/sound.md` |

## What the framework still lacks (honest list)
1. **Identity conditioning in the DiT** (reference images / per-character embeddings) - needs retraining.
2. **Audio-conditioned mouths in the generator** (so the picture follows the voice instead of the voice following the picture) - needs retraining.
3. **Real measurements**: nothing has been timed or scored on a GPU; step-cache thresholds, draft step counts and mix values are starting points.
4. **Distilled few-step sampling** (consistency / self-forcing style) would cut compute far more than caching; not attempted.
