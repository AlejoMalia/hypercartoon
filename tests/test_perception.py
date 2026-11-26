import numpy as np

from hypercartoon.perception import coherence_report, load_labelmaps, save_labelmaps
from hypercartoon.perception.associate import track_instances
from hypercartoon.perception.labelmap import masks_to_labelmap


def _moving_square(T=12, H=60, W=90, jump_at=None, vanish=None):
    lab = np.zeros((T, H, W), np.uint8)
    for t in range(T):
        if vanish and t in vanish:
            continue
        x = 5 + 3 * t + (30 if jump_at is not None and t >= jump_at else 0)
        lab[t, 20:30, x : x + 10] = 1
    return lab


def test_smooth_beats_broken():
    good = coherence_report(_moving_square())
    teleport = coherence_report(_moving_square(jump_at=6))
    gappy = coherence_report(_moving_square(vanish={4, 5}))
    assert good["coherence"] > teleport["coherence"]
    assert good["coherence"] > gappy["coherence"]
    assert good["persistence"] == 1.0 and gappy["persistence"] < 1.0


def test_roundtrip_and_resize(tmp_path):
    m = {1: np.zeros((4, 120, 180), bool)}
    m[1][:, 40:80, 60:120] = True
    lab = masks_to_labelmap(m)
    assert lab.shape == (4, 60, 90) and lab.max() == 1
    p = str(tmp_path / "a.npz")
    save_labelmaps(p, lab, {1: "cat"})
    lab2, names = load_labelmaps(p)
    assert (lab == lab2).all() and names == {1: "cat"}


def test_associate_keeps_identity():
    T, frames = 8, []
    for t in range(T):
        a = np.zeros((2, 60, 90), bool)
        a[0, 10:20, 2 * t : 2 * t + 10] = True
        a[1, 40:50, 70 - 2 * t : 80 - 2 * t] = True
        frames.append(a)
    lab = track_instances(frames)
    assert set(np.unique(lab)) == {0, 1, 2}
    assert coherence_report(lab)["id_churn"] == 0.0
