"""Finishing: sharpening ("afinado") and format scaling of generated video. TTT-Video / CogVideoX output 480x720; this brings
episodes to a delivery format (HD, FHD, 4K, square, vertical...) with Real-ESRGAN super-resolution (xinntao/Real-ESRGAN) when it is
installed, and a CPU fallback (ffmpeg Lanczos + mild unsharp / temporal denoise) when it is not.

Format handling is separate from the AI step: the network upsamples (always natively x4 for the models below) and the exact target is
reached with a final Lanczos resize + pad (fit) / crop (fill) / stretch, so any size works, e.g. 720x480 -> 1920x1080.
Honest limits: super-resolution can invent detail, per-frame processing can flicker (use the video-trained `anime-video` model and the
optional temporal denoise), and it costs GPU time proportional to the input pixels of every frame. Not run on a GPU here."""
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from typing import Callable, Dict, Optional, Tuple

import numpy as np

FORMATS: Dict[str, Tuple[int, int]] = {
    "hd": (1280, 720), "fhd": (1920, 1080), "qhd": (2560, 1440), "4k": (3840, 2160),
    "square": (1080, 1080), "vertical": (1080, 1920), "cinema": (2048, 858),
}
SHARPEN = {"off": 0.0, "light": 0.4, "medium": 0.8, "strong": 1.3}
RELEASE = "https://github.com/xinntao/Real-ESRGAN/releases/download"
MODELS = {  # key -> architecture + weight file (sizes follow the official repo; verify against its README)
    "anime-video": {"arch": "srvgg", "num_conv": 16, "file": "realesr-animevideov3.pth", "tag": "v0.2.5.0",
                    "about": "compact, trained for anime/cartoon VIDEO (default: lighter and more temporally stable)"},
    "anime6b": {"arch": "rrdb", "num_block": 6, "file": "RealESRGAN_x4plus_anime_6B.pth", "tag": "v0.2.2.4", "about": "anime / illustrations, per image"},
    "general": {"arch": "srvgg", "num_conv": 32, "file": "realesr-general-x4v3.pth", "tag": "v0.2.5.0", "about": "lighter general model"},
    "x4plus": {"arch": "rrdb", "num_block": 23, "file": "RealESRGAN_x4plus.pth", "tag": "v0.1.0", "about": "general photos (heaviest)"},
}


def parse_format(s: str) -> Tuple[int, int]:
    s = s.strip().lower()
    if s in FORMATS:
        return FORMATS[s]
    m = re.fullmatch(r"(\d{2,5})x(\d{2,5})", s)
    if not m:
        raise ValueError(f"formato desconocido «{s}»: usa {', '.join(FORMATS)} o AnchoxAlto (p. ej. 1280x720)")
    return int(m.group(1)), int(m.group(2))


def _even(x: float) -> int:
    return max(2, int(round(x / 2.0)) * 2)


@dataclass
class FormatPlan:
    src: Tuple[int, int]
    target: Tuple[int, int]
    fit: str
    scale: float          # factor from source to the (pre pad/crop) content size
    upscale: bool         # needs super-resolution (scale > 1)
    outscale: float       # what the AI step is asked for (== scale when upscaling)
    content: Tuple[int, int]
    vf_final: str         # ffmpeg filters that turn the (upscaled or original) frames into the exact target


def plan_format(src_w: int, src_h: int, target, fit: str = "fit", sharpen: str = "light", denoise: bool = False) -> FormatPlan:
    tw, th = (parse_format(target) if isinstance(target, str) else tuple(target))
    tw, th = _even(tw), _even(th)
    if fit == "fit":
        s = min(tw / src_w, th / src_h)
    elif fit in ("fill", "stretch"):
        s = max(tw / src_w, th / src_h)
    else:
        raise ValueError("fit: fit | fill | stretch")
    cw, ch = (tw, th) if fit == "stretch" else (_even(src_w * s), _even(src_h * s))
    chain = []
    if denoise:
        chain.append("hqdn3d=1.2:1.2:5:5")  # light spatial + temporal denoise: calms the flicker per-frame SR can add
    chain.append(f"scale={cw}:{ch}:flags=lanczos")
    if SHARPEN[sharpen] > 0:
        chain.append(f"unsharp=5:5:{SHARPEN[sharpen]}:5:5:0")
    if fit == "fit" and (cw, ch) != (tw, th):
        chain.append(f"pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2:black")
    if fit == "fill" and (cw, ch) != (tw, th):
        chain.append(f"crop={tw}:{th}")
    chain.append("setsar=1")
    return FormatPlan((src_w, src_h), (tw, th), fit, s, s > 1.0, s if s > 1.0 else 1.0, (cw, ch), ",".join(chain))


def estimate(frames: int, src_w: int, src_h: int, sec_per_mpix_frame: Optional[float] = None) -> Dict:
    """AI cost scales with the INPUT pixels of every frame (the x4 networks work at input resolution). Calibrate with a measured
    seconds-per-input-megapixel; nothing is assumed."""
    mp = src_w * src_h / 1e6
    return {"input_megapixels_per_frame": mp, "total_megapixel_frames": mp * frames,
            "gpu_seconds": mp * frames * sec_per_mpix_frame if sec_per_mpix_frame else None}


# ---- AI upscaler (Real-ESRGAN) ----------------------------------------------------------------------------------------
def _torchvision_shim():
    """basicsr 1.4.2 imports torchvision.transforms.functional_tensor, removed in torchvision 0.17: alias it before importing basicsr."""
    try:
        import torchvision.transforms.functional_tensor  # noqa: F401
    except ModuleNotFoundError:
        import torchvision.transforms.functional as F

        sys.modules["torchvision.transforms.functional_tensor"] = F


