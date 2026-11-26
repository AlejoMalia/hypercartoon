"""Learn the sound material of the corpus: reference clips per character voice + ambience clips.
One audio decode per episode feeds VAD, soundtrack classification, voice vectors and candidate selection."""
import json
import os
import subprocess
from typing import Callable, Dict, List

import numpy as np

from studio.audio import SR, _ffmpeg, energy_vad, load_audio, logmel_embedding
from studio.emotion.prosody import features as prosody_features
from studio.sound import analyze as A


def _unit(v):
    v = np.asarray(v, np.float64)
    return v / (np.linalg.norm(v) + 1e-12)


class AudioAbsorber:
    """Callable used as the `speech` backend of absorb_corpus; also collects candidates for the banks."""

    def __init__(self, embed: Callable = logmel_embedding, per_episode: int = 40, min_speech_ratio: float = 0.4):
        self.embed, self.per_episode, self.min_ratio = embed, per_episode, min_speech_ratio
        self.voice_cands: Dict[str, List[dict]] = {}
        self.ambience: Dict[str, List[dict]] = {}
        self.sound: Dict[str, dict] = {}
        self.prosody: Dict[str, List[dict]] = {}

    def __call__(self, path: str):
        w = load_audio(path, SR)
        if len(w) < SR:
            return []
        tl = A.classify(w)
        self.sound[path] = A.ratios(tl)
        # energy VAD + soundtrack classifier: drop 'speech' segments that are really music/effects
        segs = [(a, b) for a, b in energy_vad(w, SR) if A.label_ratio(tl, a, b, "speech") >= self.min_ratio]
        out, cands, pros = [], [], []
        for a, b in segs:
            clip = w[int(a * SR) : int(b * SR)]
            vec = self.embed(clip)
            out.append((a, b, vec))
            pros.append({"start": a, "end": b, "vec": _unit(vec).round(3).tolist(), "feat": prosody_features(clip)})
            if 2.5 <= b - a <= 14:
                q = A.snr_db(clip) + 10 * (1 - A.label_ratio(tl, a, b, "music")) + min(b - a, 8)
                cands.append({"start": a, "end": b, "quality": float(q), "f0": A.pitch_f0(clip), "vec": _unit(vec).tolist()})
        self.prosody[path] = pros
        self.voice_cands[path] = sorted(cands, key=lambda c: -c["quality"])[: self.per_episode]
        self.ambience[path] = [{"start": a, "end": b, "level_db": float(10 * np.log10((w[int(a * SR):int(b * SR)] ** 2).mean() + 1e-12))}
                               for a, b, k in tl if k == "ambient" and b - a >= 4.0][:6]
        return out

    def save(self, ws: str) -> None:
        os.makedirs(ws, exist_ok=True)
        json.dump({"voice": self.voice_cands, "ambience": self.ambience, "sound": self.sound, "prosody": self.prosody},
                  open(os.path.join(ws, "audio_candidates.json.tmp"), "w"))
        os.replace(os.path.join(ws, "audio_candidates.json.tmp"), os.path.join(ws, "audio_candidates.json"))


def _extract(src: str, start: float, dur: float, dst: str, sr: int = 24000) -> None:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    subprocess.run([_ffmpeg(), "-v", "error", "-y", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", src,
                    "-vn", "-ac", "1", "-ar", str(sr), dst], check=True)


def build_bank(ws: str, voice_clusterer, per_voice: int = 3, n_ambience: int = 6) -> dict:
    """Pick the best clean reference clips for every voice id and a few ambience beds. Voice ids are re-assigned by
    nearest centroid, so merges done by Registry.consolidate() are respected."""
    cands = json.load(open(os.path.join(ws, "audio_candidates.json")))
    per: Dict[int, List[dict]] = {}
    for path, lst in cands["voice"].items():
        for c in lst:
            best = max(voice_clusterer.sums, key=lambda k: float(_unit(c["vec"]) @ voice_clusterer.centroid(k)),
                       default=None)
            if best is not None:
                per.setdefault(best, []).append(dict(c, episode=path))
    manifest = {"voices": {}, "ambience": []}
    for vid, lst in per.items():
        picked = []
        for c in sorted(lst, key=lambda c: -c["quality"]):
            if len({p["episode"] for p in picked}) < 2 or c["episode"] not in {p["episode"] for p in picked} or len(picked) < per_voice:
                picked.append(c)
            if len(picked) >= per_voice:
                break
        for i, c in enumerate(picked):
            dst = os.path.join(ws, "bank", "voices", str(vid), f"ref_{i}.wav")
            _extract(c["episode"], c["start"], c["end"] - c["start"], dst)
            manifest["voices"].setdefault(str(vid), []).append(
                {"wav": dst, "episode": c["episode"], "start": c["start"], "end": c["end"], "f0": c["f0"], "quality": c["quality"]})
    amb = sorted(((p, a) for p, lst in cands["ambience"].items() for a in lst), key=lambda x: x[1]["level_db"])
    seen = set()
    for p, a in amb:
        if p in seen and len(seen) < len(cands["ambience"]):
            continue
        seen.add(p)
        dst = os.path.join(ws, "bank", "ambience", f"amb_{len(manifest['ambience'])}.wav")
        _extract(p, a["start"], min(a["end"] - a["start"], 20.0), dst, sr=SR)
        manifest["ambience"].append({"wav": dst, "episode": p, "level_db": a["level_db"]})
        if len(manifest["ambience"]) >= n_ambience:
            break
    os.makedirs(os.path.join(ws, "bank"), exist_ok=True)
    json.dump(manifest, open(os.path.join(ws, "bank", "manifest.json"), "w"), indent=1)
    return manifest


class Bank:
    def __init__(self, ws: str):
        self.ws = ws
        p = os.path.join(ws, "bank", "manifest.json")
        self.m = json.load(open(p)) if os.path.exists(p) else {"voices": {}, "ambience": []}

    def reference(self, voice_id) -> str:
        if isinstance(voice_id, str) and voice_id.startswith("clone:"):  # a character cloned from the voice library (studio/voices.py)
            from studio.voices import VoiceLibrary

            return VoiceLibrary(self.ws).reference(voice_id[len("clone:"):])
        lst = self.m["voices"].get(str(voice_id)) if voice_id is not None else None
        return lst[0]["wav"] if lst else ""

    def ambience_wav(self) -> str:
        return self.m["ambience"][0]["wav"] if self.m["ambience"] else ""
