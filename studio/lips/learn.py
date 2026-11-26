"""Learn the show's mouth convention from episodes: pick time ranges where speech is present (from the audio candidates
saved by `learn --characters`), measure mouth activity in the video and the voice envelope, fit MouthStyle."""
import json
import os
from typing import Optional, Tuple

import numpy as np

from studio.audio import SR, load_audio
from studio.lips.style import MouthStyle, learn_style
from studio.lips.sync import audio_envelope, mouth_series_from_video


def learn_from_episode(path: str, ranges, fps_out: int = 12, bbox: Optional[Tuple[float, ...]] = None):
    """-> (openness, envelope) concatenated over speech ranges, both sampled at the video frame rate."""
    import imageio

    r = imageio.get_reader(path, "ffmpeg")
    vfps = float(r.get_meta_data()["fps"])
    wave = load_audio(path, SR)
    frames = {}
    want = sorted({int(t * vfps) for a, b in ranges for t in np.arange(a, b, 1 / vfps)})
    wset = set(want)
    for i, f in enumerate(r):
        if i in wset:
            frames[i] = f[::8, ::8]
        if i > (want[-1] if want else 0):
            break
    r.close()
    mo, en = [], []
    for a, b in ranges:
        idx = [i for i in range(int(a * vfps), int(b * vfps)) if i in frames]
        if len(idx) < 8:
            continue
        mo.append(mouth_series_from_video([frames[i] for i in idx], bbox))
        en.append(audio_envelope(wave[int(a * SR) : int(b * SR)], SR, int(round(vfps)))[: len(idx)])
    n = [min(len(x), len(y)) for x, y in zip(mo, en)]
    return np.concatenate([x[:k] for x, k in zip(mo, n)]), np.concatenate([y[:k] for y, k in zip(en, n)]), int(round(vfps))


def learn_corpus_style(ws: str, max_episodes: int = 20, bbox=None) -> MouthStyle:
    cands = json.load(open(os.path.join(ws, "audio_candidates.json")))["voice"]
    mo, en, fps = [], [], 24
    for ep, lst in list(cands.items())[:max_episodes]:
        rng = [(c["start"], c["end"]) for c in lst[:12]]
        if not rng:
            continue
        o, e, fps = learn_from_episode(ep, rng, bbox=bbox)
        mo.append(o)
        en.append(e)
    if not mo:
        raise ValueError("no speech ranges found in the audio candidates")
    st = learn_style(np.concatenate(mo), np.concatenate(en), fps)
    st.save(os.path.join(ws, "mouth_style.json"))
    return st
