"""What this machine can run: CUDA GPU / Apple MPS / CPU, memory, and whether torch + diffusers are installed. Works without torch."""
from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
from typing import Dict, List


def _ram_gb() -> float:
    try:
        if platform.system() == "Darwin":
            return int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip()) / 1e9
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9
    except Exception:
        return 0.0


def detect() -> Dict:
    from studio.engines.registry import disk_free_gb, hf_cache

    hw = {"disk_free_gb": round(disk_free_gb(), 1), "hf_cache": hf_cache(), "device": "cpu", "name": platform.processor() or platform.machine(), "vram_gb": 0.0, "ram_gb": round(_ram_gb(), 1),
          "torch": None, "diffusers": None, "cuda": False, "mps": False}
    try:
        import torch

        hw["torch"] = torch.__version__
        if torch.cuda.is_available():
            p = torch.cuda.get_device_properties(0)
            hw.update(device="cuda", cuda=True, name=p.name, vram_gb=round(p.total_memory / 1e9, 1))
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            hw.update(device="mps", mps=True, name="Apple GPU (unified memory)")
    except Exception:
        pass
    if hw["device"] == "cpu" and shutil.which("nvidia-smi"):  # a GPU exists but this Python has no CUDA torch
        try:
            out = subprocess.check_output(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"], text=True).splitlines()[0]
            name, mb = [x.strip() for x in out.split(",")]
            hw.update(name=name, vram_gb=round(float(mb) / 1024, 1), cuda_not_in_torch=True)
        except Exception:
            pass
    try:
        import diffusers

        hw["diffusers"] = diffusers.__version__
    except Exception:
        pass
    return hw


def recommend(hw: Dict) -> List[Dict]:
    """Engines ordered by preference with a verdict for this machine."""
    from studio.engines.registry import ENGINES, PREFERENCE, fits

    rows = [{"id": i, "title": ENGINES[i].title, "fit": fits(ENGINES[i], hw), "license": ENGINES[i].license, "min_vram_gb": ENGINES[i].min_vram_gb}
            for i in PREFERENCE + [k for k in ENGINES if k not in PREFERENCE]]
    order = {"ok": 0, "offload": 1, "no": 2}
    return sorted(rows, key=lambda r: (order[r["fit"]], PREFERENCE.index(r["id"]) if r["id"] in PREFERENCE else 99))


def advice_es(hw: Dict) -> List[str]:
    out = []
    if hw["device"] == "cpu":
        out.append("Sin GPU compatible: la generación de vídeo no es práctica en CPU. Puedes preparar todo (`create`, `render --dry`) y generar en una máquina con GPU.")
        if hw.get("cuda_not_in_torch"):
            out.append(f"Hay una GPU ({hw['name']}) pero este Python no tiene torch con CUDA: instala `torch` con CUDA.")
    elif hw["device"] == "mps":
        out.append("Apple GPU: funciona con diffusers en modo MPS (más lento y con menos modelos probados); los modelos pequeños (LTX-Video, CogVideoX-2B) son lo realista.")
    if hw["torch"] is None:
        out.append("Falta torch: pip install torch (con CUDA en NVIDIA).")
    if hw["diffusers"] is None:
        out.append("Falta diffusers: pip install git+https://github.com/huggingface/diffusers transformers accelerate sentencepiece ftfy imageio-ffmpeg")
    return out
