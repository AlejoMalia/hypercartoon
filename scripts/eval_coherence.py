"""Score frame/object/motion coherence of generated videos (or cached label maps). No generation cost.

  python scripts/eval_coherence.py --labels TRACKS_DIR            # cached .npz label maps
  python scripts/eval_coherence.py --videos OUT_DIR 
"""
import argparse
import glob
import json
import os

import numpy as np

from hypercartoon.perception import coherence_report, load_labelmaps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels")
    ap.add_argument("--videos")
    ap.add_argument("--out", default="coherence.json")
    a = ap.parse_args()
    res = {}
    if a.labels:
        for p in sorted(glob.glob(os.path.join(a.labels, "**", "*.npz"), recursive=True)):
            res[p] = coherence_report(load_labelmaps(p)[0])
    if a.videos:
        from hypercartoon.perception import backends

        for p in sorted(glob.glob(os.path.join(a.videos, "**", "*.mp4"), recursive=True)):
            res[p] = coherence_report(backends.yolo_track(p)[0])
    ok = [r["coherence"] for r in res.values() if not np.isnan(r["coherence"])]
    res["_mean_coherence"] = float(np.mean(ok)) if ok else float("nan")
    json.dump(res, open(a.out, "w"), indent=1)
    print(f"{len(res) - 1} videos, mean coherence {res['_mean_coherence']:.3f} -> {a.out}")


if __name__ == "__main__":
    main()
