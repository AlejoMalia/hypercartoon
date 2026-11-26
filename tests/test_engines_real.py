"""The engine wrapper against REAL diffusers pipeline classes with tiny random weights (CPU). Needs torch, diffusers, peft, transformers and
network access to the Hugging Face hub for a few KB-to-MB test repositories; skipped otherwise. This checks call arguments, frame rules, guidance
conventions, LoRA training / loading and image conditioning, not video quality."""
import os

import numpy as np
import pytest

torch = pytest.importorskip("torch")
diffusers = pytest.importorskip("diffusers")
pytest.importorskip("peft")
transformers = pytest.importorskip("transformers")

from studio.engines.diffusers_engine import DiffusersEngine  # noqa: E402
from studio.engines.registry import get  # noqa: E402

try:
    from huggingface_hub import snapshot_download

    snapshot_download("hf-internal-testing/tiny-random-t5")
except Exception:  # offline
    pytest.skip("needs the Hugging Face hub", allow_module_level=True)

LTX = "katuni4ka/tiny-random-ltx-video"
WAN = "pruna-test/wan-t2v-tiny-random"


def _t5():
    return (transformers.T5EncoderModel.from_pretrained("hf-internal-testing/tiny-random-t5"),
            transformers.AutoTokenizer.from_pretrained("hf-internal-testing/tiny-random-t5"))


def _cogvideox():
    from diffusers import AutoencoderKLCogVideoX, CogVideoXDDIMScheduler, CogVideoXPipeline, CogVideoXTransformer3DModel

    torch.manual_seed(0)
    te, tok = _t5()
    tr = CogVideoXTransformer3DModel(num_attention_heads=4, attention_head_dim=16, in_channels=4, out_channels=4, time_embed_dim=2, text_embed_dim=32, num_layers=1,
                                     sample_width=16, sample_height=16, sample_frames=9, patch_size=2, temporal_compression_ratio=4, max_text_seq_length=16)
    vae = AutoencoderKLCogVideoX(in_channels=3, out_channels=3, down_block_types=("CogVideoXDownBlock3D",) * 4, up_block_types=("CogVideoXUpBlock3D",) * 4,
                                 block_out_channels=(8, 8, 8, 8), latent_channels=4, layers_per_block=1, norm_num_groups=2, temporal_compression_ratio=4)
    return CogVideoXPipeline(tokenizer=tok, text_encoder=te, vae=vae, transformer=tr, scheduler=CogVideoXDDIMScheduler())


def _mochi():
    from diffusers import AutoencoderKLMochi, FlowMatchEulerDiscreteScheduler, MochiPipeline, MochiTransformer3DModel

    torch.manual_seed(0)
    te, tok = _t5()
    tr = MochiTransformer3DModel(patch_size=2, num_attention_heads=2, attention_head_dim=8, num_layers=2, pooled_projection_dim=16, in_channels=12, out_channels=None,
                                 qk_norm="rms_norm", text_embed_dim=32, time_embed_dim=4, activation_fn="swiglu", max_sequence_length=16)
    vae = AutoencoderKLMochi(latent_channels=12, out_channels=3, encoder_block_out_channels=(32, 32, 32, 32), decoder_block_out_channels=(32, 32, 32, 32),
                             layers_per_block=(1, 1, 1, 1, 1), temporal_expansions=(1, 2, 3), spatial_expansions=(2, 2, 2),
                             add_attention_block=(False, False, False, False, False), scaling_factor=1.0)
    return MochiPipeline(scheduler=FlowMatchEulerDiscreteScheduler(), vae=vae, text_encoder=te, tokenizer=tok, transformer=tr)


def _hunyuan15():
    from diffusers import HunyuanVideo15Pipeline
    from diffusers.guiders import ClassifierFreeGuidance

    return HunyuanVideo15Pipeline.from_pretrained(
        "akshan-main/tiny-hunyuanvideo1_5-modular-pipe", tokenizer=transformers.AutoTokenizer.from_pretrained("Qwen/Qwen2.5-VL-3B-Instruct"),
        tokenizer_2=transformers.ByT5Tokenizer.from_pretrained("google/byt5-small"), guider=ClassifierFreeGuidance(guidance_scale=6.0))


def _gen(eid, repo=None, factory=None, **kw):
    e = DiffusersEngine(get(eid), device="cpu", offload=False, repo=repo, factory=factory, call_extra=kw.pop("call_extra", None))
    return e, e.generate("a red fox in a kitchen", kw.pop("negative", "text, logo"), seconds=kw.pop("seconds", 1.0), seed=1, steps=2, size=kw.pop("size", (64, 64)), **kw)


def test_ltx_real_pipeline_class():
    e, fr = _gen("ltx-video", LTX)
    assert fr.dtype == np.uint8 and fr.shape == (17, 64, 64, 3) and type(e.pipe).__name__ == "LTXPipeline"


