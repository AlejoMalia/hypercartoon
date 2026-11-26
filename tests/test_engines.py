import json
import os
import wave

import numpy as np
import pytest
from PIL import Image

from studio.engines import hardware as HW
from studio.engines import lora as LO
from studio.engines import render as RD
from studio.engines.diffusers_engine import DiffusersEngine, to_uint8
from studio.engines.registry import ENGINES, PREFERENCE, fits, get


# ---- registry and hardware ----------------------------------------------------------------------------------------------------
def test_frame_counts_follow_each_models_rule():
    ltx, wan, cog = get("ltx-video"), get("wan22-ti2v-5b"), get("cogvideox-2b")
    assert ltx.frames_for(3.0) == 65 and (ltx.frames_for(3.0) - 1) % 8 == 0           # 8k+1
    assert wan.frames_for(3.0) == 69 and (wan.frames_for(3.0) - 1) % 4 == 0           # 4k+1
    assert cog.frames_for(100.0) == 49 and wan.frames_for(100.0) == 121               # capped at the model's limit
    assert all(e.frames_for(0.1) >= 2 for e in ENGINES.values())
    assert wan.max_seconds == pytest.approx(121 / 24)


def test_every_engine_names_a_licence_and_a_repo():
    for e in ENGINES.values():
        assert e.license and e.repo and e.commercial
    assert set(PREFERENCE) <= set(ENGINES)
    with pytest.raises(KeyError, match="disponibles"):
        get("nope")


def test_fit_and_recommendation_by_hardware():
    cpu = {"device": "cpu", "vram_gb": 0, "ram_gb": 16}
    g12 = {"device": "cuda", "vram_gb": 12, "ram_gb": 32}
    g24 = {"device": "cuda", "vram_gb": 24, "ram_gb": 64}
    mac = {"device": "mps", "vram_gb": 0, "ram_gb": 64}
    assert all(fits(e, cpu) == "no" for e in ENGINES.values())
    assert fits(get("ltx-video"), g12) == "offload" and fits(get("wan22-ti2v-5b"), g12) == "offload" and fits(get("mochi-1"), g12) == "no"
    assert fits(get("wan22-ti2v-5b"), g24) == "ok" and fits(get("mochi-1"), g24) == "offload"
    assert fits(get("ltx-video"), mac) == "ok"                                          # 60 % of 64 GB unified memory
    rec = HW.recommend(g24)
    assert rec[0]["id"] == "wan22-ti2v-5b" and rec[0]["fit"] == "ok"                    # permissive licence + modern quality first
    assert rec[-1]["fit"] == "no"
    assert any("GPU" in l for l in HW.advice_es({"device": "cpu", "torch": None, "diffusers": None}))


def test_detect_works_without_torch(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "torch", None)
    hw = HW.detect()
    assert hw["device"] in ("cpu",) and hw["torch"] is None and "ram_gb" in hw


# ---- the diffusers wrapper, with stand-in pipelines -----------------------------------------------------------------------------
class Out:
    def __init__(self, frames):
        self.frames = [frames]


