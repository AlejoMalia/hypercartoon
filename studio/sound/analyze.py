"""Soundtrack analysis, numpy only. Heuristic (scale-invariant spectral/modulation features) so it runs anywhere;
stronger taggers plug in via `tagger.py`. Thresholds were calibrated on synthetic signals only -- recalibrate on a
few real episodes (see docs/sound.md) before trusting the labels."""
from typing import List, Tuple

import numpy as np

SR = 16000
N_FFT, HOP = 512, 160  # 32 ms frames every 10 ms
LABELS = ("silence", "speech", "music", "ambient")


def _spec(wave: np.ndarray) -> np.ndarray:
    if len(wave) < N_FFT:
        wave = np.pad(wave, (0, N_FFT - len(wave)))
    idx = np.arange(0, len(wave) - N_FFT + 1, HOP)[:, None] + np.arange(N_FFT)[None]
    return np.abs(np.fft.rfft(wave[idx].astype(np.float64) * np.hanning(N_FFT), axis=1)) ** 2


def classify(wave: np.ndarray, sr: int = SR, win: float = 1.0, hop: float = 0.5) -> List[Tuple[float, float, str]]:
    """-> [(start, end, label)] over overlapping windows; adjacent equal labels merged."""
    S = _spec(wave)
    lo, hi = int(100 / (sr / N_FFT)), int(4000 / (sr / N_FFT))
    B = S[:, lo:hi] + 1e-12
    frame_db = 10 * np.log10(S.sum(1) / N_FFT + 1e-12)
    w, h = int(win * 100), int(hop * 100)
    ref = np.percentile(frame_db, 95)
    out: List[Tuple[float, float, str]] = []
    for a in range(0, max(1, len(B) - w + 1), h):
        seg, dbs = B[a : a + w], frame_db[a : a + w]
        if dbs.mean() < -62 or dbs.mean() < ref - 40:
            lab = "silence"
        else:
            flat = float(np.mean(np.exp(np.log(seg).mean(1)) / seg.mean(1)))
            env = np.sqrt(seg.sum(1))
            env = env - env.mean()
            p = np.abs(np.fft.rfft(env * np.hanning(len(env)))) ** 2
            f = np.fft.rfftfreq(len(env), 0.01)
            tot = p[1:].sum()
            mod = float(p[(f >= 2) & (f <= 8)].sum() / tot) if tot > 1e-12 else 0.0
            lab = "ambient" if flat >= 0.45 else "speech" if mod >= 0.30 else "music"
        t0, t1 = a / 100.0, a / 100.0 + win
        if out and out[-1][2] == lab and t0 <= out[-1][1] + 1e-9:
            out[-1] = (out[-1][0], t1, lab)
        else:
            out.append((t0, t1, lab))
    return out


def ratios(timeline: List[Tuple[float, float, str]]) -> dict:
    tot = sum(b - a for a, b, _ in timeline) or 1.0
    return {l: round(sum(b - a for a, b, k in timeline if k == l) / tot, 3) for l in LABELS}


def label_ratio(timeline, start: float, end: float, label: str) -> float:
    span = max(end - start, 1e-9)
    return sum(max(0.0, min(end, b) - max(start, a)) for a, b, k in timeline if k == label) / span


def pitch_f0(seg: np.ndarray, sr: int = SR, fmin: float = 60.0, fmax: float = 400.0) -> float:
    """Median f0 over voiced 40 ms frames (normalised autocorrelation); 0.0 if nothing voiced."""
    n = int(0.04 * sr)
    lo, hi = int(sr / fmax), int(sr / fmin)
    f0s = []
    for a in range(0, len(seg) - n, n // 2):
        x = seg[a : a + n].astype(np.float64)
        x = x - x.mean()
        if (x ** 2).mean() < 1e-7:
            continue
        ac = np.fft.irfft(np.abs(np.fft.rfft(x, 2 * n)) ** 2)[: n]
        ac = ac / (ac[0] + 1e-12)
        k = lo + int(np.argmax(ac[lo : min(hi, n - 1)]))
        if ac[k] > 0.45:
            f0s.append(sr / k)
    return float(np.median(f0s)) if f0s else 0.0


def snr_db(seg: np.ndarray, sr: int = SR) -> float:
    """Crude clip quality: loud-frame level vs the quietest 10 % (noise floor) of the same clip."""
    n = int(0.03 * sr)
    if len(seg) < 4 * n:
        return 0.0
    e = 10 * np.log10((seg[: len(seg) // n * n].reshape(-1, n) ** 2).mean(1) + 1e-12)
    return float(np.percentile(e, 90) - np.percentile(e, 10))