def realesrgan_available() -> bool:
    import importlib.util

    return all(importlib.util.find_spec(m) is not None for m in ("realesrgan", "basicsr", "torch", "cv2"))


class RealESRGANUpscaler:
    """RealESRGANer wrapper following the official inference script. Weights are NOT downloaded unless allow_download=True
    (they are fetched from the project's GitHub releases); otherwise put the .pth in `weights_dir`."""

    def __init__(self, model: str = "anime-video", tile: int = 0, half: bool = True, device: str = "cuda",
                 weights_dir: Optional[str] = None, allow_download: bool = False):
        if model not in MODELS:
            raise ValueError(f"modelo: {', '.join(MODELS)}")
        spec = MODELS[model]
        path = os.path.join(weights_dir or os.path.expanduser("~/.cache/hypercartoon/realesrgan"), spec["file"])
        url = f"{RELEASE}/{spec['tag']}/{spec['file']}"
        if not os.path.exists(path):
            if not allow_download:
                raise RuntimeError(f"falta el peso {spec['file']}: descárgalo de {url} en {os.path.dirname(path)} o usa allow_download=True")
            path = url
        _torchvision_shim()
        from realesrgan import RealESRGANer

        if spec["arch"] == "rrdb":
            from basicsr.archs.rrdbnet_arch import RRDBNet

            net = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=spec["num_block"], num_grow_ch=32, scale=4)
        else:
            from realesrgan.archs.srvgg_arch import SRVGGNetCompact

            net = SRVGGNetCompact(num_in_ch=3, num_out_ch=3, num_feat=64, num_conv=spec["num_conv"], upscale=4, act_type="prelu")
        self.up = RealESRGANer(scale=4, model_path=path, model=net, tile=tile, tile_pad=10, pre_pad=0, half=half and device != "cpu",
                               device=None if device == "cuda" else device)

    def upscale(self, frame_rgb: np.ndarray, outscale: float) -> np.ndarray:
        out, _ = self.up.enhance(frame_rgb[:, :, ::-1].copy(), outscale=outscale)  # the library works in BGR
        return out[:, :, ::-1].copy()


# ---- video ----------------------------------------------------------------------------------------------------------------
def _ffmpeg() -> str:
    from studio.audio import _ffmpeg as f

    return f()


def probe(path: str) -> Dict:
    import imageio

    r = imageio.get_reader(path, "ffmpeg")
    m = r.get_meta_data()
    r.close()
    return {"width": int(m["size"][0]), "height": int(m["size"][1]), "fps": float(m["fps"]), "duration": float(m.get("duration") or 0.0)}


def finish_video(src: str, dst: str, fmt: str = "fhd", fit: str = "fit", model: str = "anime-video", tile: int = 0, half: bool = True,
                 device: str = "cuda", sharpen: str = "light", denoise: bool = False, crf: int = 16, upscaler=None, use_ai: bool = True,
                 allow_download: bool = False, weights_dir: Optional[str] = None, progress: Optional[Callable] = None, dry: bool = False) -> Dict:
    """Sharpen + scale `src` to the delivery format. AI path when an upscaler is given / Real-ESRGAN is installed and the plan needs
    upscaling; otherwise one ffmpeg pass. Audio is kept. Returns a report (mode, plan, seconds)."""
    info = probe(src)
    plan = plan_format(info["width"], info["height"], fmt, fit, sharpen, denoise)
    ai = use_ai and plan.upscale and (upscaler is not None or realesrgan_available())
    rep = {"src": src, "dst": dst, "mode": "esrgan" if ai else "lanczos", "plan": asdict(plan), "fps": info["fps"], "model": model if ai else None}
    if dry:
        return rep
    t0 = time.time()
    os.makedirs(os.path.dirname(os.path.abspath(dst)) or ".", exist_ok=True)
    ff = _ffmpeg()
    enc = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", str(crf), "-preset", "medium", "-c:a", "aac", "-b:a", "192k"]
    if not ai:
        subprocess.run([ff, "-v", "error", "-y", "-i", src, "-vf", plan.vf_final, "-map", "0:v", "-map", "0:a?", *enc, dst], check=True)
        progress and progress(1.0)
        rep["seconds"] = time.time() - t0
        return rep

    import imageio

    up = upscaler or RealESRGANUpscaler(model, tile, half, device, weights_dir, allow_download)
    with tempfile.TemporaryDirectory() as tmp:
        mid = os.path.join(tmp, "sr.mp4")
        rd = imageio.get_reader(src, "ffmpeg")
        n = max(1, int(round(info["duration"] * info["fps"]))) if info["duration"] else None
        wr = imageio.get_writer(mid, fps=info["fps"], codec="libx264", pixelformat="yuv420p", macro_block_size=1,
                                ffmpeg_params=["-crf", "10", "-preset", "veryfast"])
        for i, frame in enumerate(rd):
            sr = up.upscale(np.asarray(frame), plan.outscale)
            h, w = sr.shape[:2]
            wr.append_data(sr[: h - h % 2, : w - w % 2])  # yuv420p needs even sides
            if progress and n:
                progress(min(0.95, (i + 1) / n))
        wr.close()
        rd.close()
        # the exact target format (resize/pad/crop/sharpen) + the original audio
        subprocess.run([ff, "-v", "error", "-y", "-i", mid, "-i", src, "-vf", plan.vf_final, "-map", "0:v", "-map", "1:a?", *enc, dst], check=True)
    progress and progress(1.0)
    rep["seconds"] = time.time() - t0
    return rep
