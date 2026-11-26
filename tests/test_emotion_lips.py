import shutil
import numpy as np
import pytest

from studio.emotion import prosody as P
from studio.emotion.engine import LexiconBridge, EmotionBridge, express_word, lexicon_appraisal, make_bridge, measure_dialogue
from studio.lips import visemes as V
from studio.lips.style import MouthStyle, apply_style, lag_of, learn_style
from studio.lips.sync import align_lines, audio_envelope, mouth_series_from_video, sync_score
from studio.sound.speak import ScratchVoice

rng = np.random.default_rng(1)
LINES = [("FOX", "Hola, soy el zorro!"), ("OWL", "Eres un inutil, no sirves para nada!"), ("FOX", "Perdona, te quiero mucho.")]


def test_lexicon_separates_anger_sadness_joy():
    anger, sad, joy = (lexicon_appraisal(t) for t in ("Idiota, no sirves para nada!", "Estoy triste, mal, solo", "Gracias, te quiero! genial"))
    assert anger["arousal"] > sad["arousal"] and anger["valence"] < 0 < joy["valence"]
    assert express_word(anger["valence"], anger["arousal"], anger["dominance"]) == "angry"
    assert express_word(sad["valence"], sad["arousal"]) == "sad" and "happy" in express_word(0.6, 0.8)


def test_measure_dialogue_lexicon_fallback():
    out = measure_dialogue(LINES, LexiconBridge())
    assert [o["character"] for o in out] == ["FOX", "OWL", "FOX"] and out[1]["word"] == "angry"
    assert out[2]["arousal"] != out[0]["arousal"]  # fox heard the insult before speaking again


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_emotions_bridge_live():
    bridge, kind = make_bridge("emotions")
    try:
        assert kind == "emotions"
        out = measure_dialogue(LINES, bridge)
        assert len(out) == 3 and all(-1 <= o["valence"] <= 1 and 0 <= o["arousal"] <= 1 for o in out)
        # persistence: the fox's state after hearing the insult differs from its first state
        assert out[2]["arousal"] != out[0]["arousal"] or out[2]["valence"] != out[0]["valence"]
    finally:
        bridge.close()


def test_prosody_arousal_relative_to_baseline():
    sr = 16000

    def voice(f0, amp, rate):
        t = np.arange(sr * 2) / sr
        ph = 2 * np.pi * np.cumsum(f0 * (1 + 0.1 * np.sin(2 * np.pi * 0.8 * t))) / sr
        return (sum(np.sin(k * ph) / k for k in range(1, 10)) * (0.5 + 0.5 * np.sin(2 * np.pi * rate * t)) * amp).astype(np.float32)

    b = P.Baseline()
    for _ in range(12):
        b.add(P.features(voice(120 + rng.normal() * 4, 0.2, 3.5)))
    calm, hot = b.arousal(P.features(voice(120, 0.2, 3.5))), b.arousal(P.features(voice(200, 0.5, 6)))
    assert hot > 0.75 and 0.3 < calm < 0.7 and b.arousal(P.features(voice(90, 0.1, 2.0))) < 0.3
    assert P.delivery_params(-0.5, 0.9)["rate"] > P.delivery_params(0.0, 0.1)["rate"]


def test_emotion_changes_delivery_of_the_voice():
    v = ScratchVoice()
    calm, hot = v.say("hola soy el zorro", emotion={"valence": 0, "arousal": 0.1}), v.say("hola soy el zorro", emotion={"valence": -0.5, "arousal": 0.95})
    assert len(hot) < len(calm)  # more aroused = faster


def test_visemes_follow_text_and_envelope():
    seq = [s for s, _ in V.text_to_visemes("mamá fue")]
    assert seq[0] == "MBP" and "AI" in seq and "FV" in seq
    tr = V.viseme_track("aaa mmm", 0, 1.0, 24)
    assert tr[:8].mean() > tr[-6:].mean()  # open vowels first, closed MBP after
    env = np.r_[np.zeros(10), np.ones(10)]  # voice only in the second half
    plain = V.viseme_track("mmm aaa", 0, 1.0, 24)
    warped = V.viseme_track("mmm aaa", 0, 1.0, 24, env, env_mix=0.9)
    assert warped[:12].mean() < plain[:12].mean()  # silent first half: lips stay closed until the voice starts


def test_style_learning_recovers_convention():
    fps = 24
    t = np.arange(fps * 20) / fps
    env = np.clip(np.sin(2 * np.pi * 3.2 * t) + 0.4, 0, None)
    env = env / env.max()
    lead = int(0.08 * fps)  # mouth moves 2 frames before the sound
    target = np.roll(env, -lead)
    levels = np.array([0, 0.4, 0.75, 1.0])
    q = levels[np.abs(target[:, None] - levels[None]).argmin(1)]
    held = np.repeat(q[::2], 2)[: len(q)]  # animated "on twos"
    st = learn_style(held, env, fps)
    assert st.hold_frames == 2 and 3 <= len(st.levels) <= 5 and 0.03 <= st.lead_s <= 0.13
    out = apply_style(np.linspace(0, 1, 48), st, fps)
    assert set(np.round(out, 2)) <= set(np.round(st.levels, 2))


def test_sync_score_and_alignment_fix_offset():
    fps, sr = 24, 16000
    amp = lambda t: 0.5 + 0.5 * np.sin(2 * np.pi * (2 * t + 3 * t ** 2))  # non-periodic chirp: unambiguous alignment

    def clip(dur):
        t = np.arange(int(dur * sr)) / sr
        return (np.sin(2 * np.pi * 150 * t) * amp(t)).astype(np.float32)

    mouth = np.zeros(fps * 6)
    for a, b in ((1.0, 1.6), (3.0, 3.7)):  # the mouth really opens here
        tt = np.arange(int(a * fps), int(b * fps)) / fps - a
        mouth[int(a * fps) : int(b * fps)] = amp(tt)
    clips = [(1.3, clip(0.6)), (3.3, clip(0.7))]  # dialogue was placed 0.3 s late
    shifts = align_lines(mouth, clips, sr, fps)
    assert all(abs(s + 0.3) < 0.1 for s in shifts), shifts

    def place(sh):
        w = np.zeros(sr * 6, np.float32)
        for (st, c), s in zip(clips, sh):
            w[int((st + s) * sr) : int((st + s) * sr) + len(c)] += c
        return audio_envelope(w, sr, fps)

    assert sync_score(mouth, place(shifts), fps)["score"] > sync_score(mouth, place([0, 0]), fps, 0.0)["score"]


def test_mouth_series_from_video_reacts_to_opening():
    frames = []
    for i in range(30):
        f = np.full((60, 80), 200, np.uint8)
        if (i // 3) % 2:  # dark opening in the lower-centre
            f[45:55, 30:50] = 20
        frames.append(f)
    s = mouth_series_from_video(frames)
    still = mouth_series_from_video([np.full((60, 80), 200, np.uint8)] * 30)
    assert s.std() > still.std() and abs(s.max() - 1.0) < 1e-6
