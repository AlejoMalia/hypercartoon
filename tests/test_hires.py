import os
import re
import subprocess

import imageio
import numpy as np
import pytest

from studio import hires as HR
from studio import quality as Q
from studio import tiling as T
from studio.audio import _ffmpeg
from studio.sound.mix import write_wav


# ---- planner: three named modes with exact costs ---------------------------------------------------------------------------------------
def test_three_modes_have_the_documented_tile_counts_and_costs():
    no = T.plan_tiles((1440, 960), (720, 480), "no_overlap")
    sa = T.plan_tiles((1440, 960), (720, 480), "seam_aware")
    fo = T.plan_tiles((1440, 960), (720, 480), "full_overlap")
    assert [len(g) for g in no.grids] == [4] and no.overlap == (0, 0) and no.passes_per_step == 4 and no.feather == 0
    assert [len(g) for g in sa.grids] == [4, 5] and sa.passes_per_step == 4.5 and (360, 240) in [(t.x0, t.y0) for t in sa.grids[1]]
    assert [len(g) for g in fo.grids] == [9] and fo.overlap == (360, 240) and fo.passes_per_step == 9
    assert {m: T.plan_tiles((1440, 960), (720, 480), a).mode for m, a in (("exact", "no_overlap"), ("alternate", "seam_aware"), ("overlap", "full_overlap"))} == \
        {"exact": "no_overlap", "alternate": "seam_aware", "overlap": "full_overlap"}                      # names of the first version still work
    with pytest.raises(ValueError):
        T.plan_tiles((1440, 960), (720, 480), "diagonal")


def test_overlap_pixels_only_where_an_overlap_is_possible():
    with pytest.raises(ValueError, match="no_overlap"):
        T.plan_tiles((1440, 960), (720, 480), "no_overlap", overlap_pixels=64)
    assert T.plan_tiles((1440, 960), (720, 480), "no_overlap", overlap_pixels=0).passes_per_step == 4      # 0 is the same as not passing it
    assert T.plan_tiles((1440, 960), (720, 480), "seam_aware", overlap_pixels=96).feather == 96            # = feather width in seam_aware
    a = T.plan_tiles((1440, 960), (720, 480), "full_overlap", overlap_pixels=100)                          # asks 100 px, a fixed window cannot give less than 360
    assert len(a.grids[0]) == 9 and a.overlap[0] >= 360 and any("mínimo posible" in w for w in a.warnings)
    b = T.plan_tiles((1440, 960), (720, 480), "full_overlap", overlap_pixels=400)                          # 400 px needs more than 3 tiles per axis
    assert len(b.grids[0]) > 9 and b.overlap[0] >= 400 and b.overlap[1] >= 400
    with pytest.raises(ValueError):
        T.plan_tiles((1440, 960), (720, 480), "full_overlap", overlap_pixels=440)                          # > 90 % of the window


def test_cost_is_explicit_in_passes_steps_and_memory():
    p = T.plan_tiles((1440, 960), (720, 480), "seam_aware")
    c = T.cost(p, seconds=63, steps=25, base_vram_gb=40, batch_tiles=2)
    assert c["passes_per_step"] == 4.5 and c["total_tile_passes"] == 112.5 and c["step_segments"] == pytest.approx(4.5 * 25 * 21)
    assert c["wall_relative"] == 2.25 and c["vram_gb"] == 80 and 0.1 < c["state_gb"] < 0.3 and T.cost(p, 3, 25)["vram_gb"] is None


def test_alignment_for_the_token_grid():
    p = T.plan_tiles((1440, 960), (720, 480), "seam_aware", align=16)
    assert all(t.x0 % 16 == 0 and t.y0 % 16 == 0 for g in p.grids for t in g)
    assert p.grids[0][3].norm(p.frame) == (0.5, 0.5, 1.0, 1.0)


# ---- fusion: windows that sum to exactly 1, exposure matching, seam metric and the gate ---------------------------------------------------
@pytest.mark.parametrize("kind", ["cosine", "gaussian"])
@pytest.mark.parametrize("mode,ov", [("full_overlap", 48), ("seam_aware", None), ("no_overlap", None)])
def test_normalised_windows_sum_to_exactly_one_where_covered(kind, mode, ov):
    p = T.plan_tiles((192, 128), (96, 64), mode, ov)
    for grid in p.grids:
        ws = T.normalized_windows(grid, p.frame, max(8, p.feather), kind)
        tot, cov = np.zeros((128, 192)), np.zeros((128, 192), bool)
        for t, w in zip(grid, ws):
            tot[t.y0 : t.y1, t.x0 : t.x1] += w
            cov[t.y0 : t.y1, t.x0 : t.x1] = True
        assert np.allclose(tot[cov], 1.0, atol=1e-12) and np.allclose(tot[~cov], 0.0)
    with pytest.raises(ValueError):
        T.tile_window(p.grids[0][0], p.frame, 8, "box")


