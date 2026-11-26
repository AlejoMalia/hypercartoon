import json
import os

import pytest

from studio import layers as LY


def _shot(dur, shot_type, cam, palette, cell="middle-center", agents=(), scenery=(), free=40.0):
    lab = [{"track": i, "label": l, "kind": "animal" if l in ("dog", "cat") else "person", "agent": True, "caption": f"a {l}", "color": c, "area_pct": 10, "presence": 1.0, "bbox": [0, 0, 1, 1]}
           for i, (l, c) in enumerate(agents)]
    lab += [{"track": 90 + i, "label": l, "kind": "scenery", "agent": False, "caption": l, "color": "green", "area_pct": 5, "presence": 1.0, "bbox": [0, 0, 1, 1]} for i, l in enumerate(scenery)]
    return {"duration": dur, "camera": {"label": cam}, "framing": {"shot_type": shot_type, "subject": {"cell": cell}, "free_space_pct": free, "n_characters": len(agents)},
            "labelled": lab, "color": {"palette": palette, "metrics": {"saturation": 0.6, "luminance": 0.5}}}


def _pal(*cols):
    n = len(cols)
    return [{"rgb": list(c), "pct": 100.0 / n} for c in cols]


YELLOW, BLUE, RED, GREEN, WHITE = (240, 220, 50), (50, 80, 220), (220, 40, 40), (50, 180, 70), (250, 250, 250)


def _analysis(shots, minutes=10.0, palette=None, dialogue=6):
    return {"duration": minutes * 60, "shots": shots, "scenes": [{"start": 0, "end": 60, "palette": _pal(*(palette or [YELLOW]))[:1]} ,
                                                                {"start": 60, "end": 120, "palette": _pal(BLUE)}],
            "dialogue": [{}] * dialogue,
            "color": {"palette": _pal(*(palette or [YELLOW, BLUE])), "bands": {"shadows": {"palette": _pal((20, 20, 40))}, "mids": {"palette": _pal(*(palette or [YELLOW]))},
                                                                                  "highlights": {"palette": _pal(WHITE)}},
                      "metrics": {"saturation": 0.6, "luminance": 0.5}}}


def A():   # show A: fast, close-ups, yellow/blue
    sh = [_shot(1.0, "primer plano", "estático", _pal(YELLOW, BLUE), agents=[("person", "yellow")], scenery=["tree"]) for _ in range(30)]
    sh += [_shot(3.0, "plano medio", "panorámica", _pal(YELLOW, WHITE), agents=[("person", "yellow"), ("dog", "brown")]) for _ in range(10)]
    return _analysis(sh, 5.0, [YELLOW, BLUE])


def B():   # show B: slow, wide shots, green/white; shares the close-up grammar a little
    sh = [_shot(6.0, "plano general", "panorámica", _pal(GREEN, WHITE), agents=[("cat", "gray")], scenery=["hill", "tree"], free=70.0) for _ in range(12)]
    sh += [_shot(1.0, "primer plano", "estático", _pal(GREEN, BLUE), agents=[("cat", "gray")]) for _ in range(6)]
    return _analysis(sh, 8.0, [GREEN, WHITE], dialogue=2)


def test_series_layers_capture_each_kind_of_knowledge():
    L = LY.build_series_layers([A()])
    assert {l: bool(L[l]) for l in LY.LAYERS} == {l: True for l in LY.LAYERS}
    names = {LY._name(c["rgb"]) for c in L["palettes"]["global"]}
    assert "yellow" in names and "blue" in names
    assert L["palettes"]["by_shot_type"]["primer plano"] and L["palettes"]["bands"]["highlights"]
    t = {x["type"]: x for x in L["scene_types"]["types"]}
    assert t["primer plano · estático · quick"]["share"] == pytest.approx(0.75)
    assert t["plano medio · panorámica · medium"]["characters"] == 2
    assert L["rhythm"]["cuts_per_min"] == pytest.approx(40 / 5.0) and L["rhythm"]["camera"]["estático"] == pytest.approx(0.75)
    assert L["backgrounds"]["places"] and L["backgrounds"]["scenery"] == {"tree": 30}
    seen = {(c["label"], c["color"]) for c in L["characters"]["seen"]}
    assert ("person", "yellow") in seen and ("dog", "brown") in seen