def test_wan_real_pipeline_class():
    e, fr = _gen("wan22-ti2v-5b", WAN, seconds=0.2)           # the smallest valid clip: Wan's 3D VAE is slow on CPU even with tiny weights
    assert fr.dtype == np.uint8 and fr.shape[1:] == (64, 64, 3) and (fr.shape[0] - 1) % 4 == 0 and type(e.pipe).__name__ == "WanPipeline"


def test_cogvideox_real_pipeline_class():
    e, fr = _gen("cogvideox-2b", factory=lambda k, s: _cogvideox(), seconds=1.25, size=(128, 128), call_extra={"max_sequence_length": 16})
    assert fr.shape == (9, 128, 128, 3) and type(e.pipe).__name__ == "CogVideoXPipeline"


def test_mochi_real_pipeline_class():
    e, fr = _gen("mochi-1", factory=lambda k, s: _mochi())
    assert fr.dtype == np.uint8 and (fr.shape[0] - 1) % 6 == 0 and type(e.pipe).__name__ == "MochiPipeline"


def test_hunyuan15_real_pipeline_class_takes_guidance_from_its_guider():
    e, fr = _gen("hunyuan-video-1.5", factory=lambda k, s: _hunyuan15(), seconds=0.5, guidance=5.0, negative="")
    assert fr.shape[1:] == (64, 64, 3) and e.pipe.guider.guidance_scale == 5.0 and type(e.pipe).__name__ == "HunyuanVideo15Pipeline"


def test_ltx_image_to_video_continues_from_the_last_frame():
    from diffusers import LTXImageToVideoPipeline

    base = DiffusersEngine(get("ltx-video"), device="cpu", offload=False, repo=LTX).load()
    e = DiffusersEngine(get("ltx-video"), device="cpu", factory=lambda kind, spec: base.pipe if kind == "base" else LTXImageToVideoPipeline(**base.pipe.components))
    first = e.generate("a fox", seconds=1.0, seed=1, steps=2, size=(64, 64))
    nxt = e.generate("a fox", seconds=1.0, seed=2, steps=2, size=(64, 64), image=first[-1])
    assert type(e.i2v).__name__ == "LTXImageToVideoPipeline" and nxt.shape == first.shape


def test_lora_trains_on_the_exported_set_and_changes_the_render(tmp_path):
    import imageio

    from studio.engines.train_lora import train_ltx_lora

    d = tmp_path / "set"
    (d / "videos").mkdir(parents=True)
    files, prompts = [], []
    for i in range(4):
        w = imageio.get_writer(str(d / "videos" / f"s{i}.mp4"), fps=8, macro_block_size=1)
        for t in range(9):
            f = np.zeros((64, 64, 3), np.uint8)
            f[:] = (230, 200, 40)
            f[10 + t : 30 + t, 10 + 3 * t : 30 + 3 * t] = (40, 60, 200 + 10 * i)
            w.append_data(f)
        w.close()
        files.append(f"videos/s{i}.mp4")
        prompts.append(f"toonshow animation style. a blue figure runs on a yellow floor, shot {i}")
    (d / "videos.txt").write_text("\n".join(files) + "\n")
    (d / "prompt.txt").write_text("\n".join(prompts) + "\n")
    logs = []
    r = train_ltx_lora(str(d), str(tmp_path / "lora"), repo=LTX, steps=30, rank=4, lr=5e-3, size=(64, 64), frames=9, fps=8, device="cpu", dtype="float32", log=logs.append)
    assert os.path.exists(r["lora"]) and r["samples"] == 4 and len(r["losses"]) == 30
    assert np.mean(r["losses"][-5:]) < np.mean(r["losses"][:5])                 # it learns
    base = DiffusersEngine(get("ltx-video"), device="cpu", offload=False, repo=LTX).generate("a blue figure runs", "", seconds=1.0, seed=3, steps=2, size=(64, 64))
    tuned_e = DiffusersEngine(get("ltx-video"), device="cpu", offload=False, repo=LTX, lora=str(tmp_path / "lora"))
    tuned = tuned_e.generate("a blue figure runs", "", seconds=1.0, seed=3, steps=2, size=(64, 64))
    assert tuned_e.pipe.get_active_adapters() and np.abs(base.astype(int) - tuned.astype(int)).mean() > 1.0


def test_render_episode_with_a_real_pipeline(tmp_path):
    from studio.engines import render as RD

    ep = tmp_path / "ep"
    ep.mkdir()
    segs = [{"text": "a fox in a kitchen, cartoon style", "requires_scene_transition": False, "neg_text": "text, logo"},
            {"text": "a night street, cartoon style<end_scene>", "requires_scene_transition": True, "neg_text": "text"}]
    open(ep / "prompts.jsonl", "w").write(__import__("json").dumps(segs) + "\n")
    e = DiffusersEngine(get("ltx-video"), device="cpu", offload=False, repo=LTX)
    rep = RD.render_episode(str(ep), e, size_out=(96, 64), fps_out=8, steps=2, seed=0)
    assert len(rep["clips"]) == 2 and os.path.getsize(rep["videos"][0]) > 1000
