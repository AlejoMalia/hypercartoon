import functools
import http.server
import json
import os
import threading

import numpy as np
import pytest

from studio import voices as VX
from studio.audio import load_audio
from studio.sound.analyze import pitch_f0
from studio.sound.mix import write_wav
from studio.sound.speak import ScratchVoice

SR = 24000


@pytest.fixture(autouse=True)
def _builtin_voiceprint(monkeypatch):
    """These tests use synthetic talkers: pin the built-in descriptor even where speechbrain (ECAPA) is installed."""
    orig = VX.get_embedder
    monkeypatch.setattr(VX, "get_embedder", lambda kind="voiceprint", device="cpu": orig("voiceprint" if kind == "auto" else kind, device))


def voice(f0, seconds, seed=0, syl=0.19):
    """Synthetic talker: formant syllables at a fixed pitch with pauses, so utterances and speakers are well defined."""
    rng = np.random.default_rng(seed)
    sp = ScratchVoice(syllable=syl)
    out = []
    t = 0.0
    while t < seconds:
        n = int(rng.integers(8, 20))
        w = np.concatenate([sp._syl(f0 * (1 + 0.05 * np.sin(k)), ((800, 1200, 2800), (500, 1900, 2600), (300, 2300, 3000))[k % 3]) for k in range(n)])
        w = np.interp(np.linspace(0, len(w) - 1, int(len(w) * SR / sp.sr)), np.arange(len(w)), w)
        out += [w / (np.abs(w).max() + 1e-9) * 0.5, np.zeros(int(SR * rng.uniform(0.8, 1.4)))]
        t += len(out[-2]) / SR + len(out[-1]) / SR
    return np.concatenate(out).astype(np.float32)


def music(seconds, seed=1):
    t = np.arange(int(seconds * SR)) / SR
    return (0.2 * (np.sin(2 * np.pi * 262 * t) + np.sin(2 * np.pi * 330 * t) + np.sin(2 * np.pi * 392 * t)) * (1 + 0.3 * np.sin(2 * np.pi * 2 * t))).astype(np.float32)


def test_utterances_split_at_pauses_and_respect_the_limit():
    w = voice(120, 40)
    u = VX.utterances(w)
    assert len(u) >= 5 and all(1.5 <= b - a <= 12.0 + 1e-6 for a, b in u)
    assert not VX.speech_like(music(8)) and not VX.speech_like(np.random.default_rng(0).normal(0, 0.1, 8 * SR).astype(np.float32)) and VX.speech_like(w[: 6 * SR])


def test_quality_penalises_noise_and_clipping():
    clean = voice(120, 12)
    noisy = clean + np.random.default_rng(0).normal(0, 0.15, len(clean)).astype(np.float32)
    clipped = np.clip(clean * 6, -1, 1)
    q = [VX.quality(x) for x in (clean, noisy, clipped)]
    assert q[0]["score"] > q[1]["score"] and q[0]["score"] > q[2]["score"] and q[2]["clip"] > 0.01
    n = VX.normalize(clean)
    assert abs(float(np.sqrt((n ** 2).mean())) - 0.07) < 0.01 and np.abs(n).max() <= 0.95


