"""Learn a style/time profile from the manifest and derive an automatic training plan (self-regulated by data)."""
from collections import Counter
from typing import Dict

import numpy as np

SEG = 3.0  # Hypercartoon works on 3-second segments
STAGES = [3, 9, 18, 30, 63]  # seconds, curriculum ladder (see configs/train)
MIN_CLIPS_PER_STAGE = 32


def build_profile(videos: Dict) -> Dict:
    shots = [s for v in videos.values() for s in v.shots]
    if not shots:
        raise ValueError("no shots found")
    lens = np.array([s.end - s.start for s in shots])
    pal = Counter()
    for s in shots:
        for c in s.palette:
            pal[tuple(c)] += 1
    vids = list(videos.values())
    return {
        "n_videos": len(vids),
        "total_seconds": float(sum(v.duration for v in vids)),
        "fps": float(np.median([v.fps for v in vids])),
        "aspect": float(np.median([v.width / v.height for v in vids])),
        "shot_len": {"median": float(np.median(lens)), "p10": float(np.percentile(lens, 10)),
                     "p90": float(np.percentile(lens, 90))},
        "cuts_per_min": float(len(shots) / max(sum(v.duration for v in vids), 1e-6) * 60),
        "motion": float(np.mean([s.motion for s in shots])),
        "brightness": float(np.mean([s.brightness for s in shots])),
        "palette": [list(c) for c, _ in pal.most_common(6)],
        # contiguous runnable length available per video (shots concatenate into one episode)
        "episode_seconds": [float(v.duration) for v in vids],
    }


def style_prompt(p: Dict) -> str:
    """Learned style words appended to every scene so identity/style stay constant across segments."""
    pace = "fast-paced" if p["cuts_per_min"] > 20 else "slow, calm" if p["cuts_per_min"] < 6 else "medium-paced"
    mot = "energetic motion" if p["motion"] > 0.08 else "gentle motion" if p["motion"] < 0.02 else "moderate motion"
    tone = "bright" if p["brightness"] > 0.6 else "dark moody" if p["brightness"] < 0.35 else "balanced lighting"
    return f"cartoon style, {pace}, {mot}, {tone}, consistent characters"


def training_plan(p: Dict, gpu_mem_gb: float = 80.0, global_batch: int = 64) -> Dict:
    """Pick the curriculum from what the data can actually support; scale steps to data size."""
    stages = []
    for s in STAGES:
        clips = int(sum(e // s for e in p["episode_seconds"]))
        if clips >= (MIN_CLIPS_PER_STAGE if s > 3 else 1):
            stages.append({"seconds": s, "clips": clips,
                           "steps": int(np.clip(clips * 20 / global_batch * 8, 500, 5000)),
                           "layer": "hyper_mlp" if gpu_mem_gb >= 80 else "hyper_linear"})
    if not stages:
        raise SystemExit("Not enough material: need at least 3 s of video in the folder.")
    return {"stages": stages, "max_seconds": stages[-1]["seconds"],
            "note": "hyper_mlp needs H100; hyper_linear chosen below 80GB" if gpu_mem_gb < 80 else ""}


def segment_cuts(videos: Dict) -> list:
    """3-second training segments per video (cut points only; no re-encoding here)."""
    out = []
    for p, v in videos.items():
        n = int(v.duration // SEG)
        out += [{"video": p, "start": i * SEG, "dur": SEG} for i in range(n)]
    return out


def ffmpeg_script(cuts: list, out_dir: str, fps: int = 16) -> str:
    lines = ["#!/bin/bash", "set -e", f"mkdir -p {out_dir}"]
    for i, c in enumerate(cuts):
        lines.append(f'ffmpeg -loglevel error -y -ss {c["start"]} -t {c["dur"] + 0.1} -i "{c["video"]}" '
                     f'-frames:v {int(fps * c["dur"]) + 1} -r {fps} -vf "scale=720:480:force_original_aspect_ratio=increase,crop=720:480" -an '
                     f'{out_dir}/{i:06d}.mp4')
    return "\n".join(lines) + "\n"


def season_profiles(corpus: Dict, videos: Dict) -> Dict:
    """Profile per (series, season) so style drift between seasons is visible; global profile uses everything."""
    out = {}
    for series, seasons in corpus.items():
        for se, eps in seasons.items():
            sub = {e["path"]: videos[e["path"]] for e in eps if e["path"] in videos}
            if sub:
                p = build_profile(sub)
                p["episodes"] = len(sub)
                out[f"{series}/S{se:02d}"] = p
    return out


def chapter_seconds(p: Dict) -> float:
    """Typical episode length = what 'reproduce a chapter' targets; the plan stages only cap one generation pass."""
    return float(np.median(p["episode_seconds"]))
