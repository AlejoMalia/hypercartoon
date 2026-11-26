"""Catalogue of local generation engines: what each one is, what it needs, what it can do. Facts that were checked against the
model cards / diffusers documentation are listed in `checked`; the rest (marked in docs/engines.md) must be confirmed on the card
before a long run. None of these models was downloaded or run while writing this module."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class EngineSpec:
    id: str
    title: str
    params_b: float
    license: str
    pipeline: str                       # diffusers class name ("" = not in diffusers)
    repo: str                           # Hugging Face repo id (diffusers format)
    i2v_pipeline: str = ""              # image-to-video class, used to continue a scene from its last frame
    i2v_repo: str = ""
    size: Tuple[int, int] = (720, 480)  # (width, height) native
    fps: int = 16
    max_frames: int = 49
    frame_rule: str = "8k+1"            # valid frame counts: k*m+1
    min_vram_gb: float = 16.0           # with CPU offloading / tiling
    ok_vram_gb: float = 24.0            # comfortable, no offloading
    steps: int = 50
    guidance: float = 6.0
    negative: bool = True               # accepts a negative prompt
    guider: bool = False                # guidance is set on pipe.guider (HunyuanVideo 1.5), not per call
    dtype: str = "bfloat16"
    audio: bool = False
    download_gb: float = 0.0            # what from_pretrained downloads (diffusers components, measured on the hub; 0 = unknown)
    lora_trainer: str = "finetrainers"  # `builtin` = studio train-lora
    commercial: str = "check the licence"
    notes: str = ""
    checked: List[str] = field(default_factory=list)

    @property
    def max_seconds(self) -> float:
        return self.max_frames / self.fps

    def frames_for(self, seconds: float) -> int:
        """Largest valid frame count not above the request (and not above the engine's limit), at least the smallest valid one."""
        m = int(self.frame_rule.split("k")[0])
        want = min(self.max_frames, max(1, int(round(seconds * self.fps))))
        return max(m + 1, ((want - 1) // m) * m + 1)


ENGINES: Dict[str, EngineSpec] = {s.id: s for s in [
    EngineSpec("wan22-ti2v-5b", "Wan 2.2 TI2V-5B", 5.0, "Apache-2.0", "WanPipeline", "Wan-AI/Wan2.2-TI2V-5B-Diffusers",
               size=(1280, 704), fps=24, max_frames=121, frame_rule="4k+1", min_vram_gb=12.0, ok_vram_gb=24.0, steps=50, guidance=5.0,
               download_gb=34.2, commercial="Apache-2.0: commercial use allowed", notes="best open quality for its size; needs diffusers from main; 720p at 24 fps",
               checked=["class WanPipeline", "repo id", "720p / 121 frames / guidance 5.0 in community scripts"]),
    EngineSpec("ltx-video", "LTX-Video", 2.0, "LTX community licence (free under a revenue threshold)", "LTXPipeline", "Lightricks/LTX-Video",
               i2v_pipeline="LTXImageToVideoPipeline", i2v_repo="Lightricks/LTX-Video", size=(704, 480), fps=24, max_frames=161, frame_rule="8k+1",
               min_vram_gb=8.0, ok_vram_gb=16.0, steps=50, guidance=3.0, download_gb=28.4, lora_trainer="builtin", commercial="free below a revenue threshold: read the licence",
               notes="fastest; about 10 GB VRAM; some newer versions generate audio", audio=False,
               checked=["class LTXPipeline", "repo id", "~10 GB VRAM", "704x480, 161 frames"]),
    EngineSpec("hunyuan-video-1.5", "HunyuanVideo 1.5", 8.3, "Tencent community licence (restrictions: read it)", "HunyuanVideo15Pipeline",
               "hunyuanvideo-community/HunyuanVideo-1.5-Diffusers-720p_t2v", size=(1280, 720), fps=24, max_frames=121, frame_rule="4k+1",
               min_vram_gb=14.0, ok_vram_gb=32.0, steps=50, guidance=6.0, negative=False, guider=True,
               download_gb=53.4, commercial="restricted by the Tencent licence (territory / scale clauses)", notes="cinematic quality; guidance goes through pipe.guider",
               checked=["class HunyuanVideo15Pipeline", "repo id", "guidance through pipe.guider", "cpu offload + vae tiling advised"]),
    EngineSpec("cogvideox-5b", "CogVideoX-5B", 5.0, "CogVideoX licence (custom; commercial use needs registration)", "CogVideoXPipeline", "THUDM/CogVideoX-5b",
               i2v_pipeline="CogVideoXImageToVideoPipeline", i2v_repo="THUDM/CogVideoX-5b-I2V", size=(720, 480), fps=8, max_frames=49, frame_rule="4k+1",
               min_vram_gb=8.0, ok_vram_gb=24.0, steps=50, guidance=6.0, download_gb=21.5, commercial="custom licence: register for commercial use",
               notes="same family as the Hypercartoon engine, without the test-time-training layers: 6 s clips", checked=["class CogVideoXPipeline"]),
    EngineSpec("cogvideox-2b", "CogVideoX-2B", 2.0, "Apache-2.0", "CogVideoXPipeline", "THUDM/CogVideoX-2b", size=(720, 480), fps=8, max_frames=49,
               frame_rule="4k+1", min_vram_gb=6.0, ok_vram_gb=12.0, steps=50, guidance=6.0, dtype="float16",
               download_gb=13.8, commercial="Apache-2.0: commercial use allowed", notes="smallest; runs on modest GPUs", checked=["class CogVideoXPipeline"]),
    EngineSpec("mochi-1", "Mochi 1", 10.0, "Apache-2.0", "MochiPipeline", "genmo/mochi-1-preview", size=(848, 480), fps=30, max_frames=84,
               frame_rule="6k+1", min_vram_gb=20.0, ok_vram_gb=40.0, steps=64, guidance=4.5, download_gb=90.6, commercial="Apache-2.0: commercial use allowed",
               notes="solid alternative; heavy", checked=[]),
    EngineSpec("longcat-video", "LongCat-Video", 13.6, "MIT", "", "meituan-longcat/LongCat-Video", size=(832, 480), fps=15, max_frames=93,
               min_vram_gb=40.0, ok_vram_gb=80.0, commercial="MIT", notes="long videos; has its own repository, not in diffusers: run it with its own scripts",
               checked=[]),
]}

# order of preference when the hardware allows several: permissive licence and modern quality first
PREFERENCE = ["wan22-ti2v-5b", "ltx-video", "cogvideox-2b", "hunyuan-video-1.5", "cogvideox-5b", "mochi-1"]


def get(engine_id: str) -> EngineSpec:
    if engine_id not in ENGINES:
        raise KeyError(f"motor desconocido «{engine_id}»; disponibles: hypercartoon, {', '.join(ENGINES)}")
    return ENGINES[engine_id]


def fits(spec: EngineSpec, hw: dict) -> str:
    """ok | offload | no | cpu-only: can this machine run it?"""
    if hw["device"] == "cpu":
        return "no"
    mem = hw["vram_gb"]
    if hw["device"] == "mps":  # unified memory: only a share of it is usable as VRAM
        mem = hw["ram_gb"] * 0.6
    return "ok" if mem >= spec.ok_vram_gb else "offload" if mem >= spec.min_vram_gb else "no"


def hf_cache() -> str:
    import os

    return os.environ.get("HF_HUB_CACHE") or os.path.join(os.environ.get("HF_HOME") or os.path.expanduser("~/.cache/huggingface"), "hub")


def is_cached(repo: str) -> bool:
    import os

    d = os.path.join(hf_cache(), "models--" + repo.replace("/", "--"), "snapshots")
    return os.path.isdir(d) and bool(os.listdir(d))


def disk_free_gb(path: str = "") -> float:
    import os
    import shutil

    p = path or hf_cache()
    while p and not os.path.exists(p):
        p = os.path.dirname(p)
    return shutil.disk_usage(p or "/").free / 1e9


def disk_problem(spec: EngineSpec, repo: str = "", reserve_gb: float = 3.0) -> str:
    """"" when the weights are cached or fit on disk (keeping `reserve_gb` free); otherwise a message with the numbers."""
    import os

    repo = repo or spec.repo
    if os.path.isdir(repo) or is_cached(repo) or not spec.download_gb:
        return ""
    free = disk_free_gb()
    if spec.download_gb + reserve_gb > free:
        return (f"{spec.title} descarga ≈ {spec.download_gb:g} GB y quedan {free:.1f} GB libres en {hf_cache()} (se dejan {reserve_gb:g} GB de margen). "
                f"Libera espacio o apunta la caché a otro disco: export HF_HOME=/Volumes/DISCO/hf")
    return ""
