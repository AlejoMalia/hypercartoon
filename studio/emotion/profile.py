"""Per-voice delivery baselines from the corpus (how each character normally sounds), assigned by nearest voice centroid
so Registry merges are respected."""
import json
import os

import numpy as np

from studio.emotion.prosody import Baseline


def build_emotion_profile(ws: str, voice_clusterer) -> dict:
    path = os.path.join(ws, "audio_candidates.json")
    cands = json.load(open(path)).get("prosody", {})
    bases = {}
    for ep, segs in cands.items():
        for s in segs:
            v = np.asarray(s["vec"], float)
            vid = max(voice_clusterer.sums, key=lambda k: float(v @ voice_clusterer.centroid(k)), default=None)
            if vid is not None:
                bases.setdefault(vid, Baseline()).add(s["feat"])
    prof = {str(k): b.to_json() for k, b in bases.items()}
    json.dump(prof, open(os.path.join(ws, "emotion_profile.json"), "w"))
    return prof
