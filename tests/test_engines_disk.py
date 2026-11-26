import os

import pytest

from studio.engines import registry as R
from studio.engines.diffusers_engine import DiffusersEngine


def test_disk_guard_refuses_a_download_that_does_not_fit(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "hub"))
    spec = R.get("ltx-video")
    monkeypatch.setattr(R, "disk_free_gb", lambda path="": 10.0)
    msg = R.disk_problem(spec)
    assert "28.4" in msg and "10.0" in msg and "HF_HOME" in msg
    monkeypatch.setattr(R, "disk_free_gb", lambda path="": 200.0)
    assert R.disk_problem(spec) == ""
    # a cached or local repo needs no download
    monkeypatch.setattr(R, "disk_free_gb", lambda path="": 1.0)
    os.makedirs(tmp_path / "hub" / "models--Lightricks--LTX-Video" / "snapshots" / "abc")
    assert R.disk_problem(spec) == "" and R.disk_problem(spec, str(tmp_path)) == ""


def test_engine_stops_before_downloading_when_the_disk_is_too_small(monkeypatch, tmp_path):
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "hub"))
    monkeypatch.setattr(R, "disk_free_gb", lambda path="": 2.0)
    import studio.engines.diffusers_engine as DE

    monkeypatch.setattr(DE, "disk_problem", R.disk_problem)
    pytest.importorskip("torch")
    pytest.importorskip("diffusers")
    with pytest.raises(RuntimeError, match="libres"):
        DiffusersEngine(R.get("wan22-ti2v-5b")).load()


def test_every_diffusers_engine_has_a_measured_download_size():
    assert all(e.download_gb > 0 for e in R.ENGINES.values() if e.pipeline)
    assert R.get("ltx-video").lora_trainer == "builtin" and R.get("wan22-ti2v-5b").lora_trainer == "finetrainers"


def test_train_lora_command_points_other_engines_to_finetrainers(tmp_path):
    from studio import cli

    with pytest.raises(SystemExit, match="finetrainers"):
        cli.main(["--workdir", str(tmp_path), "train-lora", "--engine", "wan22-ti2v-5b", "--data", str(tmp_path), "--out", str(tmp_path / "o")])
