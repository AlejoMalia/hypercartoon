import os
import shutil
import numpy as np
import pytest

from studio import budget as B
from studio.story import convert as CV, native as NT, pacing as PC, plan as SP
from studio.story.script_engine import ScriptEngineBridge, available

SCREENPLAY = """INT. COCINA - NOCHE

ZORRO entra con una linterna.

ZORRO
Hola, ¿hay alguien aquí? Necesito encontrar el mapa antes de que amanezca.

BUHO
(en voz baja)
Eres un inutil, no sirves para nada!

EXT. BOSQUE - DIA

El zorro corre entre los arboles.

ZORRO
Perdona, te quiero mucho.

—Vuelve —dijo Buho.
"""


def test_pacing_makes_dialogue_fit():
    long_line = [("FOX", "Hola, soy el zorro y hoy voy a contarte una historia muy larga sobre el bosque encantado")]
    assert PC.dialogue_seconds(long_line) > 3.0
    assert PC.scene_seconds(5, long_line, requested=3.0) >= 6.0 and PC.scene_seconds(5, long_line) % 3 == 0
    assert PC.scene_seconds(0, []) == 3.0


def test_converter_reads_screenplay_prose_and_blocks():
    d = CV.parse_doc(SCREENPLAY)
    assert d.fmt == "screenplay" and len(d.scenes) == 2
    assert d.scenes[0].place == "COCINA" and d.scenes[0].time == "noche" and d.scenes[0].cues == ["en voz baja"]
    assert [c for c, _ in d.scenes[0].lines] == ["ZORRO", "BUHO"]
    assert d.scenes[1].lines[-1] == ("BUHO", "Vuelve.")  # dash dialogue with attribution
    blocks = CV.parse_doc("EXT. RIO [6s] El zorro nada.\nZORRO: Que frio!\nBUHO: Salta!\n\nEl buho vuela.\nBUHO: Ya voy.")
    assert [s.lines for s in blocks.scenes][0][0] == ("ZORRO", "Que frio!") and len(blocks.scenes) >= 1
    out = CV.doc_to_script(d)
    assert "ZORRO: Hola" in out and "[12s]" in out  # long dialogue got a duration that fits


def test_native_reading_and_threads():
    d = CV.parse_doc(SCREENPLAY * 3)
    r = NT.read(d)
    assert r["stats"]["scenes"] == 6 and r["characters"][0]["name"] == "ZORRO" and len(r["acts"]) >= 3
    assert len(r["tension"]) == 6
    # a character who speaks early and then disappears is an open thread
    txt = "INT. A\nA\nhola hola\nB\nque tal\n\n" * 1
    script = "\n\n".join(f"[3s] escena {i}\nREY: linea {i}\nREY: otra {i}" for i in range(2)) + "\n\n" + "\n\n".join(f"[3s] fin {i}\nZORRO: hola {i}" for i in range(6))
    th = NT.threads(NT.read(CV.parse_doc(script)))
    assert any(t["kind"] == "vanished character" and t["subject"] == "REY" for t in th)


def test_analyze_validate_and_report_spanish():
    res = SP.analyze("INT. CASA - DIA\n[3s] Hablan.\nA: " + "palabras " * 30 + "\nB: ok\n", bridge=None)
    iss = SP.validate(res, known_looks={"A"}, max_seconds=3)
    kinds = " ".join(i["msg"] for i in iss)
    assert "B no tiene aspecto" in kinds and "dura" in kinds
    rep = SP.report_es(res, iss)
    assert rep.startswith("# Informe del guion") and "Problemas y correcciones" in rep


@pytest.mark.skipif(not available(), reason="Node not available")
def test_script_bridge_is_zero_cost_and_enriches():
    with ScriptEngineBridge() as b:
        res = SP.analyze(SCREENPLAY, bridge=b)
    assert res["source"] == "script-hypercartoon+native" and len(res["reading"]["scenes"]) == 2
    assert res["reading"]["scenes"][0]["place"] == "COCINA"


def test_budget_adaptive_cache_and_draft(tmp_path):
    vids = [[{"text": f"scene {i} fox runs"}] * 2 for i in range(4)]
    tens = [10, 50, 90, None]
    c = B.ShotCache(str(tmp_path / "c.json"))
    p = B.plan_compute(vids, tens, c, "adaptive")
    assert [v["steps"] for v in p["videos"]] == [25, 35, 50, 35] and p["saving_pct"] > 25
    c.record([s["text"] for s in vids[0]], 25, "a.mp4")
    c.record([s["text"] for s in vids[2]], 30, "b.mp4")  # fewer steps than the plan needs -> not a hit
    p2 = B.plan_compute(vids, tens, B.ShotCache(str(tmp_path / "c.json")), "adaptive")
    assert p2["videos"][0]["cached"] == "exact" and p2["videos"][2]["cached"] is None and p2["expected"] < p["expected"]
    near = B.ShotCache(str(tmp_path / "c.json")).lookup(["scene 0 fox runs", "scene 0 fox runs", ], 25)
    assert near and near["kind"] == "exact"
    d = B.plan_compute(vids, tens, None, "draft", fail_rate=0.25)
    assert d["planned"] == 4 * 2 * 20 and d["refine_expected"] == round(0.25 * 4 * 2 * 50) and abs(d["saving_pct"] - 35.0) < 0.1
    assert B.select_refine([0.9, 0.5, float("nan"), 0.8], 0.75) == [1, 2]
