"""Audio side: decode, voice-activity segments, voice embeddings, transcription.

Zero-dependency fallbacks (numpy only) keep the pipeline runnable and testable anywhere; stronger backends are
lazy imports and must be validated on real cartoons (music/SFX are the main failure mode of energy VAD):
  embeddings : speechbrain ECAPA-TDNN     (pip install speechbrain)
  diarization: pyannote.audio 3.1          (pip install pyannote.audio, needs a HF token)
  transcript : faster-whisper              (pip install faster-whisper)
"""
import shutil
import subprocess
from typing import List, Tuple

import numpy as np

SR = 16000


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def load_audio(path: str, sr: int = SR) -> np.ndarray:
    """Mono float32 in [-1,1], streamed through ffmpeg (no temp files). Empty array if the file has no audio."""
    p = subprocess.run([_ffmpeg(), "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                       capture_output=True)
    return np.frombuffer(p.stdout, dtype=np.float32) if p.returncode == 0 else np.zeros(0, np.float32)


def energy_vad(wave: np.ndarray, sr: int = SR, frame: float = 0.03, min_speech: float = 0.4,
               max_gap: float = 0.3) -> List[Tuple[float, float]]:
    """Adaptive-threshold energy VAD with zero-crossing sanity (rejects pure tones/hum). Returns [(start, end)] s."""
    n = int(frame * sr)
    if len(wave) < 2 * n:
        return []
    f = wave[: len(wave) // n * n].reshape(-1, n)
    e = np.log10((f ** 2).mean(1) + 1e-10)
    zcr = (np.abs(np.diff(np.sign(f), axis=1)) > 0).mean(1)
    thr = np.percentile(e, 20) + 0.35 * (np.percentile(e, 95) - np.percentile(e, 20))
    on = (e > thr) & (zcr > 0.005) & (zcr < 0.45)
    segs, start = [], None
    for i, v in enumerate(np.r_[on, False]):
        if v and start is None:
            start = i
        elif not v and start is not None:
            segs.append([start * frame, i * frame])
            start = None
    merged: List[List[float]] = []
    for s in segs:
        if merged and s[0] - merged[-1][1] <= max_gap:
            merged[-1][1] = s[1]
        else:
            merged.append(s)
    return [(a, b) for a, b in merged if b - a >= min_speech]


def _mel_fb(n_mels: int, n_fft: int, sr: int) -> np.ndarray:
    mel = lambda f: 2595 * np.log10(1 + f / 700)
    inv = lambda m: 700 * (10 ** (m / 2595) - 1)
    pts = inv(np.linspace(mel(60), mel(sr / 2 - 100), n_mels + 2))
    bins = np.floor((n_fft + 1) * pts / sr).astype(int)
    fb = np.zeros((n_mels, n_fft // 2 + 1))
    for m in range(1, n_mels + 1):
        l, c, r = bins[m - 1], bins[m], bins[m + 1]
        fb[m - 1, l:c] = (np.arange(l, c) - l) / max(c - l, 1)
        fb[m - 1, c:r] = (r - np.arange(c, r)) / max(r - c, 1)
    return fb


def logmel_embedding(seg: np.ndarray, sr: int = SR, n_mels: int = 40) -> np.ndarray:
    """Fallback voice embedding: mean + std of log-mel over voiced frames (80-d). Weak but dependency-free."""
    n_fft, hop = 512, 160
    if len(seg) < n_fft:
        seg = np.pad(seg, (0, n_fft - len(seg)))
    idx = np.arange(0, len(seg) - n_fft + 1, hop)[:, None] + np.arange(n_fft)[None]
    spec = np.abs(np.fft.rfft(seg[idx] * np.hanning(n_fft), axis=1)) ** 2
    lm = np.log(spec @ _mel_fb(n_mels, n_fft, sr).T + 1e-8)
    lm = lm[lm.mean(1) > np.percentile(lm.mean(1), 40)]  # voiced frames only
    return np.concatenate([lm.mean(0), lm.std(0)])


def speech_segments(path: str, embed=logmel_embedding, sr: int = SR):
    """-> [(start, end, vec)] for one file. `embed` is swappable (ECAPA etc.)."""
    w = load_audio(path, sr)
    return [(a, b, embed(w[int(a * sr) : int(b * sr)])) for a, b in energy_vad(w, sr)]


# ---- heavy backends (lazy; unverified here: no GPU / packages) ----------------------------------------
def ecapa_embedder(device: str = "cpu"):
    from speechbrain.inference.speaker import EncoderClassifier
    import torch

    m = EncoderClassifier.from_hparams("speechbrain/spkrec-ecapa-voxceleb", run_opts={"device": device})

    def embed(seg: np.ndarray, sr: int = SR) -> np.ndarray:
        with torch.no_grad():
            return m.encode_batch(torch.from_numpy(seg)[None].to(device)).squeeze().cpu().numpy()

    return embed


def transcribe(path: str, model: str = "small", device: str = "auto"):
    """-> [(start, end, text)] via faster-whisper."""
    from faster_whisper import WhisperModel

    segs, _ = WhisperModel(model, device=device).transcribe(path, vad_filter=True)
    return [(s.start, s.end, s.text.strip()) for s in segs]


def transcribe_words(path: str, model: str = "small", device: str = "auto", language: str = None):
    """-> [(start, end, word)] via faster-whisper word timestamps (WhisperX gives the same plus diarization, m-bain/whisperX)."""
    from faster_whisper import WhisperModel

    segs, _ = WhisperModel(model, device=device).transcribe(path, word_timestamps=True, language=language)
    return [(w.start, w.end, w.word.strip()) for s in segs for w in (s.words or [])]
