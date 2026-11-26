import json
import numpy as np
import pytest

from studio import cli, profile as P, script as S
from studio.ingest import detect_shots, ingest_folder
from studio.regulate import best, regulate


def _frames(T=40):
    for t in range(T):
        f = np.zeros((36, 64, 3), np.uint8)
        if t < 20:
            f[:, :, 0] = 40
            f[10:20, t : t + 10] = 255
        else:
            f[:, :, 2] = 220
        yield f


def test_shot_detection_finds_cut():
    bounds, _, _ = detect_shots(_frames(), 16.0)
    assert len(bounds) == 2 and bounds[0][1] == 20


def test_incremental_ingest(tmp_path):
    (tmp_path / "a.mp4").write_bytes(b"x")
    calls = []

    def fake(p):
        calls.append(p)
        from studio.ingest import Shot, VideoInfo
        import os
        st = os.stat(p)
        return VideoInfo(p, st.st_size, st.st_mtime, 16, 720, 480, 12.0, [Shot(0, 6, .05, .5, [[1, 2, 3]]), Shot(6, 12, .05, .5, [[1, 2, 3]])])

    m = str(tmp_path / "m.json")
    ingest_folder(str(tmp_path), m, fake)
    ingest_folder(str(tmp_path), m, fake)
    assert len(calls) == 1  # second run is a cache hit


def test_script_to_segments_and_stage():
    sc = S.parse_script("EXT. PARK\n[7s] A fox runs.\nNEG: blurry\n\nThe fox sleeps.", 3.0)
    assert [s.seconds for s in sc] == [7.0, 3.0] and sc[0].neg == "blurry" and sc[1].new_scene is False
    segs, _ = S.to_segments(sc, "cartoon")
    assert len(segs) == 4 and segs[0]["requires_scene_transition"] and not segs[1]["requires_scene_transition"]
    assert S.stage_for(4, 63) == 18 and S.eval_overrides(9)["eval.sampling_num_frames"] == 37
    assert len(S.pack_videos(segs * 10, 18)) > 1


def test_plan_scales_with_data():
    prof = {"episode_seconds": [60.0] * 3, "cuts_per_min": 10, "motion": .05, "brightness": .5}
    plan = P.training_plan(prof, 80)
    assert [s["seconds"] for s in plan["stages"]] == [3]  # 180s of data can't support 9s stage (20 clips < 32)
    prof["episode_seconds"] = [600.0] * 20
    assert P.training_plan(prof, 40)["stages"][-1]["layer"] == "hyper_linear"


def test_regulation_retries_then_keeps_best():
    scores = iter([0.3, 0.7, 0.8])
    h = regulate(lambda seed, steps: (seed, steps), lambda o: next(scores), target=0.75)
    assert len(h) == 3 and best(h).score == 0.8
    assert h[2].steps > h[1].steps  # near-miss escalates steps
    assert h[0].steps == 50
