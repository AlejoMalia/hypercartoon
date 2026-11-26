import numpy as np
import pytest

from hypercartoon.models.cogvideo import control_data as CD


def test_labels_to_latent_nearest_and_time_mapping():
    lab = np.zeros((33, 60, 90), np.uint8)
    lab[:, :30, :45] = 1
    lab[16:, 30:, 45:] = 2
    out = CD.labels_to_latent(lab, CD.latent_frames(2.0))
    assert out.shape == (9, 30, 45) and CD.latent_frames(3.0) == 13
    assert out[0, 0, 0] == 1 and out[0, 29, 44] == 0 and out[8, 29, 44] == 2  # id 2 appears at pixel frame 16 = latent 4 on


def test_audio_features_and_character_features_and_roundtrip(tmp_path):
    sr = 16000
    t = np.arange(sr * 2) / sr
    wave = (np.sin(2 * np.pi * 200 * t) * (t > 1.0)).astype(np.float32)     # silence then tone
    ff = CD.frame_feats_from_audio(wave, sr, CD.latent_frames(2.0), speech=[(1.0, 2.0)], arousal=np.full(9, 0.7))
    assert ff.shape == (9, 4) and ff[:3, 0].sum() == 0 and ff[5:, 0].min() == 1 and ff[0, 1] < 0.05 < ff[8, 1] and abs(ff[0, 3] - 0.7) < 1e-6
    cf = CD.character_feats({1: np.ones((9, 2)), 5: np.ones((9, 2))}, max_characters=3, t_latent=9)
    assert cf.shape == (9, 4, 2) and cf[:, 1].min() == 1 and cf[:, 0].max() == 0  # id 5 > max is ignored
    p = str(tmp_path / "c.npz")
    CD.save_control(p, labels=np.ones((9, 30, 45), np.uint8), frame_feats=ff)
    z = CD.load_control(p)
    assert set(z) == {"labels", "frame_feats"} and z["labels"].dtype == np.int64 and np.allclose(z["frame_feats"], ff, atol=1e-2)
    with pytest.raises(ValueError):
        CD.save_control(str(tmp_path / "x.npz"))


def test_studio_builds_control_for_real_clips_and_for_regenerated_voices():
    from studio import control as SC

    sr = 16000
    t = np.arange(sr * 4) / sr
    wave = (np.sin(2 * np.pi * 180 * t) * (t > 2.0)).astype(np.float32)           # silence, then speech-like tone
    ff = SC.clip_control(wave, sr, 0.0, 3.0, [(2.0, 4.0)])
    assert ff.shape == (CD.latent_frames(3.0), 4) and ff[:7, 0].sum() == 0 and ff[9:, 0].min() == 1 and ff[:6, 1].max() < 0.1 < ff[11, 1]
    assert SC.clip_control(np.zeros(0, np.float32), sr, 0.0, 3.0, []).sum() == 0          # footage without audio -> zeros, still valid
    clip = (0.5, (np.sin(2 * np.pi * 200 * np.arange(sr) / sr) * 0.3).astype(np.float32))  # one 1 s line starting at 0.5 s
    emo = [{"valence": -0.4, "arousal": 0.9}]
    off = SC.video_control([clip], sr, 1, emo, emotion=False)
    on = SC.video_control([clip], sr, 1, emo, emotion=True)
    assert off.shape == on.shape == (13, 4) and off[:, 2:].sum() == 0               # emotion columns stay zero unless asked
    assert on[4, 3] == pytest.approx(0.9, abs=1e-2) and on[4, 2] == pytest.approx(-0.4, abs=1e-2) and on[0, 3] == 0
    assert on[2:7, 0].min() == 1 and on[0:2, 0].max() == 0 and on[8:, 0].max() == 0                            # speech only while the line is spoken
