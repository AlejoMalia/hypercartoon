"""Text -> mouth-shape (viseme) sequence using the classic cartoon set (Preston Blair style, 10 shapes).
Spanish orthography is nearly phonetic so rules are direct; English falls back to the same letter rules (approximate)."""
import re
from typing import List, Optional, Tuple

import numpy as np

SHAPES = ["REST", "AI", "E", "O", "U", "FV", "L", "MBP", "WQ", "ETC"]
OPEN = {"REST": 0.0, "MBP": 0.0, "FV": 0.2, "ETC": 0.3, "WQ": 0.35, "L": 0.4, "U": 0.45, "E": 0.55, "O": 0.75, "AI": 1.0}
_VOW = {"a": "AI", "á": "AI", "e": "E", "é": "E", "i": "E", "í": "E", "o": "O", "ó": "O", "u": "U", "ú": "U", "ü": "U"}
_CONS = {"m": "MBP", "b": "MBP", "p": "MBP", "f": "FV", "v": "FV", "l": "L", "t": "L", "d": "L", "n": "L",
         "w": "WQ", "q": "WQ"}


def text_to_visemes(text: str) -> List[Tuple[str, float]]:
    """[(shape, weight)] where weight is the relative duration share (vowels carry the beat)."""
    t = re.sub(r"qu(?=[ei])", "k", text.lower())
    t = t.replace("ch", "x").replace("ll", "y")
    out: List[Tuple[str, float]] = []
    for ch in t:
        if ch in _VOW:
            out.append((_VOW[ch], 2.0))
        elif ch in _CONS:
            out.append((_CONS[ch], 0.7))
        elif ch.isalpha():
            out.append(("ETC", 0.6))
        elif ch in ",;:":
            out.append(("REST", 1.2))
        elif ch in ".!?":
            out.append(("REST", 2.0))
        elif ch == " " and out and out[-1][0] != "REST":
            out.append(("REST", 0.15))
    # collapse repeats (same shape twice in a row is one held shape)
    merged: List[Tuple[str, float]] = []
    for s, w in out:
        if merged and merged[-1][0] == s:
            merged[-1] = (s, merged[-1][1] + w)
        else:
            merged.append((s, w))
    return merged


def viseme_track(text: str, start: float, end: float, fps: int = 24, env: Optional[np.ndarray] = None,
                 env_mix: float = 0.5) -> np.ndarray:
    """Per-frame openness in [0,1] for t in [start, end). If the audio envelope of the line is given, shape durations are
    time-warped toward where the voice is actually loud (vowel peaks land on energy peaks)."""
    n = max(1, int(round((end - start) * fps)))
    seq = text_to_visemes(text)
    if not seq:
        return np.zeros(n)
    w = np.array([x[1] for x in seq], float)
    cum = np.cumsum(w) / w.sum()  # fraction of the line at the end of each shape
    t = (np.arange(n) + 0.5) / n
    if env is not None and len(env) > 1:
        c = np.cumsum(np.asarray(env, float) + 1e-6)
        c = c / c[-1]
        grid = np.linspace(0, 1, len(c))
        warped = np.interp(t, grid, c)  # shape mass advances fastest where the voice is loud
        t = (1 - env_mix) * t + env_mix * warped
    idx = np.searchsorted(cum, t, side="left").clip(0, len(seq) - 1)
    return np.array([OPEN[seq[i][0]] for i in idx])


def viseme_track_words(words, duration: float, fps: int = 24, env: Optional[np.ndarray] = None) -> np.ndarray:
    """Word-timed variant: words = [(start_s, end_s, text)] (e.g. from word timestamps). Each word's visemes are spread over
    that word's real interval; gaps between words are REST. More accurate than spreading a whole line uniformly."""
    n = max(1, int(round(duration * fps)))
    out = np.zeros(n)
    for a, b, txt in words:
        i0, i1 = max(0, int(round(a * fps))), min(n, int(round(b * fps)))
        if i1 <= i0:
            continue
        e = None if env is None else env[i0:i1]
        out[i0:i1] = viseme_track(txt, a, b, fps, e)[: i1 - i0]
    return out
