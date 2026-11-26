"""Cross-episode character registry. Visual identity + voice identity learned online, then linked by
audio-visual co-occurrence. More episodes => sharper centroids and stronger links (evidence accumulates).
Pure numpy; embeddings come from pluggable backends."""
import json
import os
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np


def _unit(v) -> np.ndarray:
    v = np.asarray(v, dtype=np.float64)
    return v / (np.linalg.norm(v) + 1e-12)


class OnlineClusterer:
    """Incremental cosine clustering (leader algorithm + merge pass). Stable ids across runs."""

    def __init__(self, thr: float):
        self.thr = thr
        self.sums: Dict[int, np.ndarray] = {}
        self.counts: Dict[int, int] = {}
        self.next_id = 1

    def centroid(self, k: int) -> np.ndarray:
        return _unit(self.sums[k])

    def add(self, vec, weight: int = 1) -> int:
        u = _unit(vec)
        best, sim = None, -1.0
        for k in self.sums:
            s = float(u @ self.centroid(k))
            if s > sim:
                best, sim = k, s
        if best is None or sim < self.thr:
            best = self.next_id
            self.next_id += 1
            self.sums[best], self.counts[best] = np.zeros_like(u), 0
        self.sums[best] = self.sums[best] + u * weight
        self.counts[best] += weight
        return best

    def merge_close(self) -> Dict[int, int]:
        """Merge clusters whose centroids drifted together; returns {old_id: surviving_id}."""
        remap: Dict[int, int] = {}
        changed = True
        while changed:
            changed = False
            ks = sorted(self.sums)
            for i, a in enumerate(ks):
                for b in ks[i + 1 :]:
                    if float(self.centroid(a) @ self.centroid(b)) >= self.thr + 0.05:
                        self.sums[a] += self.sums.pop(b)
                        self.counts[a] += self.counts.pop(b)
                        remap[b] = a
                        changed = True
                        break
                if changed:
                    break
        return {k: _resolve(remap, k) for k in remap}

    def to_json(self):
        return {"thr": self.thr, "next": self.next_id,
                "c": {str(k): {"s": self.sums[k].tolist(), "n": self.counts[k]} for k in self.sums}}

    @classmethod
    def from_json(cls, d):
        o = cls(d["thr"])
        o.next_id = d["next"]
        for k, v in d["c"].items():
            o.sums[int(k)], o.counts[int(k)] = np.array(v["s"]), v["n"]
        return o


def _resolve(remap, k):
    while k in remap:
        k = remap[k]
    return k


def av_overlap(track_intervals: Dict[int, Sequence[Tuple[float, float]]],
               speech: Sequence[Tuple[float, float, int]]) -> Dict[Tuple[int, int], float]:
    """Seconds each (visual track, speaker) pair spend together. speech = [(start, end, speaker_id)]."""
    out: Dict[Tuple[int, int], float] = {}
    for s0, s1, spk in speech:
        for tid, ivs in track_intervals.items():
            ov = sum(max(0.0, min(s1, e) - max(s0, b)) for b, e in ivs)
            if ov > 0:
                out[(tid, spk)] = out.get((tid, spk), 0.0) + ov
    return out


