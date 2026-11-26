import io
import json
import os
import sys
import types

import imageio
import numpy as np
import pytest
from scipy.ndimage import gaussian_filter

from studio.analysis import camera as CAM
from studio.analysis import color as CL
from studio.analysis import dialogue as DLG
from studio.analysis import elements as EL
from studio.analysis import framing as FR
from studio.analysis import scenes as SC
from studio.analysis import video as AV

rng = np.random.default_rng(0)
TEX = gaussian_filter(rng.random((400, 1200)), 2.0)
TEX = (TEX - TEX.min()) / np.ptp(TEX)


def crop(cx, cy, scale=1.0, w=96, h=54):
    sw, sh = w / scale, h / scale
    ys = np.clip(np.linspace(cy - sh / 2, cy + sh / 2, h), 0, 399).astype(int)
    xs = np.clip(np.linspace(cx - sw / 2, cx + sw / 2, w), 0, 1199).astype(int)
    return TEX[np.ix_(ys, xs)].astype(np.float32)


def classify(frames):
    ps = [CAM.pair_motion(a, b, use_cv2=False) for a, b in zip(frames, frames[1:])]
    return CAM.classify(ps, (96, 54), fps_eff=4)


# ---- camera ----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name,frames,expect", [
    ("pan right", [crop(200 + 2 * i, 200) for i in range(10)], "paneo derecha"),
    ("pan left", [crop(300 - 2 * i, 200) for i in range(10)], "paneo izquierda"),
    ("tilt up", [crop(300, 250 - i) for i in range(10)], "tilt arriba"),
    ("tilt down", [crop(300, 150 + i) for i in range(10)], "tilt abajo"),
    ("zoom in", [crop(300, 200, 1 + 0.04 * i) for i in range(10)], "zoom/dolly in"),
    ("zoom out", [crop(300, 200, 1.4 - 0.04 * i) for i in range(10)], "zoom/dolly out"),
    ("static", [crop(300, 200) for _ in range(10)], "fija"),
])
def test_camera_movement_directions(name, frames, expect):
    assert classify(frames)["label"] == expect


def test_shake_flat_background_and_foreground_motion():
    r = np.random.default_rng(5)
    shake = classify([crop(300 + int(r.integers(-3, 4)), 200 + int(r.integers(-3, 4))) for _ in range(10)])
    assert shake["label"] == "temblor / cámara en mano"
    flat = np.full((54, 96), 0.5, np.float32)
    assert CAM.classify([CAM.pair_motion(flat, flat * 0 + 0.5 + 0.2 * (i % 2), use_cv2=False) for i in range(5)], (96, 54), 4)["label"] in ("indeterminada", "fija")
    # a small object moves over a still textured background: the background wins (robust fit) -> static camera
    frames = []
    for i in range(10):
        f = crop(300, 200).copy()
        f[20:30, 10 + 5 * i : 20 + 5 * i] = 1.0
        frames.append(f)
    assert classify(frames)["label"] == "fija"


def test_dense_flow_backend_is_used_when_cv2_exists(monkeypatch):
    fake = types.ModuleType("cv2")
    fake.calcOpticalFlowFarneback = lambda a, b, *args: np.dstack([np.full(a.shape, -2.0), np.zeros(a.shape)])  # content moves left 2 px
    monkeypatch.setitem(sys.modules, "cv2", fake)
    m = CAM.pair_motion(crop(200, 200), crop(202, 200), use_cv2=True)
    assert m["tx"] == pytest.approx(-2.0, abs=1e-6) and abs(m["zoom"]) < 1e-6


# ---- framing, elements, scenes ---------------------------------------------------------------------------------
def _cartoon():
    f = np.full((180, 320, 3), (240, 230, 200), np.uint8)
    f[30:156, 50:114] = (220, 60, 60)      # character: 64x126 px
    f[140:170, 220:260] = (60, 60, 200)    # prop
    return f


def test_blob_detector_measures_area_position_and_space():
    els = EL.BlobDetector().detect(_cartoon())
    assert len(els) == 2 and els[0]["area"] == pytest.approx(64 * 126 / (320 * 180), rel=0.05)
    c = FR.composition(els)
    assert c["shot_type"] == "plano medio" and c["subject"]["cell"] == "medio-izquierda" and c["subject"]["height_pct"] == pytest.approx(70, abs=2)
    assert c["coverage_pct"] == pytest.approx(100 * (64 * 126 + 40 * 30) / (320 * 180), abs=1.5) and c["free_space_pct"] + c["coverage_pct"] == pytest.approx(100)
    assert c["occupancy_3x3"][1][0] > 0.3 and c["occupancy_3x3"][0][2] == 0       # left-middle busy, upper-right empty