def test_studio_merge_pools_averages_and_compares():
    per = {"A": LY.build_series_layers([A()]), "B": LY.build_series_layers([B()])}
    st = LY.merge_layers(per)
    assert set(st["sources"]) == {"A", "B"} and sum(st["sources"].values()) == pytest.approx(1.0)
    cols = {LY._name(c["rgb"]) for c in st["palettes"]["global"]}
    assert {"yellow", "green"} <= cols                                           # both shows are in the studio palette
    cpm = st["rhythm"]["cuts_per_min"]
    assert min(cpm["by_series"].values()) < cpm["mean"] < max(cpm["by_series"].values()) and cpm["spread"] > 0
    types = {t["type"]: t for t in st["scene_types"]["types"]}
    close = types["primer plano · estático · quick"]
    assert close["consistency"] == 1.0 and set(close["by_series"]) == {"A", "B"}   # both shows use close-ups
    wide = types["plano general · panorámica · long"]
    assert wide["consistency"] == 0.5 and wide["specific_to"] == ["B"] and not wide["signature"]
    assert st["characters"]["by_series"]["B"]["seen"][0]["label"] == "cat"          # characters are never averaged
    assert LY.studio_spread(per)["palette_distance_mean"] > 0.1


def test_compose_takes_each_layer_from_where_you_say():
    per = {"A": LY.build_series_layers([A()]), "B": LY.build_series_layers([B()])}
    res = LY.compose(per, {"palettes": "A", "rhythm": "B", "scene_types": {"A": 0.5, "B": 0.5}, "characters": ["A", "B"]}, "mine")
    pal = {LY._name(c["rgb"]) for c in res["layers"]["palettes"]["global"]}
    assert "green" not in pal and "yellow" in pal                                   # palette = show A only
    assert res["layers"]["rhythm"]["cuts_per_min"]["by_series"] == {"B": pytest.approx(per["B"]["rhythm"]["cuts_per_min"])}
    assert set(res["layers"]["characters"]["by_series"]) == {"A", "B"}
    assert res["style"]["kind"] == "composed" and "slow" in res["style"]["style_prompt"] and "yellow" in res["style"]["style_prompt"]
    # layers not named fall back to the studio blend
    assert LY.compose(per, {}, "all")["layers"]["palettes"] == LY.merge_layers(per)["palettes"]
    with pytest.raises(ValueError, match="fuente desconocida"):
        LY.compose(per, {"palettes": "Z"}, "bad")


def test_build_on_disk_import_and_style(tmp_path):
    ws = tmp_path / "ws"
    (ws / "analysis").mkdir(parents=True)
    corpus = {"ShowA": {"1": [{"path": "/v/a1.mp4", "episode": 1, "duration": 300}]}, "ShowB": {"1": [{"path": "/v/b1.mp4", "episode": 1, "duration": 480}]}}
    json.dump(corpus, open(ws / "corpus.json", "w"))
    idx = {}
    for key, an in (("a1", A()), ("b1", B())):
        json.dump(an, open(ws / "analysis" / f"{key}.analysis.json", "w"))
        idx[f"/v/{key}.mp4"] = f"analysis/{key}.analysis.json"
    json.dump(idx, open(ws / "analysis" / "index.json", "w"))
    r = LY.build(str(ws))
    assert r["series"] == ["ShowA", "ShowB"] and r["spread"]["series"] == 2
    for scope in ("ShowA", "ShowB", "_studio"):
        assert all(os.path.exists(ws / "layers" / scope / f"{l}.json") for l in LY.LAYERS) and (ws / "layers" / scope / "style.json").exists()
    assert "cartoon style" in LY.load_style(str(ws), "_studio")["style_prompt"]
    LY.compose_project(str(ws), {"palettes": "ShowB", "rhythm": "ShowA"}, "blend")
    assert LY.load_style(str(ws), "blend")["kind"] == "composed" and "blend" not in LY.load_series_layers(str(ws))   # composed styles are not shows
    rep = LY.report_es(str(ws))
    assert "Capas del estudio" in rep and "blend" in rep
    # a show learned in another project joins the studio
    other = tmp_path / "other"
    LY.save_layers(str(other), "ShowC", LY.build_series_layers([A()]))
    assert LY.import_series(str(other), str(ws), "c_") == ["c_ShowC"]
    r2 = LY.build(str(ws))
    assert r2["series"] == ["ShowA", "ShowB", "c_ShowC"]
    with pytest.raises(FileNotFoundError, match="blend|disponibles"):
        LY.load_style(str(ws), "nope")


