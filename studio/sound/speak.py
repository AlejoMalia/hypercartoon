"""Voice regeneration. A `Speaker` turns (text, reference clip of the character) into a waveform.

  ScratchVoice      : built-in, dependency-free guide voice (formant synth at the character's measured pitch). It is NOT
                      the final voice; it gives true line durations/timing and an audible animatic.
  ChatterboxSpeaker : zero-shot cloning from the reference clip (pip install chatterbox-tts). License to be checked.
Add another model by implementing `say()`; nothing else in the studio changes."""
import re
from typing import Optional

import numpy as np

from studio.emotion.prosody import delivery_params
from studio.sound.analyze import pitch_f0


def read_wav(path: str, sr: int) -> np.ndarray:
    from studio.audio import load_audio

    return load_audio(path, sr)


_FORMANTS = {"a": (800, 1200, 2800), "e": (500, 1900, 2600), "i": (300, 2300, 3000), "o": (500, 900, 2600), "u": (320, 800, 2500)}
_V = re.compile(r"[aeiouáéíóúü]+", re.I)


class ScratchVoice:
    sr = 22050

    def __init__(self, syllable: float = 0.19):
        self.syllable = syllable

    def say(self, text: str, ref_wav: str = "", voice_id=None, emotion=None) -> np.ndarray:
        f0 = 140.0
        if ref_wav:
            m = pitch_f0(read_wav(ref_wav, 16000))
            f0 = m if m > 0 else f0
        dp = delivery_params(emotion["valence"], emotion["arousal"]) if emotion else delivery_params(0.0, 0.4)
        f0 *= 2 ** (dp["pitch_semitones"] / 12)
        out, sr = [], self.sr
        self.syllable_now = self.syllable / dp["rate"]
        for tok in re.findall(r"[\wáéíóúüñ']+|[,.;:!?¿¡]", text.lower()):
            if not tok[0].isalnum() and tok[0] != "'":
                out.append(np.zeros(int(sr * (0.4 if tok in ".!?" else 0.2))))
                continue
            groups = _V.findall(tok) or ["a"]
            for g in groups:
                v = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u"}.get(g[0], g[0])
                out.append(self._syl(f0 * (1 + 0.08 * np.sin(len(out))), _FORMANTS.get(v, _FORMANTS["a"])))
            out.append(np.zeros(int(sr * 0.05)))
        w = np.concatenate(out) if out else np.zeros(int(sr * 0.2))
        return (w / (np.abs(w).max() + 1e-9) * 0.5 * min(dp['energy'], 1.4) / 1.1).astype(np.float32)

    def _syl(self, f0: float, formants) -> np.ndarray:
        syl = getattr(self, 'syllable_now', self.syllable)
        n = int(self.sr * syl)
        t = np.arange(n) / self.sr
        ph = 2 * np.pi * np.cumsum(f0 * (1 - 0.06 * t / syl)) / self.sr
        s = np.zeros(n)
        for k in range(1, int(4000 / f0) + 1):
            g = sum(np.exp(-0.5 * ((k * f0 - f) / (0.12 * f + 60)) ** 2) for f in formants)
            s += g * np.sin(k * ph) / k ** 0.5
        return s * np.hanning(n)


class ChatterboxSpeaker:
    """Zero-shot voice cloning. Follows the public API of the `chatterbox-tts` package; validate on a GPU machine."""

    def __init__(self, device: str = "cuda"):
        from chatterbox.tts import ChatterboxTTS  # external package name

        self.m = ChatterboxTTS.from_pretrained(device=device)
        self.sr = self.m.sr

    def say(self, text: str, ref_wav: str = "", voice_id=None, emotion=None) -> np.ndarray:
        kw = {"exaggeration": delivery_params(emotion["valence"], emotion["arousal"])["exaggeration"]} if emotion else {}
        w = self.m.generate(text, audio_prompt_path=ref_wav or None, **kw)
        return w.squeeze().cpu().numpy().astype(np.float32)


def _profile_of(ref_wav: str) -> dict:
    """The voice-library profile that sits next to a reference clip (language, aliases...), if any."""
    import json
    import os

    p = os.path.join(os.path.dirname(ref_wav or ""), "profile.json")
    return json.load(open(p)) if ref_wav and os.path.exists(p) else {}


class CoquiSpeaker:
    """Coqui XTTS-v2 zero-shot cloning (pip install coqui-tts). Multilingual (es, en, ...). Its licence (CPML) is NON-COMMERCIAL:
    read it before using the audio in a product. Follows the public API; not run here."""

    sr = 24000

    def __init__(self, device: str = "cuda", language: str = "en"):
        from TTS.api import TTS

        self.tts, self.language = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device), language

    def say(self, text: str, ref_wav: str = "", voice_id=None, emotion=None) -> np.ndarray:
        import os

        long = os.path.join(os.path.dirname(ref_wav), "ref_long.wav") if ref_wav else ""
        lang = _profile_of(ref_wav).get("language", self.language)
        lang = self.language if lang in ("auto", "", None) else lang
        w = self.tts.tts(text=text, speaker_wav=long if long and os.path.exists(long) else ref_wav, language=lang)
        return np.asarray(w, np.float32)


class F5Speaker:
    """F5-TTS zero-shot cloning (pip install f5-tts). Code is MIT but the released weights are CC-BY-NC: not for commercial output.
    With no reference transcript F5 transcribes the clip itself. Follows the public API; not run here."""

    sr = 24000

    def __init__(self, device: str = "cuda"):
        from f5_tts.api import F5TTS

        self.m = F5TTS(device=device)

    def say(self, text: str, ref_wav: str = "", voice_id=None, emotion=None) -> np.ndarray:
        w, sr, _ = self.m.infer(ref_file=ref_wav, ref_text="", gen_text=text)
        self.sr = sr
        return np.asarray(w, np.float32)


CLONERS = ("chatterbox", "coqui", "f5")
_MODULES = {"chatterbox": "chatterbox", "coqui": "TTS", "f5": "f5_tts"}


def available_cloners() -> list:
    import importlib.util

    return [n for n in CLONERS if importlib.util.find_spec(_MODULES[n]) is not None]


def get_speaker(name: str = "scratch", device: str = "cuda", language: str = "en"):
    if name == "auto":  # the best cloner that is installed, else the guide voice
        have = available_cloners()
        name = have[0] if have else "scratch"
    if name == "scratch":
        return ScratchVoice()
    if name == "chatterbox":
        return ChatterboxSpeaker(device)
    if name == "coqui":
        return CoquiSpeaker(device, language)
    if name == "f5":
        return F5Speaker(device)
    raise ValueError(f"unknown speaker '{name}' (auto | scratch | chatterbox | coqui | f5)")