def test_blending_reconstructs_and_exposure_matching_removes_the_step():
    p = T.plan_tiles((192, 128), (96, 64), "full_overlap", 48)
    img = np.random.default_rng(0).random((128, 192, 3)) * 200 + 20
    parts = T.split(img, p.grids[0])
    assert np.abs(T.blend(parts, p.grids[0], (128, 192), 24) - img).max() < 1e-9
    bad = [q * (1 + 0.1 * (k % 3)) + 5 * (k % 2) for k, q in enumerate(parts)]
    fixed, _ = T.match_exposure(bad, p.grids[0])
    before = np.abs(T.blend(bad, p.grids[0], (128, 192), 24) - img).mean()
    after = np.abs(T.blend(fixed, p.grids[0], (128, 192), 24) - img).mean()
    assert after < 0.3 * before and np.allclose(fixed[0], parts[0])


def test_abutting_tiles_get_an_exposure_ramp_and_the_seam_metric_is_a_hard_gate():
    flat = 100 + np.random.default_rng(2).normal(0, 1, (60, 120, 3))
    stepped = flat.copy()
    stepped[:, 60:] += 25
    stepped[40:, :] += 15
    before = T.seam_visibility(stepped, [60], [40])
    after = T.seam_visibility(T.smooth_seams(stepped, [60], [40], 24), [60], [40])
    assert before["ratio"] > 8 and after["ratio"] < T.SEAM_OK
    with pytest.raises(T.SeamTooVisible):
        T.check_seams(before)                                                   # the automatic failure above the threshold
    assert T.check_seams(after)["ratio"] < T.SEAM_OK


def test_alternating_sync_keeps_uncovered_corners():
    p = T.plan_tiles((192, 128), (96, 64), "seam_aware")
    sync = T.MultiTileSync(p, feather=8)
    sync.state = np.zeros((128, 192, 1))
    sync.sync([np.full((64, 96, 1), 1.0) for _ in p.grids[0]], 0)
    f2 = sync.sync([np.full((64, 96, 1), 5.0) for _ in p.grids[1]], 1)
    assert f2[0, 0, 0] == 1.0 and f2[64, 96, 0] == pytest.approx(5.0) and len(sync.tiles_for(2)) == 4


# ---- refiners are separate and stage-aware ----------------------------------------------------------------------------------------------
def test_refiners_declare_their_stage_and_enhance_a_video_is_not_a_post_refiner():
    assert {k: v.stage for k, v in HR.REFINERS.items()} == {"identity": "B", "esrgan": "B", "generative": "B", "enhance_a_video": "A"}
    with pytest.raises(HR.StageError, match="--eval.enhance_weight=2"):
        HR.make_refiner("enhance_a_video")
    assert HR.stage_a_flags(1.5) == ["--eval.enhance_weight=1.5"]
    with pytest.raises(ValueError):
        HR.stage_a_flags(0)
    with pytest.raises(ValueError, match="upscaler"):
        HR.make_refiner("esrgan")
    with pytest.raises(ValueError, match="backend"):
        HR.make_refiner("generative")
    assert HR.make_refiner("identity").name == "identity"


def test_enhance_weight_reaches_the_stage_a_generation_commands(tmp_path):
    from studio import episode as EP, pipeline as PL

    ws = tmp_path / "ws"
    ws.mkdir()
    import json

    (ws / "profile.json").write_text(json.dumps({"style_prompt": "s", "shot_len": {"median": 3.0}, "cuts_per_min": 10, "motion": .05, "brightness": .5}))
    (ws / "plan.json").write_text(json.dumps({"max_seconds": 9, "stages": [{"seconds": 3, "clips": 40, "steps": 500, "layer": "hyper_mlp"}]}))
    ctx = EP.make_ctx(str(ws), str(ws / "e"), "INT. SALA - DIA\n\nZORRO\nHola.\n", emotion="off", enhance_weight=1.5)
    PL.run([p for p in EP.EPISODE_PHASES if p.key in ("story", "plan", "package")], ctx)
    cmds = json.load(open(ws / "e" / "episode.json"))["generate_video_commands"]
    assert cmds and all("--eval.enhance_weight=1.5" in c for c in cmds)