def test_shot_types_thirds_and_labelled_characters():
    assert [FR.shot_type(x) for x in (0.9, 0.6, 0.3, 0.1, None)] == ["primer plano", "plano medio", "plano completo", "plano general", "plano de ambiente (sin personaje)"]
    assert FR.third_cell(0.1, 0.9) == {"horizontal": "izquierda", "vertical": "abajo", "cell": "abajo-izquierda"}
    assert FR.power_point_distance(1 / 3, 2 / 3) == pytest.approx(0.0) and FR.power_point_distance(0.5, 0.5) > 0.1
    els = [{"label": "person", "score": .9, "bbox": [0.1, 0.1, 0.3, 0.95], "area": 0.12}, {"label": "table", "score": .8, "bbox": [0.5, 0.6, 0.9, 0.95], "area": 0.14}]
    c = FR.composition(els)
    assert c["subject_source"] == "personajes detectados" and c["shot_type"] == "primer plano" and c["n_characters"] == 1
    assert FR.composition([])["shot_type"] == "plano de ambiente (sin personaje)"
    inv = EL.inventory([els, els])
    assert inv[0]["label"] == "table" and inv[0]["keyframes"] == 2 and {e["label"] for e in inv} == {"person", "table"}


def test_detector_factory_and_missing_dependencies():
    assert EL.get_detector("blobs").name == "blobs"
    with pytest.raises(ValueError):
        EL.get_detector("dino")                                  # needs prompts
    if not EL._has("ultralytics"):
        with pytest.raises(ImportError):
            EL.YoloDetector()


def test_scene_grouping_keeps_shot_reverse_shot_together():
    a = {"palette": [[200, 50, 50]], "brightness": .6}
    b = {"palette": [[20, 30, 200]], "brightness": .3}
    assert SC.group_scenes([a, dict(a), b, dict(a), dict(b)]) == [0, 0, 1, 0, 1]     # A A B A B: the cut back to A rejoins scene 0 (lookback), the last B rejoins scene 1


# ---- dialogue ------------------------------------------------------------------------------------------------------------
SHOTS = [{"start": 0.0, "end": 4.0}, {"start": 4.0, "end": 9.0}, {"start": 9.0, "end": 12.0}]


def test_dialogue_is_labelled_with_time_shot_scene_and_cuts():
    segs = [{"start": 1.0, "end": 2.5, "text": "Hola", "speaker": "A"}, {"start": 3.5, "end": 5.0, "text": "cruza un corte", "speaker": "B"},
            {"start": 10.0, "end": 11.0, "text": "adiós", "speaker": None}]
    items = DLG.label_dialogue(segs, SHOTS, [0, 0, 1])
    assert [i["shot"] for i in items] == [0, 1, 2] and [i["scene"] for i in items] == [0, 0, 1]
    assert items[1]["crosses_cut"] and items[1]["shots"] == [0, 1] and items[1]["shot_offset_s"] == pytest.approx(-0.5)
    assert items[0]["timecode"] == "00:00:01.0–00:00:02.5" and items[0]["shot_offset_s"] == pytest.approx(1.0)
    srt = DLG.to_srt(items)
    assert "1\n00:00:01,000 --> 00:00:02,500\n[E1 · T1 · A] Hola" in srt and "[E2 · T3 · ?] adiós" in srt
    by = DLG.by_scene(items)
    assert by[0]["lines"] == 2 and by[0]["speakers"] == ["A", "B"] and by[1]["words"] == 1
    assert DLG.timecode(3725.5) == "01:02:05.5" and DLG.timecode(1.25, srt=True) == "00:00:01,250"


def test_speakers_without_a_diarizer_come_from_clustering_the_voices():
    sr = 16000

    def voice(f0, secs=1.2):
        t = np.arange(int(sr * secs)) / sr
        ph = 2 * np.pi * np.cumsum(f0 * (1 + 0.1 * np.sin(2 * np.pi * 0.7 * t))) / sr
        return (sum(np.sin(k * ph) / k for k in range(1, 12)) * (0.5 + 0.5 * np.sin(2 * np.pi * 4 * t)) * 0.2).astype(np.float32)

    wave = np.concatenate([voice(110), voice(260), voice(112), voice(258)])
    segs = [{"start": i * 1.2, "end": (i + 1) * 1.2, "text": str(i), "speaker": None} for i in range(4)]
    out = DLG.assign_speakers(segs, wave, sr, thr=0.9)
    sp = [s["speaker"] for s in out]
    assert sp[0] == sp[2] and sp[1] == sp[3] and sp[0] != sp[1] and sp[0].startswith("SPEAKER_")
    keep = DLG.assign_speakers([{"start": 0, "end": 1, "text": "x", "speaker": "ZORRO"}], wave, sr)
    assert keep[0]["speaker"] == "ZORRO"                          # diarizer / known speakers are never overwritten