def test_dominant_speaker_keeps_the_voice_and_drops_the_intruder(tmp_path):
    a, b = voice(110, 36, 1), voice(230, 8, 2)
    rec = np.concatenate([a[: len(a) // 2], b, a[len(a) // 2 :]])          # the intruder is in the middle
    cands = VX.prepare(rec, VX.get_embedder(), "mix")
    lo, hi = len(a) // 2 / SR, (len(a) // 2 + len(b)) / SR
    inside = [c for c in cands if lo + 0.5 < (c["start"] + c["end"]) / 2 < hi - 0.5]
    outside = [c for c in cands if not (lo - 0.5 < (c["start"] + c["end"]) / 2 < hi + 0.5)]
    assert inside and outside
    assert sum(c["kept"] for c in inside) / len(inside) <= 0.34 and sum(c["kept"] for c in outside) / len(outside) >= 0.8


def test_add_audio_builds_references_profile_and_rejects_music(tmp_path):
    lib = VX.VoiceLibrary(str(tmp_path))
    rec = np.concatenate([voice(110, 30, 3), music(8), voice(110, 12, 4)])
    p = lib.add_audio("Homer Simpson", [("a.wav", rec)], language="es", aliases=["HOMERO"])
    d = tmp_path / "voices" / "HOMER_SIMPSON"
    assert (d / "ref_primary.wav").exists() and (d / "ref_long.wav").exists() and (d / "profile.json").exists()
    assert p["seconds"] >= 15 and p["sufficiency"]["verdict"] in ("bueno", "óptimo") and 4 <= p["primary_seconds"] <= 14
    r = load_audio(str(d / "ref_long.wav"), SR)
    assert abs(float(np.sqrt((r[r != 0] ** 2).mean())) - 0.07) < 0.02                        # loudness normalised
    assert pitch_f0(load_audio(str(d / "ref_primary.wav"), 16000)) == pytest.approx(110, rel=0.15)
    assert lib.resolve("homer simpson") == "HOMER_SIMPSON" and lib.resolve("Homero") == "HOMER_SIMPSON" and lib.resolve("MARGE") is None
    assert VX.verdict(3.0)["verdict"] == "insuficiente" and VX.verdict(3.0)["missing_s"] == 2.0
    with pytest.raises(ValueError, match="habla"):
        lib.add_audio("Musica", [("m.wav", music(10))])


def test_adding_more_audio_keeps_the_same_voice_and_grows(tmp_path):
    lib = VX.VoiceLibrary(str(tmp_path))
    p1 = lib.add_audio("A", [("1", voice(110, 12, 5))])
    p2 = lib.add_audio("A", [("2", voice(110, 25, 6))])
    assert p2["seconds"] > p1["seconds"] and set(p2["sources"]) == {"1", "2"} and p2["created"] >= p1["created"]


def test_verify_tells_characters_apart(tmp_path):
    lib = VX.VoiceLibrary(str(tmp_path))
    lib.add_audio("HOMER", [("h", voice(110, 30, 7))])
    lib.add_audio("MARGE", [("m", voice(230, 30, 8))])
    own = lib.verify("HOMER", voice(110, 8, 9))
    other = lib.verify("HOMER", voice(230, 8, 10))
    assert own["verdict"] == "ok" and own["distance"] < other["distance"]
    assert other["verdict"].startswith("más parecida a MARGE")
    assert json.load(open(tmp_path / "voices" / "index.json"))["HOMER"]["verdict"]


def test_audio_from_any_source_a_folder_and_an_http_url(tmp_path):
    srv_dir = tmp_path / "web"
    srv_dir.mkdir()
    write_wav(str(srv_dir / "actor.wav"), voice(110, 30, 11), SR)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(srv_dir))
    handler.log_message = lambda *a: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    folder = tmp_path / "local"
    folder.mkdir()
    write_wav(str(folder / "a.wav"), voice(110, 14, 12), SR)
    lib = VX.VoiceLibrary(str(tmp_path / "ws"))
    try:
        p = lib.add_inputs("ACTOR", [str(folder), f"http://127.0.0.1:{srv.server_address[1]}/actor.wav"])
    finally:
        srv.shutdown()
    assert p["seconds"] >= 20 and len(p["sources"]) == 2 and not p["fetch_errors"]
    assert not os.path.exists(tmp_path / "ws" / "voices" / "ACTOR" / "_fetch")              # nothing but the clean references stays


def test_binding_prefers_clone_then_episode_voice_then_guide(tmp_path):
    lib = VX.VoiceLibrary(str(tmp_path))
    lib.add_audio("Homer", [("h", voice(110, 20, 13))], aliases=["Homero"])
    b = VX.binding(str(tmp_path), ["HOMERO", "BART", "MARGE"], {"BART": 7, "HOMERO": 3})
    assert b["HOMERO"]["voice_id"] == "clone:HOMER" and b["HOMERO"]["source"] == "clone"
    assert b["BART"] == {"voice_id": 7, "source": "corpus"} and b["MARGE"] == {"voice_id": None, "source": "guide"}
    from studio.sound.bank import Bank

    assert Bank(str(tmp_path)).reference("clone:HOMER").endswith("ref_primary.wav") and Bank(str(tmp_path)).reference("clone:NOBODY") == ""


def test_speaker_selection_and_missing_cloners():
    from studio.sound import speak as SK

    assert set(SK.available_cloners()) <= set(SK.CLONERS)
    if not SK.available_cloners():
        assert type(SK.get_speaker("auto")).__name__ == "ScratchVoice"
    with pytest.raises(ValueError, match="coqui"):
        SK.get_speaker("nope")


def test_episode_uses_each_characters_clone(tmp_path):
    """Learning panel -> clones added by name -> an episode whose lines follow each character's own reference voice."""
    from test_layers import _clip

    from studio import episode as EP
    from studio import learning as L
    from studio import pipeline as PL

    show = tmp_path / "Show" / "S01"
    show.mkdir(parents=True)
    _clip(str(show / "E01.mp4"))
    ws = str(tmp_path / "ws")
    PL.run([p for p in L.LEARNING_PHASES if p.key in ("sources", "scan", "corpus", "profile")], {"input": str(tmp_path / "Show"), "ws": ws, "device": "cpu", "workers": 1})
    lib = VX.VoiceLibrary(ws)
    lib.add_audio("HOMER", [("h", voice(105, 25, 14))])
    lib.add_audio("MARGE", [("m", voice(240, 25, 15))])
    script = "INT. COCINA - DIA\n\nHOMER entra.\n\nHOMER\nBuenos dias, familia.\n\nMARGE\nYa es mediodia.\n\nLISA\nHola a todos.\n"
    ctx = EP.make_ctx(ws, os.path.join(ws, "episodes", "e1"), script, speaker="scratch", device="cpu")
    outs = PL.run([p for p in EP.EPISODE_PHASES if p.key in ("story", "emotion", "plan", "voices")], ctx)
    assert not any(o.status == "error" for o in outs), [(o.key, o.note) for o in outs]
    bind = json.load(open(os.path.join(ws, "episodes", "e1", "voice_binding.json")))
    assert bind["HOMER"]["voice_id"] == "clone:HOMER" and bind["MARGE"]["source"] == "clone" and bind["LISA"]["source"] == "guide"
    side = json.load(open(os.path.join(ws, "episodes", "e1", "voices.json")))
    ids = {ln["character"]: ln["voice_id"] for video in side for seg in video for ln in seg}
    assert ids["HOMER"] == "clone:HOMER" and ids["MARGE"] == "clone:MARGE" and ids["LISA"] is None
    pitch = {}
    for _, rep in ctx["rendered"]:
        for (name, _), (_, w) in zip(rep["meta"], rep["clips"]):
            pitch[name] = pitch_f0(w.astype(np.float32), 24000)
    assert pitch["MARGE"] > 1.4 * pitch["HOMER"]                      # the guide voice follows each character's own reference
    note = next(o.note for o in outs if o.key == "voices")
    assert "clones: HOMER, MARGE" in note and note.startswith("parcial")
