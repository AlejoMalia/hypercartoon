import json
import os
import numpy as np

from studio.characters import OnlineClusterer
from studio.sound import analyze as A, mix as M
from studio.sound.bank import Bank, AudioAbsorber, build_bank
from studio.sound.speak import ScratchVoice, get_speaker

sr = 16000
rng = np.random.default_rng(0)
t = np.arange(sr * 4) / sr


def speech(f0=130, secs=4):
    tt = np.arange(sr * secs) / sr
    ph = 2 * np.pi * np.cumsum(f0 * (1 + 0.15 * np.sin(2 * np.pi * 0.7 * tt))) / sr
    return (sum(np.sin(k * ph) / k for k in range(1, 15)) * (0.5 + 0.5 * np.sin(2 * np.pi * 4 * tt)) * 0.2).astype(np.float32)


MUSIC = sum(np.sin(2 * np.pi * f * t) * 0.1 for f in (220, 277.2, 329.6, 440)).astype(np.float32)
NOISE = (rng.normal(size=len(t)) * 0.05).astype(np.float32)


def test_classifier_separates_four_kinds():
    r = lambda w: A.ratios(A.classify(w))
    assert r(speech())["speech"] > 0.9 and r(MUSIC)["music"] > 0.9 and r(NOISE)["ambient"] > 0.9
    assert r(np.zeros(len(t), np.float32) + 1e-5 * rng.normal(size=len(t)).astype(np.float32))["silence"] > 0.9


def test_pitch_tracks_speaker():
    assert abs(A.pitch_f0(speech(130)) - 130) < 12 and abs(A.pitch_f0(speech(220)) - 220) < 20


def test_scratch_voice_uses_reference_pitch_and_real_duration(tmp_path):
    M.write_wav(str(tmp_path / "ref.wav"), speech(200), sr)
    v = ScratchVoice()
    w = v.say("Hola, soy el zorro!", str(tmp_path / "ref.wav"))
    assert 0.8 < len(w) / v.sr < 4 and abs(A.pitch_f0(M._resample(w, v.sr, sr)) - 200) < 30
    assert len(v.say("una frase bastante mas larga que la anterior, de verdad.")) > len(v.say("hola"))


def test_no_speech_engine_names_leak():
    import studio.sound.speak as sp
    assert get_speaker("scratch").sr > 0 and "tts" not in " ".join(dir(sp)).lower().replace("chatterbox", "")


def test_bank_picks_clean_voice_refs_and_ambience(tmp_path):
    # one "episode": 0-4s voice A, 4-8s music, 8-16s noise bed, 16-20s voice B
    w = np.concatenate([speech(120), MUSIC, np.tile(NOISE, 2), speech(240)])
    ep = str(tmp_path / "ep1.wav")
    M.write_wav(ep, w, sr)
    ab = AudioAbsorber()
    segs = ab(ep)
    assert len(segs) == 2  # music segment rejected by the soundtrack classifier
    ab.save(str(tmp_path))
    cl = OnlineClusterer(0.9)
    for _, _, v in segs:
        cl.add(v)
    man = build_bank(str(tmp_path), cl)
    assert len(man["voices"]) == 2 and len(man["ambience"]) >= 1
    b = Bank(str(tmp_path))
    vid = next(iter(man["voices"]))
    assert os.path.exists(b.reference(int(vid))) and b.reference(99) == ""
    assert os.path.exists(b.ambience_wav())


def test_render_ducks_ambience_and_reports_overflow(tmp_path):
    bank = Bank(str(tmp_path))
    segs = [[{"character": "FOX", "voice_id": 1, "line": "hola, soy el zorro, y hoy voy a contarte una historia muy larga!"}], []]
    dlg, rep = M.render_dialogue(segs, bank, ScratchVoice(), 24000)
    assert rep["lines"] == 1 and rep["late_lines"] and rep["overflow_s"] >= 0
    bed = (rng.normal(size=len(dlg)) * 0.1).astype(np.float32)
    out = M.mix(dlg, bed, 24000)
    assert np.abs(out).max() <= 0.97 + 1e-6 and len(out) == len(dlg)
    g = M.duck_gain(dlg, 24000)
    active = np.convolve(np.abs(dlg), np.ones(2400) / 2400, "same") > 0.05
    assert g[active].mean() < 0.5 * g.max() and abs(g.max() - 10 ** (-24 / 20)) < 1e-6  # ~-9 dB under dialogue
