"""Voice library: clone the voice of every character from *audio alone*, independent of the image / animation learning.

The learning panel can find voices inside the episodes (and `from_corpus` promotes them), but a cloned voice should not depend on that:
the best material is often elsewhere — a clean dubbing recording, an interview, a playlist of the actor's clips. Any input the studio can
read works (audio or video files, folders, URLs, YouTube videos / playlists, torrents; `docs/sources.md`) and only the soundtrack is kept.

For each character `NAME` the library keeps  voices/NAME/{ref_primary.wav, ref_long.wav, clips/, profile.json}:
  * the speech is cut into utterances, the **dominant speaker** is kept (other voices, music and noise are rejected by embedding distance),
    each clip is scored (signal-to-noise, clipping), loudness-normalised, and the best are assembled into a short primary reference (what
    zero-shot cloners want, ~8 s) and a long one (~30 s);
  * the profile stores the voice embedding, sources, language, quality, an honest sufficiency verdict and the links to the character
    (aliases, corpus voice id).
At creation every speaking character is bound by name to its profile (`voice_id = "clone:NAME"`), the speaker backend (Chatterbox, XTTS-v2,
F5-TTS) clones from that reference, and `verify` measures whether a generated line is closer to its own character than to any other.
Embeddings: dependency-free log-mel statistics by default (weak but real); ECAPA when installed (`embedder="ecapa"`)."""
import json
import os
import re
import shutil
import time
import unicodedata
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from studio.audio import energy_vad, load_audio, logmel_embedding

SR = 24000
PREFIX = "clone:"
MIN_S, GOOD_S, BEST_S = 5.0, 15.0, 30.0       # reference seconds: cloners quote 3-5 s as the floor; more clean speech holds the timbre better
PRIMARY_S = 8.0


