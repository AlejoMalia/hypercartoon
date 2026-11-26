"""Learn a show's mouth-animation convention from (mouth openness, audio envelope) pairs, then apply it to new tracks.
What is learned: how often the mouth may change (animating 'on 2s/3s'), the discrete set of mouth openings, how far the
mouth leads the sound, and how strongly openness follows loudness."""
import json
from dataclasses import asdict, dataclass, field
from typing import List

import numpy as np


@dataclass
class MouthStyle:
    fps: int = 24
    hold_frames: int = 2            # minimum frames a mouth shape is held ("on twos")
    levels: List[float] = field(default_factory=lambda: [0.0, 0.3, 0.55, 0.8, 1.0])
    lead_s: float = 0.04            # mouth moves this much before the sound (>0 = leads)
    gain: float = 1.0
    n_samples: int = 0

    def save(self, path: str):
        json.dump(asdict(self), open(path, "w"), indent=1)

    @classmethod
    def load(cls, path: str):
        return cls(**json.load(open(path)))


def _kmeans_1d(x: np.ndarray, k: int, iters: int = 25):
    c = np.quantile(x, np.linspace(0.05, 0.95, k))
    for _ in range(iters):
        a = np.abs(x[:, None] - c[None]).argmin(1)
        c = np.array([x[a == j].mean() if (a == j).any() else c[j] for j in range(k)])
    return np.sort(c), float(((x - c[np.abs(x[:, None] - c[None]).argmin(1)]) ** 2).sum())


def lag_of(a: np.ndarray, b: np.ndarray, fps: int, max_lag_s: float = 0.3):
    """Lag (s) of `a` relative to `b` maximising normalised cross-correlation; positive = a *leads* b. -> (lag, corr).
    Syllable rhythm is quasi-periodic, so several lags correlate almost equally: among those within 0.03 of the best,
    the smallest |lag| wins."""
    a, b = (a - a.mean()) / (a.std() + 1e-9), (b - b.mean()) / (b.std() + 1e-9)
    cs = []
    for L in range(-int(max_lag_s * fps), int(max_lag_s * fps) + 1):
        x, y = (a[: len(a) - L], b[L:]) if L >= 0 else (a[-L:], b[: len(b) + L])
        if len(x) >= 4:
            cs.append((L, float((x * y).mean())))
    if not cs:
        return 0.0, -1.0
    top = max(c for _, c in cs)
    L, c = min(((L, c) for L, c in cs if c >= top - 0.03), key=lambda p: abs(p[0]))
    return L / fps, c


def _hold_frames(o: np.ndarray, max_hold: int = 6) -> int:
    """Largest h such that (almost) all mouth changes fall on one h-frame grid: the show animates 'on h's'."""
    ch = np.flatnonzero(np.abs(np.diff(o)) > 0.05) + 1
    if len(ch) < 6:
        return 1
    best = 1
    for h in range(2, max_hold + 1):
        frac = max(float(((ch - ph) % h == 0).mean()) for ph in range(h))
        if frac >= 0.9:
            best = h
    return best


def learn_style(openness: np.ndarray, env: np.ndarray, fps: int, max_levels: int = 6) -> MouthStyle:
    o = np.clip((openness - openness.min()) / (np.ptp(openness) + 1e-9), 0, 1)
    e = (env - env.min()) / (np.ptp(env) + 1e-9)
    # discrete levels: smallest k whose quantisation error stops improving by > 25 %
    prev, levels = None, None
    for k in range(2, max_levels + 1):
        c, err = _kmeans_1d(o, k)
        if prev is not None and (prev < 1e-6 or err > 0.85 * prev):
            break
        prev, levels = err, c
    lead, _ = lag_of(o, e, fps, 0.15)
    gain = float(np.polyfit(e, o, 1)[0]) if e.std() > 1e-6 else 1.0
    return MouthStyle(fps=fps, hold_frames=_hold_frames(o), levels=[float(x) for x in levels],
                      lead_s=float(lead), gain=float(np.clip(gain, 0.3, 2.0)), n_samples=len(o))


def apply_style(track: np.ndarray, style: MouthStyle, fps: int) -> np.ndarray:
    """Quantise to the show's mouth levels, hold each shape at least `hold_frames`, and shift by the learned lead."""
    lv = np.array(style.levels)
    q = lv[np.abs(np.clip(track * style.gain, 0, 1)[:, None] - lv[None]).argmin(1)]
    hold = max(1, int(round(style.hold_frames * fps / style.fps)))
    out = q.copy()
    for i in range(0, len(q), hold):
        out[i : i + hold] = q[i : i + hold].max() if hold > 1 else q[i]
    shift = int(round(style.lead_s * fps))
    return np.roll(out, -shift) if shift > 0 else out
