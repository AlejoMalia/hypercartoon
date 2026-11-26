import io
import json
import os

import imageio
import numpy as np
import pytest

from studio import pipeline as PL
from studio import tui


def _video(path, secs=4, fps=16):
    w = imageio.get_writer(path, fps=fps)
    for t in range(secs * fps):
        f = np.zeros((48, 80, 3), np.uint8)
        if t < secs * fps // 2:
            f[:, :, 0] = 40
            f[10:20, t % 60 : t % 60 + 10] = 255
        else:
            f[:, :, 2] = 220
        w.append_data(f)
    w.close()


def test_pipeline_statuses_skip_error_and_essential():
    seen = {}

    def ok(ctx, prog):
        prog(0.5, "mitad")
        ctx["x"] = 1
        return "hecho"

    def skip(ctx, prog):
        raise PL.Skip("falta algo")

    def boom(ctx, prog):
        raise ValueError("mal")

    def peek(ctx, prog):
        seen["prev"] = [o.key for o in ctx["_outcomes"]]

    ctx = {}
    outs = PL.run([PL.Phase("a", "A", 1, ok), PL.Phase("b", "B", 1, skip), PL.Phase("c", "C", 1, boom), PL.Phase("d", "D", 1, peek)], ctx)
    assert [o.status for o in outs] == ["ok", "skipped", "error", "ok"] and outs[2].note.startswith("ValueError")
    assert seen["prev"] == ["a", "b", "c"]
    outs = PL.run([PL.Phase("a", "A", 1, boom, essential=True), PL.Phase("b", "B", 1, ok)], {})
    assert len(outs) == 1 and outs[0].status == "error"  # an essential failure stops the run
    outs = PL.run([PL.Phase("a", "A", 1, lambda c, p: (_ for _ in ()).throw(SystemExit("x")))], {})
    assert outs[0].status == "error"


def test_panel_live_and_plain_render():
    ph = [PL.Phase("a", "Escaneo", 3, lambda c, p: (p(0.5, "x.mp4"), "nota a")[1]), PL.Phase("b", "Perfil", 1, lambda c, p: None)]
    live = io.StringIO()
    PL.run(ph, {}, tui.Panel("TITULO", live, color=False, live=True))
    txt = live.getvalue()
    assert "TITULO" in txt and "100%" in txt and "Total" in txt and "✔" in txt and "█" in txt
    plain = io.StringIO()
    PL.run(ph, {}, tui.Panel("TITULO", plain, color=False, live=False))
    assert "[100%]" in plain.getvalue() and "Escaneo" in plain.getvalue()
    assert tui.fmt_t(75) == "01:15" and tui.fmt_t(3700) == "1:01:40" and tui.fmt_t(None) == "--:--"


def test_overall_percentage_is_weighted():
    p = tui.Panel("t", io.StringIO(), live=False)
    p.begin([PL.Phase("a", "A", 3, None), PL.Phase("b", "B", 1, None)])
    p.frac = [1.0, 0.0]
    assert abs(p.overall() - 0.75) < 1e-9


def test_terminal_flow_folder_then_episode(tmp_path):
    show = tmp_path / "Show"
    (show / "S01").mkdir(parents=True)
    (show / "S02").mkdir()
    for n in ("S01/E01", "S01/E02", "S02/E01"):
        _video(str(show / f"{n}.mp4"))
    script = tmp_path / "guion.txt"
    script.write_text("INT. COCINA - NOCHE\n\nZORRO entra.\n\nZORRO\nHola, ¿hay alguien?\n\nBUHO\nSoy el buho!\n", encoding="utf-8")
    answers = iter(["2", str(show), str(script)])  # folder, path, then the script to create
    out = io.StringIO()
    proj = tmp_path / "proj"
    rc = tui.main(["--out", str(proj)], inp=lambda prompt="": next(answers), out=out)
    txt = out.getvalue()
    assert rc == 0 and "PROCESO COMPLETADO" in txt and "EPISODIO PREPARADO" in txt
    kit = json.load(open(proj / "episode_kit.json"))
    assert kit["complete"] and kit["source"]["videos"] == 3 and kit["ready"]["style"] and kit["ready"]["plan"]
    assert {p["key"] for p in kit["phases"]} >= {"scan", "corpus", "profile", "characters", "soundbank", "kit"}
    assert os.path.exists(proj / "LEEME.md") and os.path.exists(proj / "profile.json")
    ep = proj / "episodes" / "episodio_01"
    assert (ep / "prompts.jsonl").exists() and (ep / "episode.json").exists() and (ep / "story_report.md").exists()
    assert json.load(open(ep / "episode.json"))["generate_video_commands"]


def test_terminal_single_video_and_bad_path(tmp_path):
    v = tmp_path / "solo.mp4"
    _video(str(v))
    out = io.StringIO()
    rc = tui.main([str(v), "--out", str(tmp_path / "p"), "--no-create"], inp=lambda p="": "", out=out)
    assert rc == 0 and json.load(open(tmp_path / "p" / "episode_kit.json"))["source"]["videos"] == 1
    assert tui.main([str(tmp_path / "no_existe")], inp=lambda p="": "", out=io.StringIO()) == 2
