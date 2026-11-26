import os
import numpy as np
import pytest

from studio import audio, corpus as C
from studio.absorb import absorb_corpus
from studio.characters import OnlineClusterer, Registry, av_overlap
from studio import script as S

rng = np.random.default_rng(0)


def _dir(k, d=32):
    v = np.zeros(d)
    v[k] = 1.0
    return v


def test_corpus_layouts():
    r = "/x/Show"
    assert C.parse_episode(f"{r}/S02/E07.mp4", r) == ("Show", 2, 7)
    assert C.parse_episode(f"{r}/Temporada 3/cap_5.mp4", r) == ("Show", 3, 5)
    assert C.parse_episode(f"{r}/1x03.mkv", r)[1:] == (1, 3)
    assert C.parse_episode(f"{r}/S01E12 - title.mp4", r)[1:] == (1, 12)
    assert C.parse_episode(f"{r}/random.mp4", r)[1] == 1


def test_clusterer_identity_across_noise():
    cl = OnlineClusterer(0.8)
    ids = [cl.add(_dir(k % 3) + 0.05 * rng.normal(size=32)) for k in range(30)]
    assert len(set(ids)) == 3 and ids[0] == ids[3] == ids[27]


def test_voice_assignment_by_lift_across_episodes():
    """Two characters, A speaks while A on screen; B on screen almost always (high base rate) but silent."""
    reg = Registry()
    for ep in range(4):
        va, vb = _dir(0) + .05 * rng.normal(size=32), _dir(1) + .05 * rng.normal(size=32)
        spk_a, spk_b = _dir(10) + .05 * rng.normal(size=32), _dir(11) + .05 * rng.normal(size=32)
        iv = {1: [(0, 20)], 2: [(0, 60)]}           # A on screen 0-20, B whole time
        speech = [(2, 8, spk_a), (4, 7, spk_a), (30, 36, spk_b), (40, 46, spk_b), (10, 15, spk_a)]
        reg.add_episode(f"ep{ep}", [1, 1], 60, {1: va, 2: vb}, {1: "fox", 2: "owl"}, iv, speech)
    reg.consolidate()
    chars = {c["kind"]: c for c in reg.characters()}
    assert len(chars) == 2 and chars["fox"]["episodes"] == 4
    # fox is the one that speaks speaker-A's voice; owl's voice must be the other speaker (B)
    assert chars["fox"]["voice_id"] != chars["owl"]["voice_id"]
    assert chars["fox"]["voice_id"] is not None


def test_registry_roundtrip_and_incremental(tmp_path):
    f = tmp_path / "e1.mp4"
    f.write_bytes(b"1")
    reg = Registry()
    ep = [{"path": str(f), "duration": 30.0}]
    tr = lambda p: (np.zeros((1, 2, 2), np.uint8), {1: "fox"})
    em = lambda p, l: ({1: _dir(0)}, {1: [(0.0, 20.0)]})
    sp = lambda p: [(1, 5, _dir(9))]
    assert absorb_corpus(ep, reg, tr, em, sp) == {"new": 1, "skipped": 0}
    reg.save(str(tmp_path / "r.json"))
    reg2 = Registry.load(str(tmp_path / "r.json"))
    assert absorb_corpus(ep, reg2, tr, em, sp) == {"new": 0, "skipped": 1}  # adding season 2 later costs only new eps
    assert reg2.presence[1] == 20.0


def test_vad_and_voice_embedding_separate_speakers():
    sr = 16000
    t = np.arange(int(1.0 * sr)) / sr
    voice = lambda f0: sum(np.sin(2 * np.pi * f0 * k * t) / k for k in range(1, 12)).astype(np.float32) * 0.2
    wave = np.concatenate([np.zeros(sr // 2), voice(110), np.zeros(sr // 2), voice(250), np.zeros(sr // 2)]).astype(np.float32)
    wave += 0.001 * rng.normal(size=len(wave)).astype(np.float32)
    segs = audio.energy_vad(wave, sr)
    assert len(segs) == 2
    e = [audio.logmel_embedding(wave[int(a * sr):int(b * sr)]) for a, b in segs]
    e2 = audio.logmel_embedding(np.concatenate([voice(110)]) * 1.0)
    cos = lambda a, b: a @ b / np.linalg.norm(a) / np.linalg.norm(b)
    assert all(np.isfinite(x).all() for x in e)
    assert cos(e[0], e2) > cos(e[1], e2)  # same pitch is closer than a different pitch


def test_dialogue_script_uses_cast_and_voices():
    src = "EXT. FOREST\n[6s] A fox meets an owl.\nFOX: Hello there!\nOWL: Who goes?\n"
    sc = S.parse_script(src, 3.0, known=set())
    assert sc[0].lines == [("FOX", "Hello there!"), ("OWL", "Who goes?")] and sc[0].new_scene
    segs, voices = S.to_segments(sc, "cartoon", {"FOX": "Fox, a fox character"})
    assert len(segs) == 2 and "Fox, a fox character" in segs[0]["text"]
    assert [len(v) for v in voices] == [1, 1]
