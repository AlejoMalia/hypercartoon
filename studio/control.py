"""Control files for the video model (see hypercartoon/models/cogvideo/control_data.py).

Audio-side control is the part the studio can always build on CPU: per latent frame, is someone speaking, how loud, and (optionally)
the emotion of the line. The SAME function serves real footage (training rows) and regenerated voices (generation), so train and
generation features come from one definition. Character layout (label maps) needs the vision stage (GPU) and is added when
available. Valence/arousal are written as zeros unless `emotion=True`: the real footage has no per-line emotion, so training them
would be meaningless; only turn it on if you trained with them."""
import os
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from hypercartoon.models.cogvideo import control_data as CD

SEG = 3.0


def clip_control(wave: np.ndarray, sr: int, start: float, dur: float, speech_ranges: Sequence[Tuple[float, float]]) -> np.ndarray:
    """frame_feats [T_latent, 4] for the window [start, start+dur) of an episode waveform."""
    t_lat = CD.latent_frames(dur)
    seg = wave[int(start * sr) : int((start + dur) * sr)] if len(wave) else np.zeros(int(dur * sr), np.float32)
    rel = [(max(0.0, a - start), min(dur, b - start)) for a, b in speech_ranges if b > start and a < start + dur]
    return CD.frame_feats_from_audio(seg, sr, t_lat, speech=rel)


def video_control(clips: Sequence[Tuple[float, np.ndarray]], sr: int, n_segments: int, line_emotions: Optional[Sequence[dict]] = None,
                  emotion: bool = False, loudness_ref: Optional[float] = None) -> np.ndarray:
    """Control for one GENERATED video from its regenerated dialogue clips [(start_s, wave)] (+ emotion per clip)."""
    dur = n_segments * SEG
    n = int(dur * sr) + sr
    wave = np.zeros(n, np.float32)
    speech = []
    for start, w in clips:
        a = int(start * sr)
        if a + len(w) > len(wave):
            wave = np.pad(wave, (0, a + len(w) - len(wave)))
        wave[a : a + len(w)] += w
        speech.append((start, start + len(w) / sr))
    t_lat = CD.latent_frames(dur)
    val = np.zeros(t_lat)
    aro = np.zeros(t_lat)
    if emotion and line_emotions:
        for (a, b), e in zip(speech, line_emotions):
            i0, i1 = int(a * CD.LATENT_FPS), min(t_lat, int(b * CD.LATENT_FPS) + 1)
            val[i0:i1], aro[i0:i1] = e.get("valence", 0.0), e.get("arousal", 0.0)
    return CD.frame_feats_from_audio(wave[: int(dur * sr)], sr, t_lat, speech=speech, valence=val, arousal=aro, loudness_ref=loudness_ref)
