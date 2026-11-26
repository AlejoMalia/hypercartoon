"""Place regenerated dialogue on the video timeline and mix it with a ducked ambience bed."""
import os
import subprocess
import wave
from typing import List, Optional

import numpy as np

from studio.audio import _ffmpeg
from studio.sound.bank import Bank
from studio.sound.speak import read_wav

SEG = 3.0


def _resample(w: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if sr_in == sr_out or len(w) == 0:
        return w
    n = int(len(w) * sr_out / sr_in)
    return np.interp(np.linspace(0, len(w) - 1, n), np.arange(len(w)), w).astype(np.float32)


def render_dialogue(segments: List[list], bank: Bank, speaker, sr: int = 24000, lead: float = 0.2, gap: float = 0.25):
    """segments[i] = [{character, voice_id, line}] spoken in 3-second segment i of one video.
    Returns (wave, report). A line that does not fit its segment pushes later lines; `overflow_s` reports spill."""
    total = len(segments) * SEG
    track = np.zeros(int(total * sr) + sr * 10, np.float32)
    report = {"lines": 0, "overflow_s": 0.0, "late_lines": []}
    clips: List[tuple] = []
    meta: List[tuple] = []
    cursor = 0.0
    for i, lines in enumerate(segments):
        cursor = max(cursor, i * SEG + lead)
        for ln in lines:
            w = _resample(speaker.say(ln["line"], bank.reference(ln.get("voice_id")), ln.get("voice_id"), ln.get("emotion")),
                          speaker.sr, sr)
            clips.append((cursor, w))
            meta.append((ln["character"], ln["line"]))
            a = int(cursor * sr)
            if a + len(w) > len(track):
                track = np.pad(track, (0, a + len(w) - len(track)))
            track[a : a + len(w)] += w
            end = cursor + len(w) / sr
            if end > (i + 1) * SEG + 1e-6:
                report["late_lines"].append({"segment": i, "character": ln["character"], "late_by_s": round(end - (i + 1) * SEG, 2)})
            cursor = end + gap
            report["lines"] += 1
    report["overflow_s"] = round(max(0.0, cursor - gap - total), 2)
    report["meta"] = meta
    report["clips"] = clips  # [(start_s, wave)] so lines can be re-timed individually (lip-sync)
    return track[: int(max(total, cursor) * sr)], report


def compose(clips, shifts, total_s: float, sr: int) -> np.ndarray:
    """Re-place clips at start + shift (seconds)."""
    track = np.zeros(int(total_s * sr) + sr * 10, np.float32)
    for (start, w), sh in zip(clips, shifts):
        a = max(0, int((start + sh) * sr))
        if a + len(w) > len(track):
            track = np.pad(track, (0, a + len(w) - len(track)))
        track[a : a + len(w)] += w
    return track[: int(max(total_s, max((s + len(w) / sr for (s, w) in clips), default=0) + max(shifts, default=0)) * sr)]


def ambience_bed(path: str, n: int, sr: int, xfade: float = 1.0) -> np.ndarray:
    """Loop an ambience clip to n samples with equal-power crossfades."""
    if not path:
        return np.zeros(n, np.float32)
    clip = read_wav(path, sr)
    xf = min(int(xfade * sr), len(clip) // 3)
    if len(clip) < 2 * xf + 1:
        return np.zeros(n, np.float32)
    out = clip.copy()
    ramp = np.linspace(0, 1, xf)
    while len(out) < n:
        out[-xf:] = out[-xf:] * np.cos(ramp * np.pi / 2) + clip[:xf] * np.sin(ramp * np.pi / 2)
        out = np.concatenate([out, clip[xf:]])
    return out[:n].astype(np.float32)


def duck_gain(d: np.ndarray, sr: int, bed_db: float = -24.0, duck_db: float = -9.0) -> np.ndarray:
    """Linear bed gain over time: bed_db when quiet, bed_db + duck_db while dialogue is active (150 ms smoothing)."""
    k = int(0.15 * sr)
    env = np.convolve(np.abs(d), np.ones(k) / k, mode="same")
    act = np.clip(env / (0.1 * (env.max() + 1e-9)), 0, 1)
    return 10 ** ((bed_db + duck_db * act) / 20)


def mix(dialogue: np.ndarray, bed: np.ndarray, sr: int, bed_db: float = -24.0, duck_db: float = -9.0,
        target_rms_db: float = -18.0) -> np.ndarray:
    """Dialogue on top; the bed is ducked while dialogue is active (smoothed side-chain), then loudness-normalised."""
    n = max(len(dialogue), len(bed))
    d = np.pad(dialogue, (0, n - len(dialogue)))
    b = np.pad(bed, (0, n - len(bed)))
    gain = duck_gain(d, sr, bed_db, duck_db)
    bed_rms = np.sqrt((b ** 2).mean()) + 1e-9
    m = d + b / bed_rms * 0.1 * gain
    rms = np.sqrt((m ** 2).mean()) + 1e-9
    m = m * 10 ** (target_rms_db / 20) / rms
    peak = np.abs(m).max()
    return (m * (0.97 / peak) if peak > 0.97 else m).astype(np.float32)


def write_wav(path: str, w: np.ndarray, sr: int) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with wave.open(path, "wb") as f:
        f.setnchannels(1), f.setsampwidth(2), f.setframerate(sr)
        f.writeframes((np.clip(w, -1, 1) * 32767).astype("<i2").tobytes())


def mux(video: str, wav: str, out: str) -> None:
    subprocess.run([_ffmpeg(), "-v", "error", "-y", "-i", video, "-i", wav, "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-shortest", out], check=True)
