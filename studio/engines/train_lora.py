"""Teach LTX-Video your show: a small LoRA trainer (flow matching, transformer LoRA, the same recipe the diffusers trainers use) that
reads the `prompt.txt` / `videos.txt` set written by `studio export-lora`. The text embeddings and video latents are computed once and
cached, then only the LoRA weights are trained; the result loads with `studio render --lora`.

Verified end to end on a tiny random LTX pipeline (loss goes down, the saved LoRA changes the output); a real run needs the real weights and
a GPU. Other engines: train with https://github.com/huggingface/finetrainers on the same files."""
from __future__ import annotations

import os
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np


def read_set(data_dir: str) -> List[Tuple[str, str]]:
    prompts = [l.rstrip("\n") for l in open(os.path.join(data_dir, "prompt.txt"), encoding="utf-8") if l.strip()]
    files = [l.strip() for l in open(os.path.join(data_dir, "videos.txt"), encoding="utf-8") if l.strip()]
    if len(prompts) != len(files):
        raise ValueError(f"prompt.txt ({len(prompts)}) y videos.txt ({len(files)}) no coinciden")
    return [(os.path.join(data_dir, f), p) for f, p in zip(files, prompts) if os.path.exists(os.path.join(data_dir, f))]


def load_video(path: str, size: Tuple[int, int], frames: int) -> np.ndarray:
    """-> float32 [3, T, H, W] in [-1, 1], exactly `frames` frames (the clip is trimmed / its last frame repeated)."""
    import imageio

    r = imageio.get_reader(path, "ffmpeg")
    out = []
    for f in r:
        out.append(np.asarray(f))
        if len(out) >= frames:
            break
    r.close()
    while len(out) < frames:
        out.append(out[-1])
    from PIL import Image

    arr = np.stack([np.asarray(Image.fromarray(f).resize(size, Image.BICUBIC)) for f in out]).astype(np.float32) / 127.5 - 1.0
    return arr.transpose(3, 0, 1, 2)


def train_ltx_lora(data_dir: str, out_dir: str, repo: str = "Lightricks/LTX-Video", steps: int = 200, rank: int = 16, lr: float = 1e-4,
                   size: Tuple[int, int] = (704, 480), frames: int = 49, fps: int = 24, device: str = "cuda", dtype: str = "bfloat16",
                   seed: int = 0, log: Callable = print, pipe=None) -> Dict:
    import torch
    from diffusers import LTXPipeline
    from peft import LoraConfig
    from peft.utils import get_peft_model_state_dict

    data = read_set(data_dir)
    if not data:
        raise ValueError(f"sin muestras en {data_dir} (¿ejecutaste make_videos.sh?)")
    dt = getattr(torch, dtype)
    pipe = pipe or LTXPipeline.from_pretrained(repo, torch_dtype=dt)
    tr, vae = pipe.transformer, pipe.vae
    g = torch.Generator(device="cpu").manual_seed(seed)
    # 1. cache text embeddings and normalised, packed video latents (the big encoders are then not needed on the GPU)
    pipe.text_encoder.to(device)
    vae.to(device)
    cache = []
    with torch.no_grad():
        for path, prompt in data:
            v = torch.from_numpy(load_video(path, size, frames))[None].to(device, vae.dtype)
            lat = vae.encode(v).latent_dist.sample(generator=g)
            lat = pipe._normalize_latents(lat, vae.latents_mean, vae.latents_std, vae.config.scaling_factor)
            nf, nh, nw = lat.shape[2:]
            packed = pipe._pack_latents(lat, pipe.transformer_spatial_patch_size, pipe.transformer_temporal_patch_size)
            pe, pm, _, _ = pipe.encode_prompt(prompt, do_classifier_free_guidance=False, device=device)
            cache.append((packed.float().cpu(), pe.cpu(), pm.cpu(), (nf, nh, nw)))
    pipe.text_encoder.to("cpu")
    vae.to("cpu")
    # 2. LoRA on the attention projections of the transformer
    for p in tr.parameters():
        p.requires_grad_(False)
    tr.add_adapter(LoraConfig(r=rank, lora_alpha=rank, init_lora_weights=True, target_modules=["to_k", "to_q", "to_v", "to_out.0"]))
    tr.to(device)
    params = [p for p in tr.parameters() if p.requires_grad]
    for p in params:
        p.data = p.data.float()  # LoRA weights train in fp32
    opt = torch.optim.AdamW(params, lr=lr, weight_decay=1e-2)
    rope = (pipe.vae_temporal_compression_ratio / fps, pipe.vae_spatial_compression_ratio, pipe.vae_spatial_compression_ratio)
    losses: List[float] = []
    tr.train()
    for step in range(steps):
        x0, pe, pm, (nf, nh, nw) = cache[int(torch.randint(len(cache), (1,), generator=g))]
        x0, pe, pm = x0.to(device), pe.to(device, dt), pm.to(device)
        eps = torch.randn(x0.shape, generator=g).to(device)
        sigma = torch.sigmoid(torch.randn(1, generator=g)).to(device)           # logit-normal noise level
        xt = (1 - sigma) * x0 + sigma * eps
        pred = tr(hidden_states=xt.to(dt), encoder_hidden_states=pe, timestep=(sigma * 1000).expand(1).to(dt), encoder_attention_mask=pm,
                  num_frames=nf, height=nh, width=nw, rope_interpolation_scale=rope, return_dict=False)[0]
        loss = torch.nn.functional.mse_loss(pred.float(), eps - x0)               # flow-matching velocity target
        loss.backward()
        torch.nn.utils.clip_grad_norm_(params, 1.0)
        opt.step()
        opt.zero_grad(set_to_none=True)
        losses.append(float(loss))
        if step % max(1, steps // 10) == 0 or step == steps - 1:
            log(f"  paso {step + 1}/{steps}  pérdida {losses[-1]:.4f}")
    os.makedirs(out_dir, exist_ok=True)
    LTXPipeline.save_lora_weights(out_dir, transformer_lora_layers=get_peft_model_state_dict(tr))
    return {"losses": losses, "lora": os.path.join(out_dir, "pytorch_lora_weights.safetensors"), "samples": len(data), "steps": steps, "rank": rank}