def _clip(path, secs=6, fps=8, color=(200, 40, 40)):
    import imageio
    import numpy as np

    w = imageio.get_writer(path, fps=fps, macro_block_size=1)
    for t in range(secs * fps):
        f = np.zeros((72, 120, 3), np.uint8)
        f[:] = (235, 235, 215) if t < secs * fps // 2 else (60, 90, 160)
        x = (t * 3) % 90
        f[20:50, x : x + 22] = color
        w.append_data(f)
    w.close()


def test_learning_panel_builds_layers_for_every_show_and_the_studio(tmp_path):
    from studio import learning as L
    from studio import pipeline as PL

    studio = tmp_path / "Studio"
    for show, col in (("ShowA", (200, 40, 40)), ("ShowB", (40, 170, 80))):
        (studio / show / "S01").mkdir(parents=True)
        for ep in ("E01", "E02"):
            _clip(str(studio / show / "S01" / f"{ep}.mp4"), color=col)
    ws = str(tmp_path / "ws")
    ctx = {"input": str(studio), "ws": ws, "device": "cpu", "workers": 1, "vision": False}
    keys = ("sources", "scan", "corpus", "profile", "overlays", "analysis", "layers")
    outs = PL.run([p for p in L.LEARNING_PHASES if p.key in keys], ctx)
    assert [o.key for o in outs] == list(keys)
    assert all(o.status in ("ok", "partial") for o in outs), [(o.key, o.status, o.note) for o in outs]
    assert "2 serie(s)" in outs[-1].note and "distancia de paleta" in outs[-1].note
    for scope in ("ShowA", "ShowB", "_studio"):
        assert all(os.path.exists(os.path.join(ws, "layers", scope, f"{l}.json")) for l in LY.LAYERS)
    assert os.path.exists(os.path.join(ws, "silhouettes")) and any(f.endswith(".sil.npz") for f in os.listdir(os.path.join(ws, "silhouettes")))
    st = LY.load_style(ws, "_studio")
    assert st["kind"] == "studio" and st["spread"]["series"] == 2 and st["style_prompt"].startswith("cartoon style")
    # an episode can be written in the studio style
    from studio import episode as EP

    ctx2 = EP.make_ctx(ws, os.path.join(ws, "episodes", "e1"), "INT. CASA\n\nZORRO entra.\n\nZORRO\nHola\n", style_layers="_studio")
    outs2 = PL.run(EP.EPISODE_PHASES, ctx2)
    assert not any(o.status == "error" for o in outs2), [(o.key, o.note) for o in outs2]
    prompts = open(os.path.join(ws, "episodes", "e1", "prompts.jsonl")).read()
    assert st["style_prompt"].split(",")[0] in prompts and "subtitles" in prompts   # the layer style and the no-text negative prompt


def test_style_prompt_is_english_even_though_the_analysis_is_spanish():
    L = LY.merge_layers({"A": LY.build_series_layers([A()])})
    sp = LY.style_from_layers(L)["style_prompt"]
    assert "close-up" in sp and "primer plano" not in sp and "fija" not in sp and "estático" not in sp
