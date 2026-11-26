"""Dialogue of a video: transcription with word times (+ speakers), labelled with time, shot ('toma') and scene ('escena').

Backends (lazy; neither was run here):
  whisperx  m-bain/whisperX: Whisper + forced word alignment + pyannote diarization (needs a Hugging Face token for the speakers)
  faster    faster-whisper with word timestamps (no speakers; speakers then come from clustering the voice of each segment)
Speakers without a diarizer: each segment's voice (ECAPA or the built-in log-mel print) is clustered online -> SPEAKER_00, 01...
Output: JSON items and an enriched SRT: "[E3 · T7 · SPEAKER_01] text"."""
import hashlib
import json
import os
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np


def timecode(s: float, srt: bool = False) -> str:
    ms = int(round(s * 1000))
    h, r = divmod(ms, 3600000)
    m, r = divmod(r, 60000)
    sec, ms = divmod(r, 1000)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}" if srt else f"{h:02d}:{m:02d}:{sec:02d}.{ms // 100}"


def _backend_available(name: str) -> bool:
    import importlib.util

    return importlib.util.find_spec({"whisperx": "whisperx", "faster": "faster_whisper"}[name]) is not None


def transcribe_whisperx(path: str, device: str = "cuda", model: str = "small", hf_token: Optional[str] = None, batch_size: int = 16) -> List[Dict]:
    import whisperx

    compute = "float16" if device == "cuda" else "int8"
    audio = whisperx.load_audio(path)
    m = whisperx.load_model(model, device, compute_type=compute)
    res = m.transcribe(audio, batch_size=batch_size)
    am, meta = whisperx.load_align_model(language_code=res["language"], device=device)
    res = whisperx.align(res["segments"], am, meta, audio, device, return_char_alignments=False)
    if hf_token:
        try:
            from whisperx.diarize import DiarizationPipeline
        except Exception:
            DiarizationPipeline = whisperx.DiarizationPipeline  # older releases expose it at the top level
        try:
            dia = DiarizationPipeline(use_auth_token=hf_token, device=device)
        except TypeError:
            dia = DiarizationPipeline(token=hf_token, device=device)
        res = whisperx.assign_word_speakers(dia(audio), res)
    return [{"start": float(s["start"]), "end": float(s["end"]), "text": s["text"].strip(), "speaker": s.get("speaker"),
             "words": [{"start": w.get("start"), "end": w.get("end"), "word": w["word"], "speaker": w.get("speaker")} for w in s.get("words", [])]}
            for s in res["segments"]]


def transcribe_faster(path: str, device: str = "auto", model: str = "small", language: Optional[str] = None) -> List[Dict]:
    from faster_whisper import WhisperModel

    segs, _ = WhisperModel(model, device=device).transcribe(path, word_timestamps=True, vad_filter=True, language=language)
    return [{"start": float(s.start), "end": float(s.end), "text": s.text.strip(), "speaker": None,
             "words": [{"start": w.start, "end": w.end, "word": w.word.strip(), "speaker": None} for w in (s.words or [])]} for s in segs]


def get_transcript(path: str, ws: Optional[str] = None, backend: str = "auto", device: str = "cuda", model: str = "small",
                   hf_token: Optional[str] = None) -> Dict:
    """Cached transcript {backend, segments}. backend: auto | whisperx | faster | off. 'off' / nothing installed -> empty segments."""
    st = os.stat(path)
    key = hashlib.sha1(f"{path}{st.st_size}{backend}{model}".encode()).hexdigest()[:16]
    cache = os.path.join(ws, "transcripts", key + ".v2.json") if ws else None
    if cache and os.path.exists(cache):
        return json.load(open(cache))
    use = backend
    if backend == "auto":
        use = "whisperx" if _backend_available("whisperx") else "faster" if _backend_available("faster") else "off"
    if use == "off" or (use in ("whisperx", "faster") and not _backend_available(use)):
        return {"backend": "off", "segments": [], "note": "sin transcripción: pip install faster-whisper (o whisperx)"}
    segs = transcribe_whisperx(path, device, model, hf_token) if use == "whisperx" else transcribe_faster(path, "cpu" if device != "cuda" else "cuda", model)
    out = {"backend": use, "segments": segs}
    if cache:
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        json.dump(out, open(cache, "w"), ensure_ascii=False)
    return out


def assign_speakers(segments: List[Dict], wave: np.ndarray, sr: int = 16000, embed: Optional[Callable] = None, thr: float = 0.85) -> List[Dict]:
    """Fill `speaker` for segments that have none, by online clustering of each segment's voice. Stable within the video only."""
    from studio.audio import logmel_embedding
    from studio.characters import OnlineClusterer

    embed = embed or logmel_embedding
    cl = OnlineClusterer(thr)
    for s in segments:
        if s.get("speaker"):
            continue
        clip = wave[int(s["start"] * sr) : int(s["end"] * sr)]
        if len(clip) < sr // 4:
            s["speaker"] = None
            continue
        s["speaker"] = f"SPEAKER_{cl.add(embed(clip)) - 1:02d}"
    return segments


def label_dialogue(segments: Sequence[Dict], shots: Sequence[Dict], scene_of_shot: Sequence[int]) -> List[Dict]:
    """Each segment gets its shot(s), scene, timecodes and the offset inside its shot. A segment crossing a cut lists every shot it touches;
    the primary shot / scene is the one it overlaps most."""
    out = []
    for i, s in enumerate(segments):
        ov = [(max(0.0, min(s["end"], sh["end"]) - max(s["start"], sh["start"])), j) for j, sh in enumerate(shots)]
        touched = [j for o, j in ov if o > 0]
        primary = max(ov)[1] if ov and max(ov)[0] > 0 else (len(shots) - 1 if s["start"] >= shots[-1]["end"] else 0) if shots else None
        out.append({"id": i, "start": s["start"], "end": s["end"], "timecode": f"{timecode(s['start'])}–{timecode(s['end'])}", "text": s["text"],
                    "speaker": s.get("speaker"), "shot": primary, "shots": touched or ([primary] if primary is not None else []),
                    "scene": scene_of_shot[primary] if primary is not None else None,
                    "shot_offset_s": (s["start"] - shots[primary]["start"]) if primary is not None else None,
                    "crosses_cut": len(touched) > 1, "words": s.get("words", [])})
    return out


def to_srt(items: Sequence[Dict], labels: bool = True) -> str:
    blocks = []
    for n, it in enumerate(items, 1):
        tag = f"[E{it['scene'] + 1} · T{it['shot'] + 1} · {it['speaker'] or '?'}] " if labels and it["scene"] is not None else ""
        blocks.append(f"{n}\n{timecode(it['start'], True)} --> {timecode(it['end'], True)}\n{tag}{it['text']}\n")
    return "\n".join(blocks)


def by_scene(items: Sequence[Dict]) -> Dict[int, Dict]:
    out: Dict[int, Dict] = {}
    for it in items:
        d = out.setdefault(it["scene"], {"lines": 0, "words": 0, "speakers": set(), "start": it["start"], "end": it["end"]})
        d["lines"] += 1
        d["words"] += len(it["text"].split())
        if it["speaker"]:
            d["speakers"].add(it["speaker"])
        d["start"], d["end"] = min(d["start"], it["start"]), max(d["end"], it["end"])
    return {k: dict(v, speakers=sorted(v["speakers"])) for k, v in out.items()}
