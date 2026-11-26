"""Compact track representation: a uint8 label map [T, H, W] (0 = background, k = persistent object id).

One representation shared by every backend, by the coherence metrics and (later) by DiT conditioning.
Default grid is the VAE latent grid (60x90) so it is ~100x smaller than pixel masks and aligns 1:1 with latents.
"""
import os
from typing import Dict, Optional, Tuple

import numpy as np

LATENT_HW = (60, 90)


def masks_to_labelmap(masks: Dict[int, np.ndarray], hw: Tuple[int, int] = LATENT_HW) -> np.ndarray:
    """masks: {obj_id: bool[T, H0, W0]} -> uint8[T, *hw]; later ids never overwrite earlier ones."""
    ids = sorted(masks)
    if not ids:
        raise ValueError("no masks")
    T = masks[ids[0]].shape[0]
    out = np.zeros((T, *hw), dtype=np.uint8)
    for oid in reversed(ids):  # lowest id wins on overlap
        out[resize_nearest(masks[oid].astype(bool), hw)] = oid
    return out


def resize_nearest(m: np.ndarray, hw: Tuple[int, int]) -> np.ndarray:
    """Nearest-neighbour resize of [T, H, W] without extra deps."""
    T, H, W = m.shape
    ys = (np.arange(hw[0]) * H // hw[0]).clip(0, H - 1)
    xs = (np.arange(hw[1]) * W // hw[1]).clip(0, W - 1)
    return m[:, ys][:, :, xs]


def save_labelmaps(path: str, labels: np.ndarray, names: Optional[Dict[int, str]] = None) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    ids = np.array(sorted(names or {}), dtype=np.int32)
    txt = np.array([names[i] for i in ids]) if len(ids) else np.array([])
    np.savez_compressed(path + ".tmp.npz", labels=labels.astype(np.uint8), ids=ids, names=txt)
    os.replace(path + ".tmp.npz", path)  # atomic: an interrupted run never leaves a corrupt cache


def load_labelmaps(path: str):
    with np.load(path, allow_pickle=False) as z:
        names = {int(i): str(n) for i, n in zip(z["ids"], z["names"])}
        return z["labels"], names
