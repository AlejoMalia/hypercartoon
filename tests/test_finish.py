import os
import re
import subprocess

import imageio
import numpy as np
import pytest

from studio import finish as FN
from studio import postprocess as PP
from studio.audio import _ffmpeg
from studio.sound.mix import write_wav


def test_format_presets_and_parsing():
    assert FN.parse_format("fhd") == (1920, 1080) and FN.parse_format("1280X720") == (1280, 720) and FN.parse_format("4K") == (3840, 2160)
    for bad in ("hdd", "100", "12x"):
        with pytest.raises(ValueError):
            FN.parse_format(bad)


def test_fit_pillarboxes_a_3_2_source_into_16_9():
    p = FN.plan_format(720, 480, "fhd", "fit")
    assert p.scale == pytest.approx(2.25) and p.content == (1620, 1080) and p.target == (1920, 1080) and p.upscale
    assert "scale=1620:1080:flags=lanczos" in p.vf_final and "pad=1920:1080:(ow-iw)/2:(oh-ih)/2" in p.vf_final and "crop" not in p.vf_final
    assert p.outscale == pytest.approx(2.25)


def test_fill_crops_and_stretch_distorts_and_exact_match_needs_no_pad():
    f = FN.plan_format(720, 480, "fhd", "fill")
    assert f.scale == pytest.approx(1920 / 720) and f.content == (1920, 1280) and "crop=1920:1080" in f.vf_final and "pad" not in f.vf_final
    s = FN.plan_format(720, 480, "fhd", "stretch")
    assert s.content == (1920, 1080) and "pad" not in s.vf_final and "crop" not in s.vf_final
    e = FN.plan_format(1920, 1080, "fhd", "fit")
    assert e.scale == 1.0 and not e.upscale and "pad" not in e.vf_final


def test_beyond_4x_and_downscale_and_odd_sizes():
    big = FN.plan_format(720, 480, "4k", "fit")
    assert big.scale == pytest.approx(4.5) and big.outscale == pytest.approx(4.5) and big.content == (3240, 2160)  # AI x4 then a small final resize
    down = FN.plan_format(3840, 2160, "fhd", "fit")
    assert not down.upscale and down.outscale == 1.0 and "scale=1920:1080" in down.vf_final
    odd = FN.plan_format(333, 201, (1001, 601), "fit")
    assert odd.target[0] % 2 == 0 and odd.target[1] % 2 == 0 and all(x % 2 == 0 for x in odd.content)  # h264 yuv420p needs even sizes


def test_sharpen_and_denoise_enter_the_filter_chain_in_order():
    off = FN.plan_format(720, 480, "hd", "fit", sharpen="off", denoise=False).vf_final
    strong = FN.plan_format(720, 480, "hd", "fit", sharpen="strong", denoise=True).vf_final
    assert "unsharp" not in off and "hqdn3d" not in off
    assert strong.index("hqdn3d") < strong.index("scale=") < strong.index("unsharp=5:5:1.3") and strong.endswith("setsar=1")


def test_model_table_and_cost_formula_and_missing_weights():
    assert set(FN.MODELS) == {"anime-video", "anime6b", "general", "x4plus"} and FN.MODELS["anime6b"]["num_block"] == 6
    e = FN.estimate(48, 720, 480, 0.5)
    assert e["input_megapixels_per_frame"] == pytest.approx(0.3456) and e["gpu_seconds"] == pytest.approx(0.3456 * 48 * 0.5)
    assert FN.estimate(48, 720, 480)["gpu_seconds"] is None            # never invented
    with pytest.raises(ValueError):
        FN.RealESRGANUpscaler("nope")
    with pytest.raises(RuntimeError, match="falta el peso"):
        FN.RealESRGANUpscaler("anime-video", weights_dir="/nonexistent_dir")  # no silent download


