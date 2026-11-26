"""Emotion measured from the *voice* (independent of the words): pitch level/range, loudness, speaking rate.
Arousal from prosody is reasonably robust; valence is not -- so only arousal is reported, always relative to the
character's own baseline (a naturally shrill character is not 'excited' all the time)."""
from typing import Dict, List

import numpy as np

from studio.sound.analyze import pitch_f0

SR = 16000


def features(clip: np.ndarray, sr: int = SR) -> Dict[str, float]:
    n = int(0.04 * sr)
    f0s = []
    for a in range(0, max(1, len(clip) - n), n // 2):
        f = pitch_f0(clip[a : a + n * 2], sr)
        if f > 0:
            f0s.append(f)
    st = 12 * np.log2(np.array(f0s) / 100.0) if f0s else np.array([0.0])
    hop = int(0.02 * sr)
    e = np.sqrt((clip[: len(clip) // hop * hop].reshape(-1, hop) ** 2).mean(1) + 1e-12) if len(clip) >= hop else np.zeros(1)
    e = np.convolve(e, np.ones(4) / 4, "same")
    peaks = int(((e[1:-1] > e[:-2]) & (e[1:-1] >= e[2:]) & (e[1:-1] > 0.4 * e.max())).sum()) if len(e) > 3 else 0
    return {"f0_semitones": float(st.mean()), "f0_range": float(np.percentile(st, 90) - np.percentile(st, 10)),
            "energy_db": float(20 * np.log10(np.percentile(e, 90) + 1e-9)), "rate": peaks / max(len(clip) / sr, 1e-6)}


KEYS = ("f0_semitones", "f0_range", "energy_db", "rate")


class Baseline:
    """Welford running mean/std per feature for one voice; z-scores of new clips against it."""

    def __init__(self):
        self.n, self.mean, self.m2 = 0, np.zeros(len(KEYS)), np.zeros(len(KEYS))

    def add(self, feat: Dict[str, float]) -> None:
        x = np.array([feat[k] for k in KEYS])
        self.n += 1
        d = x - self.mean
        self.mean += d / self.n
        self.m2 += d * (x - self.mean)

    def std(self) -> np.ndarray:
        return np.sqrt(self.m2 / max(self.n - 1, 1)) + 1e-6

    def arousal(self, feat: Dict[str, float]) -> float:
        """0..1: 0.5 = this character's usual delivery; >0.5 higher/wider/louder/faster than usual."""
        if self.n < 5:
            return 0.5
        z = (np.array([feat[k] for k in KEYS]) - self.mean) / self.std()
        return float(1 / (1 + np.exp(-np.clip(0.8 * z.mean(), -30, 30))))

    def to_json(self):
        return {"n": self.n, "mean": self.mean.tolist(), "m2": self.m2.tolist()}

    @classmethod
    def from_json(cls, d):
        b = cls()
        b.n, b.mean, b.m2 = d["n"], np.array(d["mean"]), np.array(d["m2"])
        return b


def delivery_params(valence: float, arousal: float) -> Dict[str, float]:
    """Emotion -> how a speaker should deliver the line (used by every speaker backend)."""
    return {"rate": float(np.clip(1.0 + 0.25 * (arousal - 0.4) + 0.05 * valence, 0.8, 1.3)),
            "pitch_semitones": float(np.clip(5.0 * (arousal - 0.4) + 1.5 * valence, -3.0, 5.0)),
            "energy": float(np.clip(0.8 + 0.6 * arousal, 0.6, 1.4)),
            "exaggeration": float(np.clip(0.35 + 0.65 * arousal, 0.25, 1.0))}
