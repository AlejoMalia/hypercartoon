"""Run any diffusers video pipeline locally (Wan 2.2, HunyuanVideo 1.5, LTX-Video, CogVideoX, Mochi). Lazy: torch / diffusers are imported only
when an engine is loaded, so the rest of the studio runs without them. Nothing here talks to a paid service; the weights come from the
Hugging Face hub once (a download of several GB) and are then cached on disk.
Written against the public diffusers APIs and tested with stand-in pipelines only (no GPU / weights here)."""
from __future__ import annotations

from typing import Callable, List, Optional, Tuple

import os

import numpy as np

from studio.engines.registry import EngineSpec, disk_problem


def to_uint8(frames) -> np.ndarray:
    """diffusers returns PIL images, uint8 arrays or float arrays in [0, 1] -> [T, H, W, 3] uint8."""
    if isinstance(frames, np.ndarray):
        a = frames
    else:
        a = np.stack([np.asarray(f) for f in frames])
    if a.dtype != np.uint8:
        a = (np.clip(a, 0.0, 1.0) * 255).round().astype(np.uint8) if a.max() <= 1.0 + 1e-6 else np.clip(a, 0, 255).astype(np.uint8)
    return a


def _round(v: int, m: int = 32) -> int:
    return max(m, int(round(v / m)) * m)


