"""Measure and enforce audio <-> mouth sync. Pure numpy.

mouth_series_from_video: classical cue (frame-difference energy + dark-interior change in the lower part of a face box).
For realistic faces a landmark model (e.g. MediaPipe face landmarks) gives a better openness; plug it in by returning
the same 0..1 series."""
from typing import List, Optional, Sequence, Tuple

import numpy as np

from studio.lips.style import lag_of


def audio_envelope(wave: np.ndarray, sr: int, fps: int) -> np.ndarray:
    """Loudness envelope sampled at the video frame rate, normalised to 0..1."""
    hop = max(1, int(sr / fps))
    n = len(wave) // hop
    e = np.sqrt((wave[: n * hop].reshape(n, hop).astype(np.float64) ** 2).mean(1)) if n else np.zeros(1)
    return e / (e.max() + 1e-9)


def mouth_series_from_video(frames: Sequence[np.ndarray], bbox: Optional[Tuple[float, float, float, float]] = None) -> np.ndarray:
    """frames: small grayscale/RGB arrays. bbox: (x0,y0,x1,y1) fractions of the face box; mouth = its lower 35 %.
    Without a bbox the lower-centre of the frame is used (works for close-ups with a single speaker only)."""
    x0, y0, x1, y1 = bbox or (0.25, 0.3, 0.75, 1.0)
    prev, dark_prev, out = None, None, []
    for f in frames:
        g = f.mean(2) if f.ndim == 3 else f
        h, w = g.shape
        a, b = int((y0 + 0.65 * (y1 - y0)) * h), int(y1 * h)
        c, d = int(x0 * w), int(x1 * w)
        r = g[a:max(b, a + 1), c:max(d, c + 1)].astype(np.float64)
        dark = float((r < r.mean() * 0.6).mean())
        mot = 0.0 if prev is None or prev.shape != r.shape else float(np.abs(r - prev).mean())
        dd = 0.0 if dark_prev is None else abs(dark - dark_prev)
        out.append(mot / 255.0 + 4.0 * dd + 0.5 * dark)
        prev, dark_prev = r, dark
    s = np.array(out)
    return (s - s.min()) / (np.ptp(s) + 1e-9)


def sync_score(mouth: np.ndarray, env: np.ndarray, fps: int, max_lag_s: float = 0.3) -> dict:
    """Best normalised correlation between mouth activity and voice loudness over +-max_lag. 1 = locked, ~0 = unrelated."""
    n = min(len(mouth), len(env))
    lag, corr = lag_of(mouth[:n], env[:n], fps, max_lag_s)
    return {"score": float(max(0.0, corr)), "lag_s": float(lag), "verdict": "ok" if corr >= 0.5 else "weak"}


def align_lines(mouth: np.ndarray, clips: List[Tuple[float, np.ndarray]], sr: int, fps: int,
                window_s: float = 0.6) -> List[float]:
    """For each (start_s, wave) line find the shift in [-window, +window] whose envelope correlates best with the mouth
    series over the line's span. Returns shifts in seconds (0.0 if the mouth is flat there). Lines never cross each other."""
    shifts: List[float] = []
    prev_end = 0.0
    for start, wav in clips:
        env = audio_envelope(wav, sr, fps)
        dur = len(wav) / sr
        best, best_c = 0.0, -1.0
        for s in np.arange(-window_s, window_s + 1e-9, 1.0 / fps):
            t0 = start + s
            if t0 < prev_end - 1e-9 or t0 < 0:
                continue
            a = int(round(t0 * fps))
            seg = mouth[a : a + len(env)]
            if len(seg) < len(env) or seg.std() < 1e-3:
                continue
            c = float(np.corrcoef(seg, env)[0, 1]) - 0.05 * abs(s)  # prefer small moves
            if c > best_c:
                best, best_c = float(s), c
        shifts.append(best if best_c > 0.2 else 0.0)
        prev_end = start + shifts[-1] + dur
    return shifts
