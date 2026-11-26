import json
import os

import numpy as np
import pytest

from studio import pipeline as PL
from studio import requirements as RQ
from studio import timing as TM
from studio import tui, learning as L


def test_fit_recovers_linear_cost_and_clamps_negatives():
    f = TM.fit([1, 2, 4, 8], [1.5, 2.0, 3.0, 5.0])  # 1 + 0.5 x
    assert abs(f["fixed_s"] - 1.0) < 1e-6 and abs(f["per_unit_s"] - 0.5) < 1e-6 and f["r2"] > 0.999
    g = TM.fit([1, 2, 3], [3.0, 2.0, 1.0])  # decreasing noise -> never a negative cost
    assert g["per_unit_s"] == 0.0 and g["fixed_s"] >= 0.0
    assert TM.fit([5], [2.0])["per_unit_s"] == 0.0


def test_timing_catalog_covers_every_phase_and_cost_grows_with_content(tmp_path):
    res = TM.run_bench(sizes_s=(8, 16, 32), lines=(2, 4, 8), out=str(tmp_path), size=(160, 90))
    learn, create = res["learning"], res["creation"]
    assert {p.key for p in L.LEARNING_PHASES} == set(learn["phases"])
    for key in ("scan", "characters", "lips", "profile"):
        assert learn["phases"][key]["measured"], key
    rows = learn["rows"]
    t = [rows[k]["total"] for k in sorted(rows, key=float)]
    assert t[-1] > t[0]  # more material -> more time
    proj = TM.project(learn, [10, 60, 420])
    for k in learn["phases"]:
        assert proj["10"][k] <= proj["60"][k] <= proj["420"][k]  # monotonic projections
    assert create["phases"]["voices"]["per_unit_s"] >= 0 and create["phases"]["mix"]["measured"]
    md = open(tmp_path / "TIEMPOS.md", encoding="utf-8").read()
    assert "Catálogo de tiempos" in md and "Escaneo y análisis de vídeo" in md and "Generación de vídeo (GPU, sin medir)" in md
    g = TM.generation_table(0.5)
    assert g[0]["gpu_seconds"] == pytest.approx(g[0]["step_segments"] * 0.5) and TM.generation_table()[0]["gpu_seconds"] is None
    assert json.load(open(tmp_path / "timings.json"))["learning"]["sizes_s"] == [8, 16, 32]


def test_checks_judge_levels_and_say_what_is_missing():
    c = RQ.Check("x", "X", 10, "min", 20, 120, 420, "w").judge()
    assert c.verdict == "insuficiente" and "para «mínimo» faltan 10 min" in c.missing
    assert RQ.Check("x", "X", 130, "min", 20, 120, 420, "w").judge().verdict == "bueno"
    assert RQ.Check("x", "X", 500, "min", 20, 120, 420, "w").judge().verdict == "óptimo"
    lower = RQ.Check("ci", "CI", 9.0, "%", 25, 12, 6, "w", higher_is_better=False).judge()
    assert lower.verdict == "bueno" and "bajar" in lower.missing
    cl = RQ.Check("s", "Clips", 10, "clips", 32, 100, 400, "w").judge(lambda c: c * 3 / 60)
    assert "min de material" in cl.missing


def test_bootstrap_ci_shrinks_with_more_data():
    rng = np.random.default_rng(0)
    small, big = rng.lognormal(1.0, 0.6, 30), rng.lognormal(1.0, 0.6, 1200)
    assert RQ.bootstrap_halfwidth(big) < RQ.bootstrap_halfwidth(small)
    assert RQ.bootstrap_halfwidth(np.array([1.0, 2.0])) == 1.0  # too few samples: no confidence


def test_more_material_never_lowers_the_verdict(tmp_path):
    out = {}
    for name, secs in (("small", 8), ("large", 40)):
        show = TM.make_show(str(tmp_path / name), secs, 2, size=(160, 90))
        ws = str(tmp_path / f"ws_{name}")
        os.makedirs(ws)
        ctx = {"input": show, "ws": ws, "device": "cpu", "workers": 1, "vision": False, "voice": "logmel", "gpu_mem_gb": 80.0}
        PL.run(L.LEARNING_PHASES, ctx, PL.Reporter())
        out[name] = {c["key"]: c for c in RQ.run(ws)["checks"]}
    assert out["large"]["total"]["have"] > out["small"]["total"]["have"]
    levels = RQ.LEVELS
    for k in ("total", "shots", "speech", "mouth"):
        assert levels.index(out["large"][k]["verdict"]) >= levels.index(out["small"][k]["verdict"]), k
    assert os.path.exists(tmp_path / "ws_large" / "REQUISITOS.md")