class DiffusersEngine:
    def __init__(self, spec: EngineSpec, device: str = "auto", offload: bool = True, repo: Optional[str] = None, lora: Optional[str] = None,
                 factory: Optional[Callable] = None, call_extra: Optional[dict] = None, low_memory: bool = False):
        """factory(kind, spec) -> pipeline object, only for tests / custom loading; kind is 'base' or 'i2v'."""
        self.spec, self.device, self.offload, self.repo, self.lora, self.factory = spec, device, offload, repo, lora, factory
        self.low_memory = low_memory  # encode the prompt with the big text encoder first, free it, then load the video model (small GPUs / 16 GB laptops)
        self.call_extra = dict(call_extra or {})  # extra keyword arguments for every pipeline call (e.g. max_sequence_length)
        self.pipe = None
        self.i2v = None

    # ---- loading ------------------------------------------------------------------------------------------------------
    def _device(self) -> str:
        if self.device != "auto":
            return self.device
        try:
            import torch

            return "cuda" if torch.cuda.is_available() else "mps" if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available() else "cpu"
        except Exception:
            return "cpu"

    def _build(self, kind: str, skip: tuple = (), dtype: Optional[str] = None):
        if self.factory:
            return self.factory(kind, self.spec)
        if not self.spec.pipeline:
            raise RuntimeError(f"{self.spec.title} no está en diffusers: ejecútalo con su propio repositorio ({self.spec.repo})")
        try:
            import diffusers
            import torch
        except Exception as e:
            raise RuntimeError("faltan torch y diffusers: pip install torch git+https://github.com/huggingface/diffusers transformers accelerate sentencepiece ftfy") from e
        msg = disk_problem(self.spec, self.repo or "")
        if msg:  # never fill the disk half-way through a multi-GB download
            raise RuntimeError(msg)
        cls_name = self.spec.i2v_pipeline if kind == "i2v" else self.spec.pipeline
        cls = getattr(diffusers, cls_name, None)
        if cls is None:
            raise RuntimeError(f"tu versión de diffusers no tiene {cls_name}: actualiza con pip install -U git+https://github.com/huggingface/diffusers")
        repo = (self.spec.i2v_repo if kind == "i2v" else None) or self.repo or self.spec.repo
        pipe = cls.from_pretrained(repo, torch_dtype=getattr(torch, dtype or self.spec.dtype), **{k: None for k in skip})
        if self.lora:  # a style LoRA trained on the learned show (docs/engines.md)
            pipe.load_lora_weights(self.lora)
        dev = self._device()
        if dev == "mps":
            os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")  # a few ops are missing on Apple GPUs: fall back to CPU for those
        if dev == "mps":  # Apple GPUs have no float64: some models register float64 buffers (positional tables) that cannot be moved
            import torch as _t

            for comp in getattr(pipe, "components", {}).values():
                for m in (comp.modules() if hasattr(comp, "modules") else []):
                    for n, b in list(m._buffers.items()):
                        if b is not None and b.dtype == _t.float64:
                            m._buffers[n] = b.float()
                    for n, p_ in list(m._parameters.items()):
                        if p_ is not None and p_.dtype == _t.float64:
                            p_.data = p_.data.float()
        if skip == ("transformer", "vae"):  # prompt-encoding stage: stays on CPU, it only runs once
            return pipe
        if dev == "cuda" and self.offload:
            pipe.enable_model_cpu_offload()
        else:
            pipe.to(dev)
        for fn in ("enable_tiling", "enable_slicing"):
            try:
                getattr(pipe.vae, fn)()
            except Exception:
                pass
        return pipe

    def load(self) -> "DiffusersEngine":
        if self.pipe is None and not self.low_memory:
            self.pipe = self._build("base")
        return self

    def _encode_prompt(self, prompt: str, negative: str, text_dtype: str = "bfloat16") -> dict:
        """Low-memory stage 1: only the tokenizer + text encoder are loaded; the embeddings come back as CPU tensors and the encoder is freed."""
        import gc

        import torch

        enc = self._build("base", skip=("transformer", "vae"), dtype=text_dtype)
        with torch.no_grad():
            out = enc.encode_prompt(prompt=prompt, negative_prompt=negative or None, do_classifier_free_guidance=True, device="cpu")
        del enc
        gc.collect()
        names = ("prompt_embeds", "negative_prompt_embeds") if len(out) == 2 else ("prompt_embeds", "prompt_attention_mask", "negative_prompt_embeds", "negative_prompt_attention_mask")
        return {n: t.cpu() for n, t in zip(names, out)}

    def unload(self) -> None:
        self.pipe = self.i2v = None
        try:
            import torch

            torch.cuda.empty_cache()
        except Exception:
            pass

    # ---- generating --------------------------------------------------------------------------------------------------------
    def kwargs(self, prompt: str, negative: str, seconds: float, seed: int, steps: Optional[int], guidance: Optional[float],
               size: Optional[Tuple[int, int]]) -> dict:
        s = self.spec
        w, h = size or s.size
        kw = {"prompt": prompt, "num_frames": s.frames_for(seconds), "height": _round(h), "width": _round(w), "num_inference_steps": steps or s.steps}
        if not s.guider:
            kw["guidance_scale"] = guidance if guidance is not None else s.guidance
        if negative and s.negative:
            kw["negative_prompt"] = negative
        try:
            import torch

            kw["generator"] = torch.Generator(device="cpu").manual_seed(int(seed))
        except Exception:
            pass
        return kw

    def _free_after_last_step(self, n_steps: int):
        """Low memory: when the last denoising step is done the video model is no longer needed — move it off the GPU before the VAE decode,
        which is the memory peak on small GPUs."""
        def cb(pipe, i, t, kwargs):
            if i == n_steps - 1:
                try:
                    import gc

                    import torch

                    pipe.transformer.to("cpu")
                    gc.collect()
                    for b in (getattr(torch, "mps", None), getattr(torch, "cuda", None)):
                        if b is not None and hasattr(b, "empty_cache"):
                            try:
                                b.empty_cache()
                            except Exception:
                                pass
                except Exception:
                    pass
            return kwargs

        return cb

    def generate(self, prompt: str, negative: str = "", seconds: float = 3.0, seed: int = 0, steps: Optional[int] = None,
                 guidance: Optional[float] = None, size: Optional[Tuple[int, int]] = None, image=None) -> np.ndarray:
        """-> uint8 frames [T, H, W, 3]. `image` (PIL / array): start the clip from this frame (continuing a scene), if the engine supports it."""
        self.load()
        kw = self.kwargs(prompt, negative, seconds, seed, steps, guidance, size)
        if self.low_memory:
            if self.spec.guider:
                raise RuntimeError(f"{self.spec.title} no admite el modo de poca memoria (guía por guider)")
            emb = self._encode_prompt(prompt, negative)
            kw.pop("prompt")
            kw.pop("negative_prompt", None)
            kw.update(emb)
            if self.pipe is None:
                self.pipe = self._build("base", skip=("text_encoder", "tokenizer"))
            kw = {k: (v.to(self._device(), self.pipe.dtype) if hasattr(v, "to") and k.endswith("embeds") else v.to(self._device()) if hasattr(v, "to") else v) for k, v in kw.items()}
        pipe = self.pipe
        if self.low_memory:
            kw["callback_on_step_end"] = self._free_after_last_step(kw["num_inference_steps"])
        if self.spec.guider and guidance is not None and hasattr(pipe, "guider"):
            pipe.guider = pipe.guider.new(guidance_scale=guidance)  # HunyuanVideo 1.5 takes guidance from its guider
        if image is not None and self.spec.i2v_pipeline:
            if self.i2v is None:
                self.i2v = self._build("i2v")
            pipe = self.i2v
            from PIL import Image

            kw["image"] = image if not isinstance(image, np.ndarray) else Image.fromarray(image)
        out = pipe(**{**kw, **self.call_extra})
        return to_uint8(out.frames[0])