# ---- the video pipeline ---------------------------------------------------------------------------------------------------------------
def _video(path, w=96, h=64, secs=2, fps=8, audio=True):
    wr = imageio.get_writer(path, fps=fps, macro_block_size=1)
    base = np.random.default_rng(3).random((h, w)) * 120 + 60
    for t in range(secs * fps):
        f = np.stack([base, base * 0.8, base * 0.6], -1)
        f[10:30, (t * 5) % (w - 20) : (t * 5) % (w - 20) + 20] = (230, 200, 40)
        wr.append_data(f.astype(np.uint8))
    wr.close()
    if audio:
        wav = path + ".wav"
        write_wav(wav, (np.sin(2 * np.pi * 220 * np.arange(16000 * secs) / 16000) * 0.3).astype(np.float32), 16000)
        subprocess.run([_ffmpeg(), "-v", "error", "-y", "-i", path, "-i", wav, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-shortest", path + ".m.mp4"], check=True)
        os.replace(path + ".m.mp4", path)


def _streams(p):
    err = subprocess.run([_ffmpeg(), "-i", p], capture_output=True, text=True).stderr
    m = re.search(r"Video:.*?, (\d+)x(\d+)", err)
    return (int(m.group(1)), int(m.group(2))), "Audio:" in err


class JitterRefiner:
    """Like independent diffusion tiles: each tile comes back with its own exposure error."""
    name = "jitter"

    def refine(self, lr, up, tile, i):
        k = (tile.x0 // 40 + 3 * (tile.y0 // 30)) % 4
        return np.clip(up[tile.y0 : tile.y1, tile.x0 : tile.x1].astype(np.float64) * (1 + 0.08 * (k - 1.5)) + 6 * (k - 1.5), 0, 255)


@pytest.mark.parametrize("mode,ov", [("full_overlap", 48), ("seam_aware", None)])
def test_overlapping_modes_pass_the_seam_gate_with_independent_tile_errors(tmp_path, mode, ov):
    src, dst = str(tmp_path / "a.mp4"), str(tmp_path / "o.mp4")
    _video(src)
    r = HR.hires_video(src, dst, 2.0, mode, ov, JitterRefiner(), seam_threshold=T.SEAM_OK)
    assert _streams(dst) == ((192, 128), True) and r["seam_visibility"]["ratio"] < T.SEAM_OK          # normalised windows + exposure matching hide the seams
    assert r["stage"] == "B" and r["cost"]["mode"] == mode and "metrics_vs_lanczos" in r


def _smooth_video(path, w=96, h=64, secs=1, fps=8):
    from scipy.ndimage import gaussian_filter

    base = gaussian_filter(np.random.default_rng(4).random((h, w)), 4.0)
    base = (base - base.min()) / np.ptp(base) * 120 + 60
    wr = imageio.get_writer(path, fps=fps, macro_block_size=1)
    for _ in range(secs * fps):
        wr.append_data(np.stack([base, base * 0.8, base * 0.6], -1).astype(np.uint8))
    wr.close()


class BiasJitter(JitterRefiner):
    """Exposure bias per tile (what an abutting-tile ramp is meant to fix)."""
    name = "bias"

    def refine(self, lr, up, tile, i):
        k = (tile.x0 // 40 + 3 * (tile.y0 // 30)) % 4
        return np.clip(up[tile.y0 : tile.y1, tile.x0 : tile.x1].astype(np.float64) + 12 * (k - 1.5), 0, 255)


def test_no_overlap_can_only_soften_seams_and_the_gate_says_so(tmp_path):
    src = str(tmp_path / "a.mp4")
    _smooth_video(src)
    raw = HR.hires_video(src, str(tmp_path / "raw.mp4"), 2.0, "no_overlap", None, BiasJitter(), exposure_matching=False, allow_visible_seams=True)
    soft = HR.hires_video(src, str(tmp_path / "soft.mp4"), 2.0, "no_overlap", None, BiasJitter(), allow_visible_seams=True)
    assert soft["seam_visibility"]["ratio"] < 0.5 * raw["seam_visibility"]["ratio"]               # the exposure ramp removes most of the step
    assert raw["seam_visibility"]["ratio"] > T.SEAM_OK

    class Mismatch(JitterRefiner):                                                                   # structurally different tiles: no ramp can fix that
        def refine(self, lr, up, tile, i):
            k = tile.x0 // 96 + 2 * (tile.y0 // 64)
            yy, xx = np.mgrid[0 : tile.h, 0 : tile.w]
            return np.stack([128 + 60 * np.sin(0.15 * xx + 1.7 * k)] * 3, -1)

    with pytest.raises(T.SeamTooVisible):                                                            # strict by default: stops before writing the video
        HR.hires_video(src, str(tmp_path / "bad.mp4"), 2.0, "no_overlap", None, Mismatch())
    assert not os.path.exists(tmp_path / "bad.mp4")


def test_exposure_matching_is_mandatory_unless_visible_seams_are_allowed(tmp_path):
    src = str(tmp_path / "a.mp4")
    _video(src, audio=False)
    with pytest.raises(ValueError, match="allow_visible_seams"):
        HR.hires_video(src, str(tmp_path / "x.mp4"), 2.0, "full_overlap", 48, JitterRefiner(), exposure_matching=False)
    r = HR.hires_video(src, str(tmp_path / "z.mp4"), 2.0, "full_overlap", 48, JitterRefiner(), exposure_matching=False, allow_visible_seams=True)
    assert "seam_visibility" in r


def test_identity_is_the_lanczos_baseline_and_dry_run_reports_cost_per_mode(tmp_path):
    src = str(tmp_path / "a.mp4")
    _video(src, audio=False)
    dry = HR.hires_video(src, str(tmp_path / "x.mp4"), 2.0, "seam_aware", dry=True, steps=25, base_vram_gb=40)
    assert dry["cost"]["passes_per_step"] == 9 and any("unión" in w for w in dry["warnings"]) and dry["cost"]["vram_gb"] == 40 and not os.path.exists(tmp_path / "x.mp4")
    r = HR.hires_video(src, str(tmp_path / "id.mp4"), 2.0, "no_overlap")
    m = r["metrics_vs_lanczos"]
    assert r["refiner"] == "identity" and m["lowfreq_psnr_db"] > 40 and m["temporal_ratio"] == pytest.approx(1.0, abs=0.05)   # it IS the baseline


def test_upscaler_refiner_feeds_the_low_res_region_of_each_tile():
    seen = []

    class Fake:
        def upscale(self, region, s):
            seen.append(region.shape[:2])
            return np.repeat(np.repeat(region, 2, 0), 2, 1)

    out = HR.UpscalerRefiner(Fake(), 2.0).refine(np.zeros((64, 96, 3), np.uint8), np.zeros((128, 192, 3), np.uint8), T.Tile(96, 64, 192, 128), 0)
    assert seen == [(32, 48)] and out.shape == (64, 96, 3)


# ---- metrics ---------------------------------------------------------------------------------------------------------------------------
def test_flow_residual_separates_consistent_from_flickering_video_and_compares_to_baseline():
    from scipy.ndimage import gaussian_filter

    rng = np.random.default_rng(0)
    tex = gaussian_filter(rng.random((200, 400)), 2.0)
    tex = (tex - tex.min()) / np.ptp(tex)
    pan = np.stack([np.stack([tex[10:90, 5 + 2 * i : 5 + 2 * i + 160]] * 3, -1) for i in range(8)])
    noisy = np.clip(pan + rng.normal(0, 0.08, pan.shape), 0, 1)
    assert Q.temporal_warp_error(pan) < 0.2 * Q.temporal_warp_error(noisy)
    good, bad = Q.compare_to_baseline(pan * 0.98, pan), Q.compare_to_baseline(noisy, pan)
    assert good["temporal_ratio"] < 1.5 and bad["temporal_ratio"] > 5 and good["lowfreq_psnr_db"] > bad["lowfreq_psnr_db"]
    with pytest.raises(ValueError):
        Q.compare_to_baseline(pan, pan[:, :-2])


def test_cli_hires_dry_run_and_stage_a_message(tmp_path, capsys):
    from studio.cli import main

    src = str(tmp_path / "a.mp4")
    _video(src, audio=False)
    main(["hires", src, "--dry", "--mode", "full_overlap", "--base-vram-gb", "40"])
    out = capsys.readouterr().out
    assert "96x64 -> 192x128" in out and "full_overlap" in out and "9.0 pasadas/paso" in out and "VRAM 40 GB" in out and "seam_aware" in out and "4.5" in out
    main(["hires", src, "--refiner", "enhance_a_video", "--enhance-weight", "1.5"])
    a_out = capsys.readouterr().out
    assert "FASE A" in a_out and "--eval.enhance_weight=1.5" in a_out
    main(["hires", src, "--refiner", "generative", "--strength", "0.3"])
    g = capsys.readouterr().out
    assert "refine_video.py" in g and "--refine.strength 0.3" in g and "--refine.mode seam_aware" in g
