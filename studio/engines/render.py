"""Episode -> video with any local engine. Reads the `prompts.jsonl` that `create` wrote (3-second segments with the learned style, the
characters and the negative text), cuts it into clips the engine can make, renders them (resumable), joins them in order and puts the
regenerated dialogue on top. Scenes longer than the engine's limit are continued from the last frame when the engine has an image-to-video
pipeline; otherwise they become separate clips and the report says so."""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from studio.engines.registry import EngineSpec

SEG = 3.0
_TOKENS = re.compile(r"</?end_scene>|<start_scene>|<end_scene>")


def clean(text: str) -> str:
    return _TOKENS.sub("", text).strip()


def load_videos(path: str) -> List[List[dict]]:
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def plan_clips(videos: List[List[dict]], spec: EngineSpec) -> List[dict]:
    """Scenes (split at scene transitions) -> chunks of at most the engine's duration."""
    per = max(1, int(spec.max_seconds // SEG))
    clips = []
    for vi, segs in enumerate(videos):
        scenes: List[List[dict]] = []
        for k, sg in enumerate(segs):
            if k == 0 or sg.get("requires_scene_transition"):
                scenes.append([])
            scenes[-1].append(sg)
        for si, sc in enumerate(scenes):
            for ci in range(0, len(sc), per):
                chunk = sc[ci : ci + per]
                clips.append({"video": vi, "scene": si, "chunk": ci // per, "segments": len(chunk), "seconds": len(chunk) * SEG,
                              "prompt": clean(chunk[0]["text"]), "negative": chunk[0].get("neg_text") or "", "continues": ci > 0,
                              "frames": spec.frames_for(len(chunk) * SEG),
                              "name": f"v{vi:03d}_s{si:02d}_c{ci // per:02d}"})
    return clips


def estimate(clips: List[dict], spec: EngineSpec, steps: Optional[int] = None) -> Dict:
    st = steps or spec.steps
    return {"clips": len(clips), "seconds": sum(c["seconds"] for c in clips), "denoising_steps_total": len(clips) * st,
            "continued_from_last_frame": sum(c["continues"] for c in clips) if spec.i2v_pipeline else 0,
            "hard_cuts_inside_scenes": 0 if spec.i2v_pipeline else sum(c["continues"] for c in clips)}


def _ffmpeg() -> str:
    from studio.audio import _ffmpeg

    return _ffmpeg()


def write_clip(frames: np.ndarray, path: str, fps: int) -> None:
    import imageio

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    w = imageio.get_writer(path, fps=fps, codec="libx264", macro_block_size=1, ffmpeg_params=["-pix_fmt", "yuv420p"])
    for f in frames:
        w.append_data(f)
    w.close()


def join(clips: List[str], out: str, size: Tuple[int, int], fps: int, wav: Optional[str] = None) -> str:
    """Concatenate clips (re-scaled to one size and rate) and, if given, put the dialogue audio on top."""
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    ins: List[str] = []
    for c in clips:
        ins += ["-i", c]
    n = len(clips)
    f = ";".join(f"[{i}:v]scale={size[0]}:{size[1]}:force_original_aspect_ratio=increase,crop={size[0]}:{size[1]},fps={fps},setsar=1[v{i}]" for i in range(n))
    f += ";" + "".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[v]"
    cmd = [_ffmpeg(), "-y", "-loglevel", "error", *ins]
    if wav:
        cmd += ["-i", wav]
    cmd += ["-filter_complex", f, "-map", "[v]"]
    if wav:
        cmd += ["-map", f"{n}:a", "-c:a", "aac", "-shortest"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out]
    subprocess.run(cmd, check=True)
    return out


def render_episode(ep_dir: str, engine, out_dir: Optional[str] = None, seed: int = 0, steps: Optional[int] = None, guidance: Optional[float] = None,
                   size_out: Tuple[int, int] = (720, 480), fps_out: int = 16, progress: Optional[Callable] = None, dry: bool = False,
                   only_video: Optional[int] = None) -> Dict:
    spec: EngineSpec = engine.spec
    out_dir = out_dir or os.path.join(ep_dir, "video", spec.id)
    prompts = os.path.join(ep_dir, "prompts.jsonl")
    if not os.path.exists(prompts):
        raise FileNotFoundError(f"no hay {prompts}: ejecuta primero `studio create guion.txt`")
    videos = load_videos(prompts)
    clips = plan_clips(videos, spec)
    if only_video is not None:
        clips = [c for c in clips if c["video"] == only_video]
    rep = {"engine": spec.id, "repo": engine.repo or spec.repo, "native_size": list(spec.size), "native_fps": spec.fps, "estimate": estimate(clips, spec, steps),
           "clips": clips, "out_dir": out_dir}
    if dry:
        return rep
    t0, done = time.time(), []
    for k, c in enumerate(clips):
        path = os.path.join(out_dir, "clips", c["name"] + ".mp4")
        if not os.path.exists(path):  # resumable: finished clips are kept
            img = None
            if c["continues"] and spec.i2v_pipeline and done:
                import imageio

                r = imageio.get_reader(done[-1], "ffmpeg")
                last = None
                for last in r:
                    pass
                r.close()
                img = last
            frames = engine.generate(c["prompt"], c["negative"], c["seconds"], seed + k, steps, guidance, None, img)
            write_clip(frames, path, spec.fps)
        done.append(path)
        progress and progress((k + 1) / len(clips), c["name"])
    outs = []
    for vi in sorted({c["video"] for c in clips}):
        mine = [os.path.join(out_dir, "clips", c["name"] + ".mp4") for c in clips if c["video"] == vi]
        wav = os.path.join(ep_dir, "sound", f"video_{vi:03d}.wav")
        outs.append(join(mine, os.path.join(out_dir, f"episodio_video_{vi:03d}.mp4"), size_out, fps_out, wav if os.path.exists(wav) else None))
    rep.update(videos=outs, seconds_total=time.time() - t0, size=list(size_out), fps=fps_out)
    json.dump(rep, open(os.path.join(out_dir, "render.json"), "w"), indent=1, ensure_ascii=False)
    return rep


def native_commands(ep_dir: str) -> List[str]:
    """The Hypercartoon engine runs through its own sample.py: the commands `create` already wrote."""
    p = os.path.join(ep_dir, "episode.json")
    if not os.path.exists(p):
        raise FileNotFoundError(f"no hay {p}: ejecuta primero `studio create guion.txt`")
    return json.load(open(p)).get("generate_video_commands", [])
