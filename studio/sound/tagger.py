"""Optional AudioSet tagger (527 classes: speech, music, rain, door slam, ...) for rich ambience / effects labels.
PANNs via the `panns_inference` package; follows its public API -- validate before relying on it."""
from typing import List, Tuple

import numpy as np


def panns_tags(wave32k: np.ndarray, top: int = 5, device: str = "cpu") -> List[Tuple[str, float]]:
    from panns_inference import AudioTagging, labels

    at = AudioTagging(checkpoint_path=None, device=device)
    clip, _ = at.inference(wave32k[None, :].astype(np.float32))
    idx = np.argsort(clip[0])[::-1][:top]
    return [(labels[i], float(clip[0][i])) for i in idx]