def test_transcript_backend_off_is_explicit_and_cached(tmp_path, monkeypatch):
    v = tmp_path / "a.mp4"
    v.write_bytes(b"x")
    r = DLG.get_transcript(str(v), str(tmp_path), "off")
    assert r["segments"] == [] and r["backend"] == "off"
    monkeypatch.setattr(DLG, "_backend_available", lambda n: True)
    monkeypatch.setattr(DLG, "transcribe_faster", lambda *a, **k: [{"start": 0.0, "end": 1.0, "text": "hola", "speaker": None, "words": []}])
    assert DLG.get_transcript(str(v), str(tmp_path), "faster")["segments"][0]["text"] == "hola"
    monkeypatch.setattr(DLG, "transcribe_faster", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must come from the cache")))
    assert DLG.get_transcript(str(v), str(tmp_path), "faster")["backend"] == "faster"


# ---- colour ----------------------------------------------------------------------------------------------------------------
def _frame(c1, c2, frac=0.7):
    f = np.zeros((20, 30, 3), np.uint8)
    f[:] = c1
    f[:, int(30 * frac):] = c2
    return f


def test_color_analysis_palettes_bands_rhythm_and_pictures(tmp_path):
    samples = [(float(t), _frame((220, 40, 40), (250, 240, 230)) if t < 6 else _frame((40, 60, 200), (20, 20, 30))) for t in range(12)]
    r = CL.analyze_colors(samples, [{"start": 0, "end": 6}, {"start": 6, "end": 12}], interval=3.0)
    top = {c["hex"]: c["pct"] for c in r["palette"][:4]}
    assert set(top) == {"#dc2828", "#283cc8", "#faf0e6", "#14141e"} and all(abs(v - p) < 1 for v, p in zip(sorted(top.values()), [15, 15, 35, 35]))
    assert abs(sum(c["pct"] for c in r["palette"]) - 100) < 1e-6
    assert r["per_shot"][0]["palette"][0]["rgb"] == [220, 40, 40] and r["per_shot"][1]["palette"][0]["rgb"] == [40, 60, 200]
    assert r["rhythm"]["max_change"] > 0.5 and r["rhythm"]["label"] == "paleta muy cambiante"
    still = CL.analyze_colors([(float(t), _frame((220, 40, 40), (250, 240, 230))) for t in range(12)], [{"start": 0, "end": 12}], 3.0)
    assert still["rhythm"]["label"] == "paleta estable" and still["rhythm"]["mean_change"] < 0.02
    assert abs(sum(b["pixel_pct"] for b in r["bands"].values()) - 100) < 1e-6 and r["bands"]["luces"]["palette"][0]["hex"] == "#faf0e6"
    assert r["metrics"]["warm_pct"] > 0 and "palette of" in CL.descriptor_es(r)
    paths = CL.write_pictures(r, samples, str(tmp_path))
    shapes = {k: imageio.imread(v).shape for k, v in paths.items()}
    assert set(shapes) == {"strip", "fingerprint", "hue_timeline", "treemap"} and shapes["strip"][1] == 960 and shapes["treemap"] == (360, 640, 3)
    strip = imageio.imread(paths["strip"])
    assert tuple(strip[0, 5]) == (220, 40, 40) and tuple(strip[0, 950]) == (40, 60, 200)    # warm first half, cool second half


def test_treemap_areas_are_proportional_and_kmeans_is_deterministic():
    rects = CL.squarify([60, 30, 10], 0, 0, 100, 100)
    assert [round(w * h) for _, _, w, h in rects] == [6000, 3000, 1000]
    pal = [{"rgb": [255, 0, 0], "pct": 60.0}, {"rgb": [0, 255, 0], "pct": 30.0}, {"rgb": [0, 0, 255], "pct": 10.0}]
    img = CL.treemap_image(pal, 200, 100)
    share = [(np.all(img == np.array(c["rgb"]), -1)).mean() for c in pal]
    assert share[0] > share[1] > share[2] and share[0] == pytest.approx(0.6, abs=0.08)
    px = np.concatenate([np.tile([200, 30, 30], (50, 1)), np.tile([30, 30, 200], (50, 1))])
    assert CL.dominant_colors(px, 2, seed=1) == CL.dominant_colors(px, 2, seed=1)
    assert CL.rgb_to_lab(np.array([255, 255, 255]))[0] == pytest.approx(100, abs=0.1) and CL.rgb_to_hsv(np.array([255, 0, 0]))[0] == 0


# ---- the whole thing -------------------------------------------------------------------------------------------------------
def _two_shot_video(path):
    fps, W, H = 16, 320, 180
    w = imageio.get_writer(path, fps=fps, macro_block_size=1)
    for t in range(fps * 3):                          # shot 1: warm textured background, camera pans right, small character on the left third
        x0 = 100 + 3 * t
        bg = TEX[:H, x0 : x0 + W]
        f = np.stack([bg * 120 + 120, bg * 90 + 60, bg * 40 + 30], -1).astype(np.uint8)
        f[70:150, 40:70] = (30, 30, 200)
        w.append_data(f)
    for t in range(fps * 3):                          # shot 2: cool flat background, static, big character
        f = np.zeros((H, W, 3), np.uint8)
        f[:] = (40, 120, 170)
        f[10:175, 110:210] = (230, 200, 40)
        w.append_data(f)
    w.close()


def test_analyze_video_end_to_end(tmp_path):
    v = str(tmp_path / "anim.mp4")
    _two_shot_video(v)
    r = AV.analyze_video(v, str(tmp_path / "out"), dialogue="off")
    s1, s2 = r["shots"]
    assert len(r["shots"]) == 2 and s1["camera"]["label"] == "paneo derecha" and s2["camera"]["label"] == "fija"
    assert s1["framing"]["shot_type"] == "plano completo" and s1["framing"]["subject"]["cell"] == "medio-izquierda"
    assert s2["framing"]["shot_type"] == "primer plano" and s2["framing"]["subject"]["height_pct"] > 85
    assert s2["framing"]["coverage_pct"] > 5 * s1["framing"]["coverage_pct"] and s1["scene"] != s2["scene"]
    assert r["summary"]["n_shots"] == 2 and r["summary"]["n_scenes"] == 2 and r["detector"] == "blobs"
    out = tmp_path / "out"
    names = sorted(os.listdir(out))
    assert "anim.analysis.json" in names and "anim.md" in names and "anim.color_strip.png" in names and "anim.color_treemap.png" in names
    j = json.load(open(out / "anim.analysis.json"))
    assert j["shots"][0]["camera"]["label"] == "paneo derecha" and j["color"]["palette"]
    md = (out / "anim.md").read_text(encoding="utf-8")
    assert "# Análisis de anim.mp4" in md and "| Plano | Cámara |" in md and "Banda de luminancia" in md and "heurísticas" in md


def test_analyze_video_with_dialogue_labels_it_by_shot(tmp_path, monkeypatch):
    v = str(tmp_path / "anim.mp4")
    _two_shot_video(v)
    monkeypatch.setattr(DLG, "get_transcript", lambda *a, **k: {"backend": "faster", "segments": [
        {"start": 1.0, "end": 2.0, "text": "hola", "speaker": "ZORRO", "words": []}, {"start": 4.0, "end": 5.5, "text": "adiós", "speaker": "BUHO", "words": []}]})
    r = AV.analyze_video(v, str(tmp_path / "o"), dialogue="auto")
    assert [d["shot"] for d in r["dialogue"]] == [0, 1] and r["summary"]["speakers"] == ["BUHO", "ZORRO"]
    assert (tmp_path / "o" / "anim.srt").exists() and "[E1 · T1 · ZORRO] hola" in (tmp_path / "o" / "anim.srt").read_text(encoding="utf-8")


def test_learning_panel_runs_the_analysis_and_feeds_profile_and_captions(tmp_path):
    from studio import tui

    show = tmp_path / "Show" / "S01"
    show.mkdir(parents=True)
    for e in (1, 2):
        _two_shot_video(str(show / f"E0{e}.mp4"))
    ws = tmp_path / "ws"
    outs, kit, ctx = tui.run_learning(str(tmp_path / "Show"), str(ws), io.StringIO(), workers=1)
    st = {o.key: o for o in outs}
    assert st["analysis"].status in ("ok", "partial") and "blobs" in st["analysis"].note
    prof = json.load(open(ws / "profile.json"))
    cin = prof["cinematography"]
    assert cin["shot_types"] and cin["camera"] and "mostly" in cin["prompt"] and cin["prompt"] in prof["style_prompt"]
    assert os.path.exists(ws / "analysis" / "index.json") and os.path.exists(ws / "analysis" / "E01.analysis.json")
    caps = json.load(open(ws / "dataset" / "captions.json"))
    assert any("static camera" in c or "camera pans right" in c for c in caps.values())          # captions now carry measured framing/camera
    assert any("medium shot" in c or "full shot" in c or "close-up" in c for c in caps.values())


def test_cli_analyze(tmp_path, capsys):
    from studio.cli import main

    v = str(tmp_path / "a.mp4")
    _two_shot_video(v)
    main(["analyze", v, "--out", str(tmp_path / "o"), "--dialogue", "off", "--detector", "blobs"])
    assert "2 tomas" in capsys.readouterr().out and (tmp_path / "o" / "a.analysis.json").exists()
