import json
import os

import numpy as np

from studio.analysis import elements as EL
from studio.analysis import silhouettes as SIL


def _frame(boxes, bg=(235, 235, 220)):
    f = np.zeros((120, 200, 3), np.uint8)
    f[:] = bg
    for (x0, y0, x1, y1), c in boxes:
        f[y0:y1, x0:x1] = c
    return f


def test_kind_taxonomy():
    for label, kind in [("person", "person"), ("little girl", "person"), ("dog", "animal"), ("brown bear", "animal"), ("car", "vehicle"),
                        ("tree", "scenery"), ("chair", "object"), ("elemento", "unlabeled")]:
        assert SIL.kind_of(label) == kind, label
    assert SIL.is_agent("person") and SIL.is_agent("animal") and not SIL.is_agent("object")


def test_blob_elements_get_silhouette_kind_caption_and_track():
    f1 = _frame([((20, 30, 70, 100), (220, 40, 40)), ((130, 70, 160, 100), (50, 80, 220))])
    f2 = _frame([((26, 30, 76, 100), (220, 40, 40)), ((130, 72, 160, 102), (50, 80, 220))])   # both moved a little
    det = EL.BlobDetector()
    lab, maps = SIL.shot_elements([f1, f2], [det.detect(f1), det.detect(f2)])
    assert len(lab[0]) == 2 and len(lab[1]) == 2
    big = lab[0][0]
    assert big["kind"] == "unlabeled" and "red" in big["caption"] and "large" in big["caption"] or "medium" in big["caption"]
    assert {e["track"] for e in lab[0]} == {e["track"] for e in lab[1]}      # the same two things are followed across keyframes
    assert maps[0].shape == (120, 200) and set(np.unique(maps[0])) == {0, 1, 2}
    assert maps[0][60, 40] != 0 and maps[0][5, 5] == 0                        # silhouette on the figure, background is 0
    rows = SIL.summarize(lab)
    assert [r["track"] for r in rows] and all(r["presence"] == 1.0 for r in rows) and rows[0]["area_pct"] > rows[1]["area_pct"]


def test_labelled_detections_keep_their_names_and_kinds():
    f = _frame([((20, 30, 70, 100), (200, 120, 40))])
    dets = [{"label": "dog", "score": 0.9, "bbox": [0.1, 0.25, 0.35, 0.83], "area": 0.2, "mask": None}]
    el = SIL.label_frame(f, dets)[0]
    assert el["kind"] == "animal" and el["agent"] and "dog" in el["caption"] and el["color"]
    lm = SIL.label_map([el], f.shape[:2])
    assert lm[60, 40] == 1 and lm[5, 5] == 0                                   # without a mask the box is painted


def test_failing_captioner_falls_back_to_measured():
    class Bad:
        def caption(self, frame, el):
            raise RuntimeError("model down")

    f = _frame([((20, 30, 70, 100), (220, 40, 40))])
    el = SIL.label_frame(f, EL.BlobDetector().detect(f), Bad())[0]
    assert "red" in el["caption"]


def test_tracks_do_not_jump_between_different_labels_or_far_boxes():
    a = [{"label": "dog", "bbox": [0.1, 0.1, 0.3, 0.4]}, {"label": "cat", "bbox": [0.6, 0.1, 0.8, 0.4]}]
    b = [{"label": "dog", "bbox": [0.11, 0.1, 0.31, 0.4]}, {"label": "cat", "bbox": [0.1, 0.1, 0.3, 0.4]}]   # the cat "teleported"
    n = SIL.link_tracks([a, b])
    assert b[0]["track"] == a[0]["track"] and b[1]["track"] != a[1]["track"] and n == 3


def test_silhouette_files_roundtrip(tmp_path):
    f = _frame([((20, 30, 70, 100), (220, 40, 40))])
    lab, maps = SIL.shot_elements([f], [EL.BlobDetector().detect(f)])
    p = SIL.save_silhouettes(str(tmp_path / "ep.sil"), "ep.mp4", [{"index": 0, "times": [1.0], "maps": maps, "elements": SIL.summarize(lab)}])
    z = np.load(p + ".npz")
    assert z["s0000_k0"].shape == (120, 200)
    meta = json.load(open(p + ".json"))
    assert meta["shots"][0]["elements"][0]["caption"]


def test_analysis_writes_labelled_elements_and_silhouettes(tmp_path):
    import imageio

    from studio.analysis import video as AV

    p = str(tmp_path / "ep.mp4")
    w = imageio.get_writer(p, fps=8, macro_block_size=1)
    for i in range(48):
        w.append_data(_frame([((20 + i, 30, 70 + i, 100), (220, 40, 40))] if i < 24 else [((130, 40, 170, 100), (50, 80, 220))]))
    w.close()
    res = AV.analyze_video(p, str(tmp_path / "a"), dialogue="off", silhouettes_dir=str(tmp_path / "sil"))
    assert all("labelled" in s for s in res["shots"]) and any(s["labelled"] for s in res["shots"])
    assert os.path.exists(str(tmp_path / "sil" / "ep.sil.npz")) and os.path.exists(str(tmp_path / "sil" / "ep.sil.json"))
