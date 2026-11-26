"""Native story reading (no Node): same schema the script-hypercartoon bridge returns, computed from the Doc."""
from typing import Dict, List

from studio.emotion.engine import lexicon_appraisal
from studio.story.convert import Doc
from studio.story.pacing import scene_seconds


def read(doc: Doc) -> Dict:
    n = len(doc.scenes)
    dur = [scene_seconds(s.action_words, s.lines, s.requested) for s in doc.scenes]
    raw = []
    for s in doc.scenes:
        ap = lexicon_appraisal(" ".join([s.action_text] + [t for _, t in s.lines]))
        raw.append(100.0 * (0.6 * ap["arousal"] + 0.4 * max(0.0, -ap["valence"])))
    # smooth with neighbours so one shouted line is a bump, not a spike
    tension = [round(0.25 * raw[max(0, i - 1)] + 0.5 * raw[i] + 0.25 * raw[min(n - 1, i + 1)], 1) for i in range(n)] if n else []
    chars: Dict[str, dict] = {}
    for i, s in enumerate(doc.scenes, 1):
        for c, t in s.lines:
            d = chars.setdefault(c, {"name": c, "cues": 0, "words": 0, "firstScene": i, "lastScene": i, "scenes": set()})
            d["cues"] += 1
            d["words"] += len(t.split())
            d["lastScene"] = i
            d["scenes"].add(i)
    tot = sum(c["words"] for c in chars.values()) or 1
    characters = [dict(c, scenes=len(c["scenes"]), share=round(c["words"] / tot, 3)) for c in sorted(chars.values(), key=lambda c: -c["words"])]
    total = sum(dur) or 1.0
    acts, acc, part = [], 0.0, 0
    bounds = [0.25, 0.5, 0.75, 1.01]
    start = 1
    for i, d in enumerate(dur, 1):
        acc += d
        if acc / total >= bounds[part] or i == n:
            seg = tension[start - 1 : i]
            peak = start + max(range(len(seg)), key=lambda k: seg[k]) if seg else None
            acts.append({"part": ["I", "IIa", "IIb", "III"][part], "scenes": [start, i], "peakScene": peak})
            start, part = i + 1, min(part + 1, 3)
    scenes = [{"index": i, "place": s.place, "intExt": s.int_ext, "time": s.time, "cast": sorted({c for c, _ in s.lines}),
               "tension": tension[i - 1], "seconds": dur[i - 1], "dialogueShare": 0.0} for i, s in enumerate(doc.scenes, 1)]
    return {"source": "native", "stats": {"scenes": n, "seconds": total, "speakers": len(chars)}, "scenes": scenes,
            "characters": characters, "acts": acts, "tension": tension,
            "places": [{"place": p, "scenes": [i for i, s in enumerate(doc.scenes, 1) if s.place == p]} for p in sorted({s.place for s in doc.scenes if s.place})]}


def threads(reading: Dict) -> List[dict]:
    n = reading["stats"]["scenes"]
    out = []
    if n >= 4:
        cut = max(1, int(round(n * 0.75)))
        for c in reading["characters"]:
            if c["cues"] >= 2 and c["lastScene"] <= cut and c["firstScene"] <= n // 2:
                out.append({"kind": "vanished character", "subject": c["name"], "weight": round(min(1.0, c["share"] * 2), 2),
                            "evidence": [f"habla en las escenas {c['firstScene']}–{c['lastScene']} y desaparece antes del final"]})
        t = reading["tension"]
        if t and t[-1] >= 0.8 * max(t) and max(t) > 40:
            out.append({"kind": "tension left high", "subject": "final", "weight": 0.6,
                        "evidence": [f"la última escena mantiene tensión {t[-1]:.0f} (pico {max(t):.0f})"]})
    return out
