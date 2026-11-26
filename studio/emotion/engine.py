"""Per-character emotional state across a script, via the vendored emotions-hypercartoon kernel (Node >= 18).

Protocol: studio/emotion/runner.mjs keeps one emotions-hypercartoon instance per character. A line spoken by S is *heard* by every
other character present (their state changes); S's expressed emotion = S's current state blended with the line's own
appraisal. Output per line: valence / arousal / dominance in [-1,1], a label and an expression word for the prompt."""
import json
import os
import shutil
import subprocess
from typing import Dict, List, Optional, Sequence, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

_POS = {"te quiero", "gracias", "genial", "feliz", "amor", "bien", "bravo", "love", "thanks", "great", "happy", "yay", "ja", "jaja", "wow"}
_ANGER = {"odio", "inutil", "inútil", "idiota", "estupido", "estúpido", "no sirves", "cállate", "callate", "hate", "stupid", "shut up", "maldito"}
_SAD = {"triste", "mal", "muerte", "nunca", "sad", "alone", "solo", "lloro", "cry", "perdi", "perdí"}
_FEAR = {"miedo", "afraid", "scared", "socorro", "ayuda", "help"}
_HI = {"!", "¡", "grita", "corre", "rápido", "rapido", "ayuda", "help", "run", "now", "ya"}


def lexicon_appraisal(text: str) -> Dict[str, float]:
    """Tiny dependency-free valence/arousal estimate; the fallback and the 'own line' term of the blend."""
    t = text.lower()
    pos, ang, sad, fear = (sum(w in t for w in s) for s in (_POS, _ANGER, _SAD, _FEAR))
    neg = ang + sad + fear
    ar = 0.15 * t.count("!") + 0.1 * t.count("¡") + 0.2 * (text.isupper() and len(text) > 3) + 0.15 * sum(w in t for w in _HI)
    ar += 0.3 * ang + 0.25 * fear - 0.1 * sad  # insults and fear are high-arousal, sadness is low
    return {"valence": max(-1.0, min(1.0, 0.45 * (pos - neg))), "arousal": max(0.0, min(1.0, 0.2 + ar + 0.1 * pos)),
            "dominance": max(-1.0, min(1.0, 0.3 * ang - 0.3 * fear))}


def express_word(v: float, a: float, d: float = 0.0, label: Optional[str] = None) -> str:
    """Quadrant of the valence/arousal plane -> a word a video prompt can use."""
    if label and label not in ("neutral", "grounded_baseline"):
        m = {"frustration": "angry", "surprise": "surprised", "joy": "joyful", "sadness": "sad", "fear": "scared",
             "anger": "angry", "disgust": "disgusted", "compassion": "tender", "nostalgia": "wistful"}
        if label in m:
            return m[label]
    if abs(v) < 0.12 and a < 0.45:
        return "calm"
    if v >= 0.12:
        return "excited and happy" if a >= 0.55 else "content"
    return "angry" if (a >= 0.55 and d >= -0.1) else "scared" if a >= 0.55 else "sad"


class EmotionBridge:
    def __init__(self, src: Optional[str] = None, timeout: float = 20.0):
        self.src = src or os.environ.get("HYPERCARTOON_EMOTIONS") or os.path.join(ROOT, "vendor", "emotions-hypercartoon", "src", "index.js")
        if not shutil.which("node"):
            raise RuntimeError("Node.js (>=18) is required for emotions-hypercartoon")
        if not os.path.exists(self.src):
            raise RuntimeError(f"emotions-hypercartoon not found at {self.src}")
        self.p = subprocess.Popen(["node", os.path.join(HERE, "runner.mjs")], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, env=dict(os.environ, EMOTIONS_SRC=self.src))
        self.timeout = timeout

    def step(self, character: str, text: str, speaker: str = "other", personality: Optional[dict] = None) -> dict:
        self.p.stdin.write(json.dumps({"character": character, "text": text, "speaker": speaker,
                                       "personality": personality or {}}) + "\n")
        self.p.stdin.flush()
        while True:
            line = self.p.stdout.readline()
            if not line:
                raise RuntimeError("emotions-hypercartoon process ended unexpectedly")
            if line.startswith("@@"):
                r = json.loads(line[2:])
                if not r.get("ok"):
                    raise RuntimeError(r.get("error"))
                return r

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(timeout=5)
        except Exception:
            self.p.kill()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class LexiconBridge:
    """Same interface, no Node: state = exponentially smoothed appraisal of what the character hears."""

    def __init__(self):
        self.state: Dict[str, Dict[str, float]] = {}

    def step(self, character, text, speaker="other", personality=None):
        a = lexicon_appraisal(text)
        s = self.state.setdefault(character, {"valence": 0.0, "arousal": 0.2, "dominance": 0.0})
        for k in s:
            s[k] = 0.7 * s[k] + 0.3 * a[k]
        return {"ok": True, "vector": dict(s), "dominant": None, "tags": [], "gestalt": None}

    def close(self):
        pass


def make_bridge(kind: str = "auto", src: Optional[str] = None):
    if kind in ("auto", "emotions"):
        try:
            return EmotionBridge(src), "emotions"
        except Exception as e:
            if kind == "emotions":
                raise
            print(f"[emotion] emotions-hypercartoon unavailable ({e}); using lexicon fallback")
    return LexiconBridge(), "lexicon"


def measure_dialogue(lines: Sequence[Tuple[str, str]], bridge, cast: Optional[Sequence[str]] = None,
                     personalities: Optional[Dict[str, dict]] = None, own_weight: float = 0.4) -> List[dict]:
    """lines = [(CHARACTER, text)] in story order. Returns one emotion dict per line (same order).
    A character's state only changes by *hearing* others, so a speaker with nobody speaking before them is neutral
    plus the appraisal of their own words (own_weight)."""
    present = list(dict.fromkeys(list(cast or []) + [c for c, _ in lines]))
    personalities = personalities or {}
    last: Dict[str, dict] = {}  # latest engine reply per listening character
    out = []
    for speaker, text in lines:
        cur = last.get(speaker) or {}
        vec = cur.get("vector") or {"valence": 0.0, "arousal": 0.2, "dominance": 0.0}
        own = lexicon_appraisal(text)
        v = (1 - own_weight) * vec["valence"] + own_weight * own["valence"]
        a = (1 - own_weight) * vec["arousal"] + own_weight * own["arousal"]
        d = (1 - own_weight) * vec.get("dominance", 0.0) + own_weight * own["dominance"]
        out.append({"character": speaker, "valence": round(v, 3), "arousal": round(a, 3), "dominance": round(d, 3),
                    "label": cur.get("dominant"), "word": express_word(v, a, d, cur.get("dominant")),
                    "tags": cur.get("tags", [])})
        for listener in present:
            if listener != speaker:
                last[listener] = bridge.step(listener, text, speaker=speaker, personality=personalities.get(listener))
    return out