def _key(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").upper()


def _unit(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, np.float64)
    return v / (np.linalg.norm(v) + 1e-12)


class Embedder:
    """A callable voice descriptor with the metric that fits it (`euclid` for the built-in voiceprint, `cos` for neural embeddings)."""

    def __init__(self, fn: Callable, name: str, metric: str):
        self.fn, self.name, self.metric = fn, name, metric

    def __call__(self, w: np.ndarray) -> np.ndarray:
        return np.asarray(self.fn(w), np.float64)

    def dist(self, a: np.ndarray, b: np.ndarray) -> float:
        return float(np.linalg.norm(a - b)) if self.metric == "euclid" else float(1.0 - _unit(a) @ _unit(b))

    @property
    def floor(self) -> float:  # smallest spread that is meaningful for this metric
        return 0.3 if self.metric == "euclid" else 0.02


def voiceprint(w: np.ndarray, sr: int = SR) -> np.ndarray:
    """Dependency-free descriptor: median pitch (octave-scaled), the level-free spectral envelope (mean log-mel minus its average) and
    its variation. Separates a deep voice from a high one and different timbres; much weaker than ECAPA (use `ecapa` for real material)."""
    from studio.sound.analyze import pitch_f0

    f0 = pitch_f0(_resample(w, sr, 16000))
    f0 = f0 if f0 > 0 else 150.0
    lm = logmel_embedding(w, sr)
    return np.concatenate([[4.0 * np.log2(f0 / 100.0)], lm[:40] - lm[:40].mean(), lm[40:] * 0.5])


def get_embedder(kind: str = "auto", device: str = "cpu") -> Embedder:
    if kind == "auto":  # ECAPA (speechbrain) when installed: far better than the built-in descriptor on real voices
        import importlib.util

        kind = "ecapa" if importlib.util.find_spec("speechbrain") is not None and importlib.util.find_spec("torch") is not None else "voiceprint"
    if kind in ("voiceprint", "logmel"):
        return Embedder(voiceprint, "voiceprint", "euclid")
    if kind == "ecapa":
        from studio.audio import ecapa_embedder

        f = ecapa_embedder(device)
        return Embedder(lambda w: f(_resample(w, SR, 16000), 16000), "ecapa", "cos")
    raise ValueError("embedder: voiceprint | ecapa")


def _resample(w: np.ndarray, a: int, b: int) -> np.ndarray:
    if a == b:
        return w
    n = int(len(w) * b / a)
    return np.interp(np.linspace(0, len(w) - 1, n), np.arange(len(w)), w).astype(np.float32)


# ---- from raw audio to clean reference clips --------------------------------------------------------------------------------------------------
def quality(w: np.ndarray, sr: int = SR) -> Dict[str, float]:
    """snr_db: loud frames vs the quietest 10 % of frames; clip: fraction of samples at full scale; score in 0..1."""
    n = int(0.03 * sr)
    f = w[: len(w) // n * n].reshape(-1, n)
    e = (f ** 2).mean(1) + 1e-12
    snr = float(10 * np.log10(np.mean(np.sort(e)[len(e) // 2 :]) / np.mean(np.sort(e)[: max(1, len(e) // 10)])))
    clip = float((np.abs(w) > 0.99).mean())
    return {"snr_db": snr, "clip": clip, "score": float(np.clip(snr / 35.0, 0, 1) - 5 * clip)}


def normalize(w: np.ndarray, rms_target: float = 0.07, peak: float = 0.95) -> np.ndarray:
    r = float(np.sqrt((w ** 2).mean()) + 1e-9)
    w = w * (rms_target / r)
    return (w * min(1.0, peak / (np.abs(w).max() + 1e-9))).astype(np.float32)


def utterances(w: np.ndarray, sr: int = SR, min_s: float = 1.5, max_s: float = 12.0, gap: float = 0.6) -> List[Tuple[float, float]]:
    """Speech ranges merged across short pauses into clips of at most `max_s` (long ranges are cut), dropping the ones under `min_s`."""
    rng = energy_vad(w, sr, min_speech=0.3, max_gap=gap)
    out: List[List[float]] = []
    for a, b in rng:
        if out and a - out[-1][1] <= gap and b - out[-1][0] <= max_s:
            out[-1][1] = b
        else:
            out.append([a, b])
    cut: List[Tuple[float, float]] = []
    for a, b in out:
        while b - a > max_s:
            cut.append((a, a + max_s))
            a += max_s
        cut.append((a, b))
    return [(a, b) for a, b in cut if b - a >= min_s]


def dominant_speaker(emb: np.ndarray, embed: Optional[Embedder] = None, keep_frac: float = 0.5) -> Tuple[np.ndarray, np.ndarray]:
    """-> (keep mask, distance of every clip to the voice centroid). The centroid is the mean of the clips closest to the medoid, so a
    minority of other voices, music or noise cannot drag it away; clips far beyond the typical spread are dropped."""
    embed = embed or get_embedder()
    n = len(emb)
    if n < 3:
        return np.ones(n, bool), np.zeros(n)
    D = np.array([[embed.dist(a, b) for b in emb] for a in emb])
    seed = int(np.argmin(D.mean(1)))
    core = np.argsort(D[seed])[: max(3, int(np.ceil(keep_frac * n)))]
    cen = np.mean(emb[core], 0)
    d = np.array([embed.dist(e, cen) for e in emb])
    med = float(np.median(d))
    mad = float(np.median(np.abs(d - med)))
    return d <= med + 3.0 * max(mad, 0.5 * embed.floor) + embed.floor, d


def speech_like(seg: np.ndarray, sr: int = SR) -> bool:
    """Speech swings between loud and quiet syllable by syllable (coefficient of variation of the power); a held chord barely does
    and white noise has a wild, structureless spectrum (flux). Rhythmic music can pass: separate vocals first (`--separate`).
    Thresholds were set on synthetic signals only."""
    n, h = int(0.025 * sr), int(0.01 * sr)
    if len(seg) < 2 * n:
        return False
    idx = np.arange(0, len(seg) - n, h)[:, None] + np.arange(n)[None]
    f = seg[idx].astype(np.float64)
    pw = (f ** 2).mean(1)
    sp = np.abs(np.fft.rfft(f * np.hanning(n), axis=1)) ** 2
    B = np.log(np.stack([sp[:, b].sum(1) for b in np.array_split(np.arange(sp.shape[1]), 24)], 1) + 1e-8)
    B = B - B.mean(1, keepdims=True)
    cs = (B[1:] * B[:-1]).sum(1) / (np.linalg.norm(B[1:], axis=1) * np.linalg.norm(B[:-1], axis=1) + 1e-9)
    flux, cv = float((1 - cs).mean()), float(pw.std() / (pw.mean() + 1e-12))
    return flux <= 0.6 and cv >= 0.6


def prepare(w: np.ndarray, embed: Embedder, source: str = "", sr: int = SR) -> List[Dict]:
    """One recording -> candidate clips {wave, start, end, source, emb, snr_db, clip, score, dev, kept}."""
    cands = []
    for a, b in utterances(w, sr):
        seg = w[int(a * sr) : int(b * sr)]
        if not speech_like(seg, sr):  # music, hum, noise that passed the energy detector
            continue
        q = quality(seg, sr)
        cands.append({"wave": seg.astype(np.float32), "start": a, "end": b, "source": source, "emb": embed(seg), **q})
    if cands:
        keep, dev = dominant_speaker(np.stack([c["emb"] for c in cands]), embed)
        for c, k, d_ in zip(cands, keep, dev):
            c["kept"], c["dev"] = bool(k), float(d_)
    return cands


def select(cands: Sequence[Dict], target_s: float = BEST_S) -> Dict:
    """Best kept clips up to `target_s` seconds; a primary reference of about PRIMARY_S seconds."""
    kept = [c for c in cands if c["kept"] and c["score"] > -0.5]
    kept.sort(key=lambda c: -(c["score"] - 0.05 * c["dev"]))
    chosen, tot = [], 0.0
    for c in kept:
        if tot >= target_s:
            break
        chosen.append(c)
        tot += len(c["wave"]) / SR
    gap = np.zeros(int(0.25 * SR), np.float32)
    primary: List[Dict] = []
    p = 0.0
    for c in sorted(chosen, key=lambda c: abs(len(c["wave"]) / SR - PRIMARY_S))[:3]:
        if p < PRIMARY_S:
            primary.append(c)
            p += len(c["wave"]) / SR
    join = lambda cs: np.concatenate([x for c in cs for x in (normalize(c["wave"]), gap)][:-1]) if cs else np.zeros(0, np.float32)
    return {"chosen": chosen, "primary": primary, "primary_wave": join(primary), "long_wave": join(chosen), "seconds": tot,
            "rejected": [c for c in cands if not any(c is x for x in chosen)]}


def verdict(seconds: float) -> Dict:
    v = "insuficiente" if seconds < MIN_S else "mínimo" if seconds < GOOD_S else "bueno" if seconds < BEST_S else "óptimo"
    nxt = GOOD_S if seconds < GOOD_S else BEST_S
    return {"verdict": v, "seconds": round(seconds, 1), "missing_s": round(max(0.0, (MIN_S if seconds < MIN_S else nxt) - seconds), 1),
            "note": "referencia de voz limpia del personaje; los clonadores zero-shot citan 3-5 s como mínimo, más habla limpia fija mejor el timbre"}


# ---- the library ----------------------------------------------------------------------------------------------------------------------------
class VoiceLibrary:
    def __init__(self, ws: str, root: Optional[str] = None):
        self.root = root or os.path.join(ws, "voices")

    def _d(self, name: str, *p) -> str:
        return os.path.join(self.root, _key(name), *p)

    def names(self) -> List[str]:
        return sorted(d for d in (os.listdir(self.root) if os.path.isdir(self.root) else []) if os.path.exists(os.path.join(self.root, d, "profile.json")))

    def profile(self, name: str) -> Dict:
        p = self._d(self.resolve(name) or name, "profile.json")
        if not os.path.exists(p):
            raise KeyError(f"no hay voz «{name}» (hay: {', '.join(self.names()) or 'ninguna'}; añade una con `studio voices add`)")
        return json.load(open(p))

    def resolve(self, character: str) -> Optional[str]:
        """Character name (or alias) -> library key, accent- and case-insensitive; None if the character has no clone."""
        k = _key(character)
        names = self.names()
        if k in names:
            return k
        for n in names:
            if k in [_key(a) for a in json.load(open(self._d(n, "profile.json"))).get("aliases", [])]:
                return n
        return None

    def has(self, character: str) -> bool:
        return self.resolve(character) is not None

    def reference(self, name: str, long: bool = False) -> str:
        k = self.resolve(name)
        if not k:
            return ""
        f = self._d(k, "ref_long.wav" if long else "ref_primary.wav")
        return f if os.path.exists(f) else ""

    # ---- building a voice ------------------------------------------------------------------------------------------------------------------
    def add_audio(self, name: str, waves: Sequence[Tuple[str, np.ndarray]], language: str = "auto", embedder: str = "auto",
                  aliases: Sequence[str] = (), device: str = "cpu") -> Dict:
        """waves: [(source label, mono float32 at 24 kHz)]. Adds to an existing voice (its clips compete with the new ones)."""
        key = _key(name)
        embed = get_embedder(embedder, device)
        cands: List[Dict] = []
        if os.path.exists(self._d(key, "profile.json")):
            old = json.load(open(self._d(key, "profile.json")))
            for c in old["clips"]:
                wv = load_audio(self._d(key, "clips", c["file"]), SR)
                cands.append({"wave": wv, "start": c["start"], "end": c["end"], "source": c["source"], "emb": embed(wv), "snr_db": c["snr_db"],
                              "clip": c["clip"], "score": c["score"], "kept": True, "dev": 0.0})
            language = old.get("language", language) if language == "auto" else language
            aliases = list(dict.fromkeys(list(old.get("aliases", [])) + list(aliases)))
            links = old.get("links", {})
        else:
            links = {}
        for src, w in waves:
            cands += prepare(w, embed, src)
        if not cands:
            raise ValueError("no encontré habla en ese audio (¿solo música o silencio?)")
        keep, dev = dominant_speaker(np.stack([c["emb"] for c in cands]), embed)  # again over everything: old and new clips must be one voice
        for c, k, d_ in zip(cands, keep, dev):
            c["kept"], c["dev"] = bool(k) and c.get("kept", True), float(d_)
        sel = select(cands)
        if not sel["chosen"]:
            raise ValueError("ninguna frase tenía calidad suficiente (demasiado ruido o recortes)")
        d = self._d(key)
        if os.path.isdir(os.path.join(d, "clips")):
            shutil.rmtree(os.path.join(d, "clips"))
        os.makedirs(os.path.join(d, "clips"), exist_ok=True)
        meta = []
        for i, c in enumerate(sel["chosen"]):
            f = f"c{i:03d}.wav"
            _write(os.path.join(d, "clips", f), normalize(c["wave"]))
            meta.append({"file": f, "start": c["start"], "end": c["end"], "source": c["source"], "seconds": len(c["wave"]) / SR,
                         "snr_db": c["snr_db"], "clip": c["clip"], "score": c["score"], "dev": c["dev"]})
        _write(os.path.join(d, "ref_primary.wav"), sel["primary_wave"])
        _write(os.path.join(d, "ref_long.wav"), sel["long_wave"])
        cen = np.mean([c["emb"] for c in sel["chosen"]], 0)
        spread = float(np.mean([embed.dist(c["emb"], cen) for c in sel["chosen"]]))
        prof = {"name": key, "display": name, "aliases": list(aliases), "language": language, "embedder": embed.name, "created": time.time(),
                "sources": sorted({c["source"] for c in cands if c["source"]}), "seconds": sel["seconds"], "primary_seconds": len(sel["primary_wave"]) / SR,
                "clips": meta, "rejected": len(sel["rejected"]), "embedding": [float(x) for x in cen], "spread": spread, "sufficiency": verdict(sel["seconds"]),
                "quality": {"snr_db": float(np.mean([c["snr_db"] for c in sel["chosen"]])), "clip_max": float(max(c["clip"] for c in sel["chosen"]))},
                "links": links}
        json.dump(prof, open(os.path.join(d, "profile.json"), "w"), ensure_ascii=False, indent=1)
        self._index()
        return prof

    def add_inputs(self, name: str, inputs: Sequence[str], opts=None, separate: bool = False, **kw) -> Dict:
        """Any input the studio can read (files, folders, URLs, YouTube, playlists, torrents): only the soundtrack is used."""
        from studio import sources as S

        tmp = self._d(name, "_fetch")
        o = opts or S.Options()
        o.audio_only = True
        pr = S.prepare(list(inputs), tmp, o)
        waves = []
        for p in pr.paths:
            src = p
            if separate:  # clean vocals out of music with Demucs when installed
                from studio.sound.separate import split_dialogue

                src = split_dialogue(p, os.path.join(tmp, "stems"))[0]
            w = load_audio(src, SR)
            if len(w):
                waves.append((os.path.basename(p), w))
        shutil.rmtree(tmp, ignore_errors=True)
        if not waves:
            raise ValueError("ninguna de las fuentes tiene pista de audio")
        prof = self.add_audio(name, waves, **kw)
        prof["fetch_errors"] = pr.errors
        return prof

    def from_corpus(self, ws: str, min_seconds: float = 3.0) -> List[str]:
        """Promote the voices the learning found in the episodes to library profiles, for every character that has a name."""
        from studio.characters import Registry
        from studio.sound.bank import Bank

        rp = os.path.join(ws, "registry.json")
        if not os.path.exists(rp):
            return []
        reg, bank, made = Registry.load(rp), Bank(ws), []
        for c in reg.characters():
            vid = c.get("voice_id")
            if not vid or c["name"].startswith("PERSONAJE") or not c["name"]:
                continue
            waves = [(f"corpus:{vid}", load_audio(e["wav"], SR)) for e in bank.m["voices"].get(str(vid), []) if os.path.exists(e["wav"])]
            if sum(len(w) for _, w in waves) / SR < min_seconds:
                continue
            prof = self.add_audio(c["name"], waves)
            prof["links"]["corpus_voice_id"] = vid
            self._save_links(c["name"], {"corpus_voice_id": vid, "visual_id": c["id"]})
            made.append(prof["name"])
        return made

    def link(self, name: str, aliases: Sequence[str] = (), **links) -> None:
        k = self.resolve(name) or _key(name)
        p = self._d(k, "profile.json")
        prof = json.load(open(p))
        prof["aliases"] = list(dict.fromkeys(list(prof.get("aliases", [])) + list(aliases)))
        prof["links"] = {**prof.get("links", {}), **links}
        json.dump(prof, open(p, "w"), ensure_ascii=False, indent=1)
        self._index()

    def _save_links(self, name: str, links: Dict) -> None:
        self.link(name, (), **links)

    def remove(self, name: str) -> None:
        shutil.rmtree(self._d(self.resolve(name) or name), ignore_errors=True)
        self._index()

    def _index(self) -> None:
        idx = {n: {"aliases": p.get("aliases", []), "seconds": p["seconds"], "verdict": p["sufficiency"]["verdict"], "language": p["language"],
                   "links": p.get("links", {})} for n in self.names() for p in [json.load(open(self._d(n, "profile.json")))]}
        os.makedirs(self.root, exist_ok=True)
        json.dump(idx, open(os.path.join(self.root, "index.json"), "w"), ensure_ascii=False, indent=1)

    # ---- is a generated line really that character? ---------------------------------------------------------------------------------------------
    def verify(self, name: str, wave: np.ndarray, sr: int = SR, margin_min: float = 0.0) -> Dict:
        """How far a generated line is from the character's voice, and from every other voice in the library. `ok` = it is within the
        spread of the character's own clips (x3) and no other voice is closer."""
        prof = self.profile(name)
        embed = get_embedder(prof.get("embedder", "voiceprint"))
        e = embed(_resample(wave, sr, SR))
        d_own = embed.dist(e, np.asarray(prof["embedding"]))
        others = {n: embed.dist(e, np.asarray(self.profile(n)["embedding"])) for n in self.names() if n != prof["name"]}
        closest = min(others, key=others.get) if others else None
        near = d_own <= 3.0 * max(prof.get("spread", 0.0), embed.floor) + embed.floor
        ok = near and (closest is None or others[closest] - d_own > margin_min)
        return {"distance": d_own, "similarity": 1.0 / (1.0 + d_own), "closest_other": closest, "closest_other_distance": others.get(closest) if closest else None,
                "margin": (others[closest] - d_own) if closest else None,
                "verdict": "ok" if ok else f"más parecida a {closest}" if closest and others[closest] < d_own
                else "es la voz más cercana, pero lejos de la referencia (revisa la referencia o el clonador)"}


def _write(path: str, w: np.ndarray, sr: int = SR) -> None:
    from studio.sound.mix import write_wav

    os.makedirs(os.path.dirname(path), exist_ok=True)
    write_wav(path, w, sr)


# ---- binding characters to voices at creation time -----------------------------------------------------------------------------------------------
def binding(ws: str, characters: Iterable[str], corpus_ids: Optional[Dict[str, object]] = None) -> Dict[str, Dict]:
    """{CHARACTER: {'voice_id', 'source': clone|corpus|guide, 'profile', 'seconds', 'verdict'}}. A clone profile wins over the voice found in the
    episodes, which wins over the generic guide voice."""
    lib = VoiceLibrary(ws)
    out: Dict[str, Dict] = {}
    for c in characters:
        k = lib.resolve(c)
        if k:
            p = lib.profile(k)
            out[c.upper()] = {"voice_id": PREFIX + k, "source": "clone", "profile": k, "seconds": round(p["seconds"], 1), "verdict": p["sufficiency"]["verdict"]}
        elif corpus_ids and corpus_ids.get(c.upper()) is not None:
            out[c.upper()] = {"voice_id": corpus_ids[c.upper()], "source": "corpus"}
        else:
            out[c.upper()] = {"voice_id": None, "source": "guide"}
    return out