class FakePipe:
    def __init__(self, kind="base", fmt="pil"):
        self.calls, self.kind, self.fmt = [], kind, fmt
        self.guider = type("G", (), {"new": lambda s, guidance_scale: setattr(self, "g", guidance_scale) or s})()

    def __call__(self, **kw):
        self.calls.append(kw)
        n, h, w = kw["num_frames"], kw["height"], kw["width"]
        arr = np.full((n, h, w, 3), 90 + 40 * (self.kind == "i2v"), np.uint8)
        arr[:, :, : w // 2, 0] = 220
        if self.fmt == "pil":
            return Out([Image.fromarray(a) for a in arr])
        return Out(arr.astype(np.float32) / 255.0)


def _engine(eid, **kw):
    pipes = {}

    def factory(kind, spec):
        pipes[kind] = FakePipe(kind, **kw)
        return pipes[kind]

    e = DiffusersEngine(get(eid), factory=factory)
    return e, pipes


def test_to_uint8_accepts_pil_float_and_uint8():
    a = np.random.default_rng(0).integers(0, 255, (3, 8, 8, 3), dtype=np.uint8)
    assert np.array_equal(to_uint8([Image.fromarray(x) for x in a]), a)
    assert np.array_equal(to_uint8(a), a)
    assert np.abs(to_uint8(a.astype(np.float32) / 255).astype(int) - a.astype(int)).max() <= 1


def test_call_arguments_respect_each_models_conventions():
    e, p = _engine("wan22-ti2v-5b")
    fr = e.generate("a fox", "text, logo", seconds=3.0, seed=3, steps=10)
    kw = p["base"].calls[0]
    assert kw["num_frames"] == 69 and kw["width"] % 32 == 0 and kw["height"] % 32 == 0 and kw["guidance_scale"] == 5.0
    assert kw["negative_prompt"] == "text, logo" and kw["num_inference_steps"] == 10
    assert fr.dtype == np.uint8 and fr.shape == (69, kw["height"], kw["width"], 3)
    e, p = _engine("hunyuan-video-1.5")                                                # guidance goes through the guider, no negative prompt
    e.generate("a fox", "text", seconds=3.0, guidance=7.5)
    kw = p["base"].calls[0]
    assert "guidance_scale" not in kw and "negative_prompt" not in kw and p["base"].g == 7.5
    e, p = _engine("ltx-video", fmt="np")
    assert e.generate("a fox", seconds=3.0).shape[0] == 65


def test_image_conditioning_uses_the_i2v_pipeline_only_when_the_engine_has_one():
    img = np.zeros((480, 704, 3), np.uint8)
    e, p = _engine("ltx-video")
    fr = e.generate("a fox", seconds=3.0, image=img)
    assert "image" in p["i2v"].calls[0] and fr.mean() > 120
    e, p = _engine("wan22-ti2v-5b")
    e.generate("a fox", seconds=3.0, image=img)
    assert "i2v" not in p and "image" not in p["base"].calls[0]


def test_missing_torch_or_diffusers_has_a_clear_message(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "diffusers", None)
    with pytest.raises(RuntimeError, match="faltan torch y diffusers"):
        DiffusersEngine(get("ltx-video")).load()
    with pytest.raises(RuntimeError, match="propio repositorio"):
        DiffusersEngine(get("longcat-video")).load()


# ---- planning and rendering an episode ---------------------------------------------------------------------------------------------
def _episode(tmp_path, scenes=((4, "a fox in a kitchen"), (1, "a night street"))):
    ep = tmp_path / "ep"
    (ep / "sound").mkdir(parents=True)
    segs = []
    for n, text in scenes:
        for k in range(n):
            segs.append({"text": ("<start_scene>" if k == 0 and segs else "") + f"{text}, cartoon style" + ("<end_scene>" if k == n - 1 else ""),
                         "requires_scene_transition": k == 0 and bool(segs), "neg_text": "text, subtitles, logo"})
    open(ep / "prompts.jsonl", "w").write(json.dumps(segs) + "\n")
    with wave.open(str(ep / "sound" / "video_000.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes((np.sin(np.arange(16000 * 15) / 20) * 8000).astype(np.int16).tobytes())
    return str(ep)


def test_scenes_are_split_at_transitions_and_chunked_to_the_engines_limit(tmp_path):
    ep = _episode(tmp_path)
    videos = RD.load_videos(os.path.join(ep, "prompts.jsonl"))
    ltx = RD.plan_clips(videos, get("ltx-video"))                  # 161/24 = 6.7 s -> two 3 s segments per clip
    assert [(c["scene"], c["chunk"], c["segments"], c["continues"]) for c in ltx] == [(0, 0, 2, False), (0, 1, 2, True), (1, 0, 1, False)]
    assert "<" not in ltx[0]["prompt"] and ltx[0]["negative"].startswith("text")
    assert RD.estimate(ltx, get("ltx-video"))["continued_from_last_frame"] == 1
    wan = RD.plan_clips(videos, get("wan22-ti2v-5b"))              # 5 s: one segment per clip
    assert len(wan) == 5
    e = RD.estimate(wan, get("wan22-ti2v-5b"), steps=20)
    assert e["hard_cuts_inside_scenes"] == 3 and e["denoising_steps_total"] == 100   # no i2v pipeline: the report says so


def test_render_episode_end_to_end_resumable_with_audio(tmp_path):
    ep = _episode(tmp_path)
    e, pipes = _engine("ltx-video")
    got = []
    rep = RD.render_episode(ep, e, size_out=(320, 192), fps_out=12, progress=lambda f, d="": got.append(d), steps=2)
    assert len(rep["videos"]) == 1 and os.path.getsize(rep["videos"][0]) > 1000 and len(got) == 3
    # the second chunk of scene 0 continues from the last frame of the first one (image-to-video), the others do not
    assert len(pipes["base"].calls) == 2 and len(pipes["i2v"].calls) == 1 and "image" in pipes["i2v"].calls[0]
    import imageio

    r = imageio.get_reader(rep["videos"][0], "ffmpeg")
    meta = r.get_meta_data()
    r.close()
    assert meta["size"] == (320, 192)
    from studio.audio import load_audio

    assert len(load_audio(rep["videos"][0], 16000)) > 16000                           # the regenerated dialogue is on the video
    n_before = len(pipes["base"].calls) + len(pipes["i2v"].calls)
    RD.render_episode(ep, e, size_out=(320, 192), steps=2)
    assert len(pipes["base"].calls) + len(pipes["i2v"].calls) == n_before            # finished clips are kept
    assert json.load(open(os.path.join(ep, "video", "ltx-video", "render.json")))["engine"] == "ltx-video"


def test_dry_run_loads_nothing(tmp_path):
    ep = _episode(tmp_path)
    e, pipes = _engine("wan22-ti2v-5b")
    rep = RD.render_episode(ep, e, dry=True)
    assert rep["estimate"]["clips"] == 5 and not pipes and e.pipe is None
    with pytest.raises(FileNotFoundError, match="create"):
        RD.render_episode(str(tmp_path / "nothing"), e, dry=True)


# ---- teaching a third-party engine your show ------------------------------------------------------------------------------------------
def test_export_lora_dataset_from_the_learned_project(tmp_path):
    from test_layers import _clip

    from studio import learning as L
    from studio import pipeline as PL
    from studio.dataset import build_training_set

    show = tmp_path / "Show" / "S01"
    show.mkdir(parents=True)
    _clip(str(show / "E01.mp4"), secs=12)
    ws = str(tmp_path / "ws")
    ctx = {"input": str(tmp_path / "Show"), "ws": ws, "device": "cpu", "workers": 1, "vision": False}
    PL.run([p for p in L.LEARNING_PHASES if p.key in ("sources", "scan", "corpus", "profile", "overlays")], ctx)
    build_training_set(ws, [3, 9], with_control=False)
    out = str(tmp_path / "lora")
    r = LO.export_dataset(ws, out, get("ltx-video"))
    assert r["samples"] >= 1
    prompts = open(os.path.join(out, "prompt.txt")).read().splitlines()
    files = open(os.path.join(out, "videos.txt")).read().splitlines()
    assert len(prompts) == len(files) == r["samples"] and all(f.startswith("videos/") and f.endswith(".mp4") for f in files)
    assert all("animation style" in p for p in prompts) and not any(w in " ".join(prompts).lower() for w in ("subtitle", "logo", "watermark"))
    sh = open(os.path.join(out, "make_videos.sh")).read()
    assert "scale=704:480" in sh and "-r 24" in sh and sh.count("ffmpeg") == r["samples"]
    assert "finetrainers" in open(os.path.join(out, "LEEME.md")).read()


def test_cli_engines_and_render_dry_and_native(tmp_path, capsys):
    from studio import cli

    ws = tmp_path / "ws"
    ep = ws / "episodes" / "episodio_01"
    os.makedirs(ep)
    os.rename(_episode(tmp_path), str(ep / "tmp"))
    for f in os.listdir(ep / "tmp"):
        os.rename(ep / "tmp" / f, ep / f)
    json.dump({"generate_video_commands": ["torchrun sample.py --x"]}, open(ep / "episode.json", "w"))
    cli.main(["--workdir", str(ws), "engines"])
    out = capsys.readouterr().out
    assert "hypercartoon" in out and "wan22-ti2v-5b" in out and "Sin GPU" in out
    cli.main(["--workdir", str(ws), "render", "--engine", "ltx-video", "--dry"])
    assert "3 clips" in capsys.readouterr().out
    cli.main(["--workdir", str(ws), "render", "--engine", "hypercartoon"])
    assert "torchrun sample.py --x" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="ningún motor"):
        cli.main(["--workdir", str(ws), "render", "--engine", "auto"])
