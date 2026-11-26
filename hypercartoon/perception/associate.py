"""Detector-agnostic identity association (numpy/scipy). Used when a backend gives per-frame masks without IDs
(e.g. re-tracking a *generated* video) and as a zero-GPU fallback."""
import numpy as np
from scipy.optimize import linear_sum_assignment


def mask_iou_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """a: bool[N,H,W], b: bool[M,H,W] -> IoU[N,M]."""
    A, B = a.reshape(len(a), -1).astype(np.float32), b.reshape(len(b), -1).astype(np.float32)
    inter = A @ B.T
    union = A.sum(1)[:, None] + B.sum(1)[None] - inter
    return inter / np.maximum(union, 1.0)


def track_instances(frames, iou_thr: float = 0.3) -> np.ndarray:
    """frames: list over T of bool[N_t,H,W] instance masks -> uint8 label map [T,H,W] with persistent ids."""
    T = len(frames)
    H, W = frames[0].shape[1:] if len(frames[0]) else next(f.shape[1:] for f in frames if len(f))
    out = np.zeros((T, H, W), dtype=np.uint8)
    prev_ids, prev = [], np.zeros((0, H, W), bool)
    next_id = 1
    for t, cur in enumerate(frames):
        cur_ids = [-1] * len(cur)
        if len(prev) and len(cur):
            r, c = linear_sum_assignment(-mask_iou_matrix(prev, cur))
            iou = mask_iou_matrix(prev, cur)
            for i, j in zip(r, c):
                if iou[i, j] >= iou_thr:
                    cur_ids[j] = prev_ids[i]
        for j in range(len(cur)):
            if cur_ids[j] < 0:
                cur_ids[j], next_id = next_id, min(next_id + 1, 255)
            out[t][cur[j]] = cur_ids[j]
        prev_ids, prev = cur_ids, cur
    return out
