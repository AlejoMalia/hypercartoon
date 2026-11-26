"""Hooks for external tools that polish a generated episode (lip-sync models, upscalers, frame interpolation...).
Nothing here knows any tool's CLI: you declare commands in `postprocess.json` inside the project; placeholders are
{video} {audio} {out} {workdir} {name}. Steps run in order, each reading the previous step's output as {video}. A step whose
executable is missing is skipped with the reason. Example (check each tool's own README for its real command):
  {"steps": [{"name": "lipsync", "when": "has_audio", "cmd": "python -m scripts.inference --video_path {video} --audio_path {audio} --video_out_path {out}"}]}
Candidates found while researching: ByteDance/LatentSync (lip-sync, Apache-2.0 per third-party sources), TMElyralab/MuseTalk
(licence unclear), ToonCrafter (cartoon interpolation), Real-ESRGAN anime models (upscaling). Verify licences yourself."""
import json
import os
import shlex
import shutil
import subprocess
from typing import List, Optional

KNOWN = {"video", "audio", "out", "workdir", "name"}


def load_steps(ws: str) -> List[dict]:
    p = os.path.join(ws, "postprocess.json")
    return json.load(open(p)).get("steps", []) if os.path.exists(p) else []


def run_steps(steps: List[dict], video: str, audio: Optional[str], workdir: str, name: str = "episode", dry: bool = False) -> List[dict]:
    log, cur = [], video
    os.makedirs(workdir, exist_ok=True)
    for i, st in enumerate(steps):
        rec = {"name": st.get("name", f"step{i}"), "status": "ok", "note": ""}
        log.append(rec)
        if st.get("when") == "has_audio" and not audio:
            rec.update(status="skipped", note="no hay audio")
            continue
        out = os.path.join(workdir, f"{name}.{rec['name']}.mp4")
        if st.get("builtin") == "finish":  # {"builtin": "finish", "format": "fhd", "model": "anime-video", ...}
            from studio.finish import finish_video

            opts = {k: v for k, v in st.items() if k in ("fit", "model", "tile", "half", "device", "sharpen", "denoise", "crf", "use_ai", "allow_download", "weights_dir")}
            try:
                r = finish_video(cur, out, st.get("format", "fhd"), dry=dry, **opts)
                rec["note"] = f"{r['mode']} -> {r['plan']['target'][0]}x{r['plan']['target'][1]}"
                if not dry:
                    cur = out
            except Exception as e:
                rec.update(status="error", note=str(e)[:300])
            continue
        try:
            argv = shlex.split(st["cmd"].format(video=cur, audio=audio or "", out=out, workdir=workdir, name=name))
        except (KeyError, IndexError) as e:
            rec.update(status="error", note=f"marcador desconocido {e}")
            continue
        if not shutil.which(argv[0]):
            rec.update(status="skipped", note=f"no está instalado: {argv[0]}")
            continue
        if dry:
            rec["note"] = " ".join(argv)
            continue
        r = subprocess.run(argv, capture_output=True, text=True, cwd=st.get("cwd") or None)
        if r.returncode != 0 or not os.path.exists(out):
            rec.update(status="error", note=(r.stderr or r.stdout)[-300:])
            continue
        cur = out
    return log + [{"final": cur}]
