"""Optional stem separation (dialogue vs everything else) with Demucs' command line, used to get *clean* references
and ambience from episodes that have music under the dialogue.  pip install demucs  (MIT).
Stronger separators (BS-RoFormer / Mel-RoFormer checkpoints) can replace this behind the same function."""
import os
import subprocess
import sys
from typing import Tuple


def split_dialogue(path: str, out_dir: str, model: str = "htdemucs") -> Tuple[str, str]:
    """-> (vocals.wav, no_vocals.wav). `vocals` is voice-like content incl. sung vocals; tune per show."""
    subprocess.run([sys.executable, "-m", "demucs", "--two-stems=vocals", "-n", model, "-o", out_dir, path], check=True)
    stem = os.path.join(out_dir, model, os.path.splitext(os.path.basename(path))[0])
    return os.path.join(stem, "vocals.wav"), os.path.join(stem, "no_vocals.wav")