def _video(path, w=80, h=48, secs=2, fps=12, audio=True):
    wr = imageio.get_writer(path, fps=fps, macro_block_size=1)
    for t in range(secs * fps):
        f = np.zeros((h, w, 3), np.uint8)
        f[:, :, t % 3] = 120
        f[h // 4 : h // 2, (t * 3) % (w // 2) : (t * 3) % (w // 2) + w // 8] = 255
        wr.append_data(f)
    wr.close()
    if audio:
        wav = path + ".wav"
        sr = 16000
        write_wav(wav, (np.sin(2 * np.pi * 220 * np.arange(sr * secs) / sr) * 0.3).astype(np.float32), sr)
        tmp = path + ".mux.mp4"
        subprocess.run([_ffmpeg(), "-v", "error", "-y", "-i", path, "-i", wav, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-shortest", tmp], check=True)
        os.replace(tmp, path)


def _streams(path):
    err = subprocess.run([_ffmpeg(), "-i", path], capture_output=True, text=True).stderr
    size = re.search(r"Video:.*?, (\d+)x(\d+)", err)
    return (int(size.group(1)), int(size.group(2))), "Audio:" in err


def test_cpu_path_reaches_exact_format_and_keeps_audio(tmp_path):
    src, dst = str(tmp_path / "a.mp4"), str(tmp_path / "out.mp4")
    _video(src)
    rep = FN.finish_video(src, dst, "320x180", "fit", use_ai=False, sharpen="medium", denoise=True)
    assert rep["mode"] == "lanczos" and _streams(dst) == ((320, 180), True)
    fill = FN.finish_video(src, str(tmp_path / "f.mp4"), "180x180", "fill", use_ai=False)
    assert _streams(str(tmp_path / "f.mp4"))[0] == (180, 180)


class Nearest4x:
    """Stand-in for Real-ESRGAN: nearest-neighbour x4, then the requested outscale like the real wrapper does."""

    def __init__(self):
        self.calls = []

    def upscale(self, frame, outscale):
        self.calls.append(outscale)
        up = np.repeat(np.repeat(frame, 4, 0), 4, 1)
        h, w = int(frame.shape[0] * outscale), int(frame.shape[1] * outscale)
        ys, xs = (np.arange(h) * up.shape[0] // h), (np.arange(w) * up.shape[1] // w)
        return up[ys][:, xs]


def test_ai_path_runs_the_upscaler_per_frame_then_reaches_the_format_and_audio(tmp_path):
    src, dst = str(tmp_path / "a.mp4"), str(tmp_path / "out.mp4")
    _video(src)
    up, prog = Nearest4x(), []
    rep = FN.finish_video(src, dst, "fhd", "fit", upscaler=up, progress=prog.append)
    assert rep["mode"] == "esrgan" and len(up.calls) == 24 and up.calls[0] == pytest.approx(rep["plan"]["outscale"])
    assert _streams(dst) == ((1920, 1080), True) and prog[-1] == 1.0 and max(prog[:-1]) <= 0.95
    # no upscaling needed -> the AI step is skipped even if an upscaler is available
    big = str(tmp_path / "big.mp4")
    _video(big, 640, 360, secs=1, audio=False)
    r2 = FN.finish_video(big, str(tmp_path / "o2.mp4"), "320x180", "fit", upscaler=up)
    assert r2["mode"] == "lanczos" and _streams(str(tmp_path / "o2.mp4"))[0] == (320, 180)


def test_dry_run_and_postprocess_builtin_step(tmp_path):
    src = str(tmp_path / "a.mp4")
    _video(src, audio=False)
    assert FN.finish_video(src, str(tmp_path / "x.mp4"), "hd", dry=True)["plan"]["target"] == (1280, 720)
    assert not os.path.exists(tmp_path / "x.mp4")
    log = PP.run_steps([{"name": "polish", "builtin": "finish", "format": "240x136", "use_ai": False, "sharpen": "off"}], src, None, str(tmp_path / "w"), "ep")
    assert log[0]["status"] == "ok" and "lanczos" in log[0]["note"] and _streams(log[-1]["final"])[0] == (240, 136)