class Registry:
    def __init__(self, vis_thr: float = 0.80, voice_thr: float = 0.85):
        self.visual = OnlineClusterer(vis_thr)
        self.voice = OnlineClusterer(voice_thr)
        self.overlap: Dict[str, float] = {}      # "v|a" -> seconds together
        self.presence: Dict[int, float] = {}     # visual id -> seconds on screen
        self.speech: Dict[int, float] = {}       # voice id -> seconds speaking
        self.total_time = 0.0
        self.names: Dict[int, str] = {}          # visual id -> user/auto name
        self.labels: Dict[int, Dict[str, int]] = {}  # visual id -> detector label votes
        self.episodes: Dict[int, List[str]] = {} # visual id -> episode keys
        self.done: Dict[str, List[float]] = {}   # episode path -> [size, mtime]

    # ---- evidence ------------------------------------------------------------------------------
    def add_episode(self, key: str, stamp: Sequence[float], duration: float,
                    track_vecs: Dict[int, np.ndarray], track_labels: Dict[int, str],
                    track_intervals: Dict[int, List[Tuple[float, float]]],
                    speech: Sequence[Tuple[float, float, np.ndarray]]) -> None:
        """track_vecs/labels/intervals keyed by the episode-local track id; speech vectors are per segment."""
        loc2vis = {t: self.visual.add(v) for t, v in track_vecs.items()}
        for t, vid in loc2vis.items():
            lab = track_labels.get(t)
            if lab:
                self.labels.setdefault(vid, {}).setdefault(lab, 0)
                self.labels[vid][lab] += 1
            self.presence[vid] = self.presence.get(vid, 0.0) + sum(e - b for b, e in track_intervals.get(t, []))
            self.episodes.setdefault(vid, [])
            if key not in self.episodes[vid]:
                self.episodes[vid].append(key)
        segs = [(s0, s1, self.voice.add(vec)) for s0, s1, vec in speech]
        for s0, s1, a in segs:
            self.speech[a] = self.speech.get(a, 0.0) + (s1 - s0)
        vis_iv = {loc2vis[t]: iv for t, iv in track_intervals.items() if t in loc2vis}
        for (v, a), sec in av_overlap(vis_iv, segs).items():
            k = f"{v}|{a}"
            self.overlap[k] = self.overlap.get(k, 0.0) + sec
        self.total_time += duration
        self.done[key] = list(stamp)

    def is_done(self, key: str, stamp: Sequence[float]) -> bool:
        return self.done.get(key) == list(stamp)

    # ---- queries -------------------------------------------------------------------------------
    def voice_of(self, vid: int, min_sec: float = 3.0, min_lift: float = 1.3) -> Optional[Tuple[int, float]]:
        """Best voice for a visual id by *lift* (speaks-while-on-screen vs base rate on screen); None if weak."""
        base = self.presence.get(vid, 0.0) / max(self.total_time, 1e-9)
        best = None
        for k, sec in self.overlap.items():
            v, a = map(int, k.split("|"))
            if v != vid or sec < min_sec or self.speech.get(a, 0) <= 0:
                continue
            lift = (sec / self.speech[a]) / max(base, 1e-9)
            if lift >= min_lift and (best is None or lift > best[1]):
                best = (a, lift)
        return best

    def characters(self, min_presence: float = 5.0) -> List[dict]:
        out = []
        for vid in sorted(self.visual.sums):
            if self.presence.get(vid, 0.0) < min_presence:
                continue
            votes = self.labels.get(vid, {})
            voice = self.voice_of(vid)
            out.append({"id": vid, "name": self.names.get(vid) or f"character_{vid}",
                        "kind": max(votes, key=votes.get) if votes else "unknown",
                        "seconds_on_screen": round(self.presence[vid], 1), "episodes": len(self.episodes.get(vid, [])),
                        "voice_id": voice[0] if voice else None, "voice_lift": round(voice[1], 2) if voice else None})
        return out

    def consolidate(self) -> None:
        """Merge duplicate clusters (identity fragments) and re-key every table that references them."""
        vmap = self.visual.merge_close()
        amap = self.voice.merge_close()
        for remap, tables in ((vmap, (self.presence, self.labels, self.episodes, self.names)), (amap, (self.speech,))):
            for old, new in remap.items():
                for t in tables:
                    if old not in t:
                        continue
                    val = t.pop(old)
                    if isinstance(val, dict):
                        for lk, c in val.items():
                            t.setdefault(new, {})[lk] = t.get(new, {}).get(lk, 0) + c
                    elif isinstance(val, list):
                        t[new] = list(dict.fromkeys(t.get(new, []) + val))
                    elif isinstance(val, str):
                        t.setdefault(new, val)
                    else:
                        t[new] = t.get(new, 0) + val
        fixed: Dict[str, float] = {}
        for k, sec in self.overlap.items():
            v, a = map(int, k.split("|"))
            key = f"{vmap.get(v, v)}|{amap.get(a, a)}"
            fixed[key] = fixed.get(key, 0.0) + sec
        self.overlap = fixed

    # ---- persistence ---------------------------------------------------------------------------
    def save(self, path: str) -> None:
        d = {"visual": self.visual.to_json(), "voice": self.voice.to_json(), "overlap": self.overlap,
             "presence": self.presence, "speech": self.speech, "total_time": self.total_time, "names": self.names,
             "labels": self.labels, "episodes": self.episodes, "done": self.done}
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        json.dump(d, open(path + ".tmp", "w"))
        os.replace(path + ".tmp", path)

    @classmethod
    def load(cls, path: str) -> "Registry":
        r = cls()
        if not os.path.exists(path):
            return r
        d = json.load(open(path))
        r.visual, r.voice = OnlineClusterer.from_json(d["visual"]), OnlineClusterer.from_json(d["voice"])
        r.overlap, r.total_time, r.done = d["overlap"], d["total_time"], d["done"]
        ik = lambda m: {int(k): v for k, v in m.items()}
        r.presence, r.speech, r.names, r.labels, r.episodes = (ik(d[k]) for k in
                                                              ("presence", "speech", "names", "labels", "episodes"))
        return r
