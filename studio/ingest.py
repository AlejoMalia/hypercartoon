"""Scan a folder of videos, measure content + time, detect shots. Streaming, low-res, cached per file."""
import json
import os
from dataclasses import asdict, dataclass, field
from typing import Dict, List

import numpy as np

VIDEO_EXT = (".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mpg", ".mpeg", ".wmv", ".flv", ".3gp", ".ogv", ".m2ts")


@dataclass
class Shot:
    start: float  # seconds
    end: float
    motion: float  # mean abs frame difference in [0,1]
    brightness: float
    palette: List[List[int]] = field(default_factory=list)  # top RGB colours


@dataclass
class VideoInfo:
    path: str
    size: int
    mtime: float
    fps: float
    width: int
    height: int
    duration: float
    shots: List[Shot]


def _hist(gray: np.ndarray) -> np.ndarray:
    h = np.bincount((gray >> 3).ravel(), minlength=32).astype(np.float32)
    return h / max(h.sum(), 1.0)


def detect_shots(frames, fps: float, min_len: int = 8, thr: float = 0.35):
    """frames: iterable of small RGB uint8 arrays. Returns list of (start_idx, end_idx) and per-frame diffs."""
    prev_h, prev_g, diffs, cuts, small = None, None, [], [0], []
    for i, f in enumerate(frames):
        g = f.mean(2).astype(np.uint8)
        h = _hist(g)
        d = 0.0 if prev_h is None else 0.5 * float(np.abs(h - prev_h).sum())
        mot = 0.0 if prev_g is None else float(np.abs(g.astype(np.int16) - prev_g).mean() / 255.0)
        diffs.append(mot)
        if d > thr and i - cuts[-1] >= min_len:
            cuts.append(i)
        prev_h, prev_g = h, g.astype(np.int16)
        small.append(f)
    n = len(diffs)
    bounds = list(zip(cuts, cuts[1:] + [n]))
    return bounds, np.array(diffs), small


def _palette(frames: List[np.ndarray], k: int = 5):
    if not frames:
        return []
    px = (np.concatenate([f.reshape(-1, 3) for f in frames]) >> 5).astype(np.int32)  # 3 bits / channel
    key = px[:, 0] * 64 + px[:, 1] * 8 + px[:, 2]
    top = np.argsort(np.bincount(key, minlength=512))[::-1][:k]
    return [[int(t // 64 * 32 + 16), int(t // 8 % 8 * 32 + 16), int(t % 8 * 32 + 16)] for t in top]


def analyze_video(path: str, stride: int = 8) -> VideoInfo:
    import imageio

    r = imageio.get_reader(path, "ffmpeg")
    meta = r.get_meta_data()
    fps = float(meta["fps"])
    w, h = meta["size"]

    def small():
        for f in r:
            yield f[::stride, ::stride]

    bounds, mot, frames = detect_shots(small(), fps)
    r.close()
    n = len(frames)
    better = scenedetect_bounds(path, fps, n)  # optional: AdaptiveDetector handles fades/pans better than a histogram diff
    if better:
        bounds = better
    shots = []
    for a, b in bounds:
        seg = frames[a:b]
        shots.append(Shot(a / fps, b / fps, float(mot[a + 1 : b].mean()) if b - a > 1 else 0.0,
                          float(np.mean([s.mean() for s in seg[:: max(1, len(seg) // 8)]]) / 255.0),
                          _palette(seg[:: max(1, len(seg) // 6)])))
    st = os.stat(path)
    return VideoInfo(path, st.st_size, st.st_mtime, fps, w, h, n / fps, shots)


def load_manifest(path: str) -> Dict[str, VideoInfo]:
    out = {}
    if os.path.exists(path):
        for k, v in json.load(open(path)).items():
            v["shots"] = [Shot(**s) for s in v["shots"]]
            out[k] = VideoInfo(**v)
    return out


def scenedetect_bounds(path: str, fps: float, n_frames: int):
    """Shot boundaries from PySceneDetect's AdaptiveDetector (Breakthrough/PySceneDetect) as [(start_idx, end_idx)];
    None when the package is missing or finds nothing, so the histogram detector is used instead."""
    try:
        from scenedetect import AdaptiveDetector, detect
    except Exception:
        return None
    try:
        scenes = detect(path, AdaptiveDetector())
    except Exception:
        return None
    return bounds_from_scenes([(a.get_seconds(), b.get_seconds()) for a, b in scenes], fps, n_frames)


def bounds_from_scenes(scenes, fps: float, n_frames: int):
    if not scenes:
        return None
    b = [(min(int(round(a * fps)), n_frames - 1), min(int(round(e * fps)), n_frames)) for a, e in scenes]
    b = [(a, e) for a, e in b if e > a]
    if b:
        b[0] = (0, b[0][1])
        b[-1] = (b[-1][0], n_frames)
    return b or None


def list_videos(folder: str):
    """Video files under a folder (sorted), or the file itself."""
    if os.path.isfile(folder):
        return [folder]
    out = []
    for root, _, files in os.walk(folder):
        out += [os.path.join(root, f) for f in sorted(files) if f.lower().endswith(VIDEO_EXT)]
    return sorted(out)


def ingest_paths(paths, manifest_path: str, analyze=analyze_video, workers: int = 1, progress=None) -> Dict[str, VideoInfo]:
    """Incremental: unchanged files (same size+mtime) are never re-analyzed. progress(done, total, path) after each file."""
    old = load_manifest(manifest_path)
    out, todo = {}, []
    for p in paths:
        st = os.stat(p)
        c = old.get(p)
        if c and c.size == st.st_size and c.mtime == st.st_mtime:
            out[p] = c
        else:
            todo.append(p)
    total, done = len(paths), len(out)
    if progress:
        progress(done, total, "")
    if workers > 1 and len(todo) > 1:  # decoding is CPU-bound and per-file independent
        from concurrent.futures import ProcessPoolExecutor

        with ProcessPoolExecutor(workers) as ex:
            for p, info in zip(todo, ex.map(analyze, todo)):
                out[p] = info
                done += 1
                progress and progress(done, total, p)
    else:
        for p in todo:
            out[p] = analyze(p)
            done += 1
            progress and progress(done, total, p)
    os.makedirs(os.path.dirname(manifest_path) or ".", exist_ok=True)
    json.dump({k: asdict(v) for k, v in out.items()}, open(manifest_path, "w"), indent=1)
    return out


def ingest_folder(folder: str, manifest_path: str, analyze=analyze_video, workers: int = 1, progress=None) -> Dict[str, VideoInfo]:
    return ingest_paths(list_videos(folder), manifest_path, analyze, workers, progress)
