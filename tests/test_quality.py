import os

import imageio
import numpy as np
import pytest

from studio import quality as Q


def _video(path, flicker=0.0, jitter=0, seed=0, T=24, W=64, H=40):
    rng = np.random.default_rng(seed)
    w = imageio.get_writer(path, fps=12, macro_block_size=1)
    x = 4.0
    for t in range(T):
        x += 2 + (int(rng.integers(-jitter, jitter + 1)) if jitter else 0)   # constant speed, optionally with erratic steps
        xi = int(np.clip(x, 0, W - 12))
        f = np.full((H, W, 3), 90, np.float32)
        f[12:24, xi : xi + 12] = 220
        f *= 1.0 + flicker * (1 if t % 2 else -1)
        w.append_data(np.clip(f, 0, 255).astype(np.uint8))
    w.close()


def test_metrics_see_flicker_jitter_and_noise_levels(tmp_path):
    calm, flick, jit = (str(tmp_path / n) for n in ("calm.mp4", "flick.mp4", "jit.mp4"))
    _video(calm)
    _video(flick, flicker=0.25)
    _video(jit, jitter=6)
    mc, mf, mj = (Q.score_video(p) for p in (calm, flick, jit))
    assert mf["flicker"] > 5 * mc["flicker"] + 0.01          # alternating brightness
    assert mj["stutter"] > 2 * mc["stutter"]                  # erratic step-to-step motion
    assert 0.5 < mc["frame_corr"] <= 1.0 and mc["color_drift"] < 0.1
    with pytest.raises(ValueError):
        Q.metrics(np.zeros((3, 4, 4, 3), np.float32))


def _fake(flicker, stutter, corr, drift, sharp=1.0):
    return {"flicker": flicker, "stutter": stutter, "frame_corr": corr, "color_drift": drift, "sharpness": sharp}


def test_paired_comparison_verdicts_and_small_samples():
    rng = np.random.default_rng(1)
    a = [_fake(0.05 + rng.normal(0, 0.005), 1.0, 0.9, 0.02) for _ in range(12)]
    b_better = [_fake(x["flicker"] - 0.02, x["stutter"], x["frame_corr"] + 0.01, x["color_drift"]) for x in a]
    b_same = [dict(x, flicker=x["flicker"] + rng.normal(0, 0.01)) for x in a]
    b_worse = [dict(x, flicker=x["flicker"] + 0.03) for x in a]
    assert Q.compare(a, b_better)["flicker"]["verdict"] == "B mejor" and Q.compare(a, b_better)["frame_corr"]["verdict"] == "B mejor"
    assert Q.compare(a, b_same)["flicker"]["verdict"] == "sin diferencia clara"
    assert Q.compare(a, b_worse)["flicker"]["verdict"] == "B peor"
    assert Q.compare(a, b_better)["sharpness"]["verdict"] == "informativa"      # sharper is not automatically better
    assert "insuficiente" in Q.compare(a[:3], b_better[:3])["flicker"]["verdict"]  # no verdict from 3 pairs
    with pytest.raises(ValueError):
        Q.compare(a, b_better[:-1])


def test_pick_best_prefers_the_steadier_candidate_and_handles_one_candidate():
    good, bad, mid = _fake(0.01, 1.0, 0.95, 0.01), _fake(0.20, 3.0, 0.60, 0.15), _fake(0.08, 1.8, 0.80, 0.05)
    assert Q.pick_best([bad, good, mid]) == 1 and Q.pick_best([bad]) == 0
    assert Q.pick_best([_fake(0.05, 1, 0.9, 0.02, 5.0), _fake(0.05, 1, 0.9, 0.02, 50.0)]) == 0  # sharpness alone never decides


def test_ab_and_pick_cli_on_real_files(tmp_path):
    from studio.cli import main

    for run, fl in (("A", 0.0), ("B", 0.25), ("C", 0.05)):
        for i in range(6):
            os.makedirs(tmp_path / run / f"prompt-{i}", exist_ok=True)
            _video(str(tmp_path / run / f"prompt-{i}" / "000000.mp4"), flicker=fl, seed=i)
    out = tmp_path / "ab.md"
    main(["ab", str(tmp_path / "A"), str(tmp_path / "B"), "--out", str(out)])
    txt = out.read_text(encoding="utf-8")
    assert "parpadeo de brillo" in txt and "B peor" in txt and "no sustituyen" in txt
    main(["pick", str(tmp_path / "B"), str(tmp_path / "C"), str(tmp_path / "A"), "--out", str(tmp_path / "p.json"), "--link", str(tmp_path / "best")])
    import json

    picked = json.load(open(tmp_path / "p.json"))
    assert len(picked) == 6 and all(v["winner"].endswith("A") for v in picked.values())
    assert os.path.islink(tmp_path / "best" / "prompt-0" / "000000.mp4")
