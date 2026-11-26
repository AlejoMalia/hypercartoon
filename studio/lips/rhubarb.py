"""Audio-accurate mouth cues with Rhubarb Lip Sync (DanielSWolf/rhubarb-lip-sync, MIT): the de-facto tool that outputs the
classic cartoon mouth shapes A-H + X from a recording. Needs the `rhubarb` binary (PATH or HYPERCARTOON_RHUBARB).
JSON export: {"mouthCues": [{"start": 0.0, "end": 0.12, "value": "X"}, ...]}  (shapes A-F basic, G/H/X extended)."""
import json
import os
import shutil
import subprocess
import tempfile
from typing import List, Optional, Tuple

import numpy as np

from studio.lips.visemes import OPEN

# Rhubarb shape -> our (Preston Blair style) viseme names
SHAPE_MAP = {"A": "MBP", "B": "ETC", "C": "E", "D": "AI", "E": "O", "F": "WQ", "G": "FV", "H": "L", "X": "REST"}


def find_binary() -> Optional[str]:
    p = os.environ.get("HYPERCARTOON_RHUBARB") or shutil.which("rhubarb")
    return p if p and os.path.exists(p) else None


def parse_cues(data) -> List[Tuple[float, float, str]]:
    """JSON text or dict -> [(start, end, shape A-H/X)] sorted, validated."""
    d = json.loads(data) if isinstance(data, (str, bytes)) else data
    cues = [(float(c["start"]), float(c["end"]), str(c["value"]).upper()) for c in d.get("mouthCues", [])]
    bad = [c for c in cues if c[2] not in SHAPE_MAP or c[1] < c[0]]
    if bad:
        raise ValueError(f"invalid mouth cue(s): {bad[:3]}")
    return sorted(cues)


def run_rhubarb(wav_path: str, dialog_text: Optional[str] = None, binary: Optional[str] = None, timeout: float = 180.0):
    """Run the binary on a WAV and return the cues. A dialog text makes recognition much more accurate."""
    exe = binary or find_binary()
    if not exe:
        raise RuntimeError("rhubarb not found (install it and set HYPERCARTOON_RHUBARB or put it in PATH)")
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "cues.json")
        cmd = [exe, "-f", "json", "--extendedShapes", "GHX", "-o", out, "--quiet"]
        if dialog_text:
            dlg = os.path.join(tmp, "dialog.txt")
            open(dlg, "w", encoding="utf-8").write(dialog_text)
            cmd += ["--dialogFile", dlg]
        r = subprocess.run(cmd + [wav_path], capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0 or not os.path.exists(out):
            raise RuntimeError(f"rhubarb failed: {r.stderr[-300:]}")
        return parse_cues(open(out, encoding="utf-8").read())


def cues_track(cues, duration: float, fps: int) -> np.ndarray:
    """Per-frame openness in [0,1] from cues (frame centre decides which cue is active; REST outside)."""
    n = max(1, int(round(duration * fps)))
    out = np.zeros(n)
    for a, b, v in cues:
        i0, i1 = int(np.floor(a * fps + 0.5 - 1e-9)), int(np.floor(b * fps + 0.5 - 1e-9))
        out[max(i0, 0) : min(i1, n)] = OPEN[SHAPE_MAP[v]]
    return out


def shape_names(cues) -> List[Tuple[float, float, str]]:
    return [(a, b, SHAPE_MAP[v]) for a, b, v in cues]
