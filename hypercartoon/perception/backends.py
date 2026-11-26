"""Lazy adapters to external perception repos. Nothing here is imported unless a backend is requested, so the
training/sampling environment needs none of these packages.

Cost design (single expensive pass, cached as label maps):
  grounded_sam2 : text -> Grounding DINO on ONE keyframe per scene -> SAM 2 propagates masks through the video
                  (SAM 2's memory bank carries identity; no per-frame detection).
  yolo_track    : Ultralytics YOLO-seg + ByteTrack/BoT-SORT, per-frame, for closed-set classes / fast preview.
Install (separate env): pip install sam-2 transformers ultralytics  (see docs/perception.md)
NOTE: these adapters follow the public APIs of each project but must be validated on a GPU machine.
"""
from typing import Dict, List, Tuple

import numpy as np

from hypercartoon.perception.labelmap import masks_to_labelmap


def grounded_sam2(video_dir: str, prompts: List[str], sam2_cfg: str, sam2_ckpt: str,
                  dino_id: str = "IDEA-Research/grounding-dino-tiny", device: str = "cuda") -> Tuple[np.ndarray, Dict[int, str]]:
    """video_dir: folder of JPEG frames (SAM 2 video-predictor input). Returns (labelmap uint8[T,60,90], names)."""
    import torch
    from PIL import Image
    from sam2.build_sam import build_sam2_video_predictor
    from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor
    import os

    frames = sorted(f for f in os.listdir(video_dir) if f.lower().endswith((".jpg", ".jpeg")))
    proc = AutoProcessor.from_pretrained(dino_id)
    dino = AutoModelForZeroShotObjectDetection.from_pretrained(dino_id).to(device).eval()
    img = Image.open(os.path.join(video_dir, frames[0])).convert("RGB")
    text = ". ".join(p.lower().strip(" .") for p in prompts) + "."
    with torch.no_grad():
        out = dino(**proc(images=img, text=text, return_tensors="pt").to(device))
    det = proc.post_process_grounded_object_detection(out, threshold=0.35, text_threshold=0.25,
                                                     target_sizes=[img.size[::-1]])[0]
    boxes, labels = det["boxes"].cpu().numpy(), det["labels"]

    pred = build_sam2_video_predictor(sam2_cfg, sam2_ckpt, device=device)
    names: Dict[int, str] = {}
    masks: Dict[int, List[np.ndarray]] = {}
    with torch.inference_mode(), torch.autocast(device, dtype=torch.bfloat16):
        state = pred.init_state(video_path=video_dir)
        for k, (b, lab) in enumerate(zip(boxes, labels), start=1):
            pred.add_new_points_or_box(state, frame_idx=0, obj_id=k, box=b)
            names[k], masks[k] = str(lab), [None] * len(frames)
        for fi, obj_ids, logits in pred.propagate_in_video(state):
            for j, oid in enumerate(obj_ids):
                masks[int(oid)][fi] = (logits[j, 0] > 0).cpu().numpy()
    stacked = {k: np.stack(v) for k, v in masks.items() if all(m is not None for m in v)}
    return masks_to_labelmap(stacked), {k: names[k] for k in stacked}


def yolo_track(video_path: str, weights: str = "yolo11n-seg.pt", tracker: str = "bytetrack.yaml",
               device: str = "cuda") -> Tuple[np.ndarray, Dict[int, str]]:
    """Ultralytics segmentation + built-in tracker -> label map. IDs are remapped to compact uint8 ids."""
    from ultralytics import YOLO

    model = YOLO(weights)
    remap: Dict[int, int] = {}
    names: Dict[int, str] = {}
    per_frame: List[Dict[int, np.ndarray]] = []
    for r in model.track(source=video_path, tracker=tracker, persist=True, stream=True, device=device, verbose=False):
        cur = {}
        if r.boxes.id is not None and r.masks is not None:
            for tid, cls, m in zip(r.boxes.id.int().tolist(), r.boxes.cls.int().tolist(), r.masks.data.cpu().numpy()):
                k = remap.setdefault(tid, len(remap) + 1)
                if k > 255:
                    continue
                names[k] = r.names[cls]
                cur[k] = m > 0.5
        per_frame.append(cur)
    if not remap:
        raise RuntimeError("no tracked objects")
    h, w = next(iter(next(f for f in per_frame if f).values())).shape
    masks = {k: np.stack([f.get(k, np.zeros((h, w), bool)) for f in per_frame]) for k in names}
    return masks_to_labelmap(masks), names


def track_embeddings(video_path: str, labels: np.ndarray, n_samples: int = 6, model_id: str = "facebook/dinov2-small",
                     device: str = "cuda"):
    """Appearance vector per track id = mean DINOv2 CLS of its (masked-bbox) crops over n_samples frames.
    Returns ({id: vec}, {id: [(start_s, end_s)]}) so tracks can be matched across episodes and linked to voices."""
    import imageio
    import torch
    from transformers import AutoImageProcessor, AutoModel

    proc, net = AutoImageProcessor.from_pretrained(model_id), AutoModel.from_pretrained(model_id).to(device).eval()
    ids = [int(i) for i in np.unique(labels) if i != 0]
    T, H, W = labels.shape  # one label map per video frame, so frame index == label index
    r = imageio.get_reader(video_path, "ffmpeg")
    fps = float(r.get_meta_data()["fps"])
    want = set()
    for i in ids:
        pres = np.flatnonzero((labels == i).any((1, 2)))
        want.update(np.linspace(pres[0], pres[-1], n_samples).astype(int).tolist())
    pix = {t: f for t, f in enumerate(r) if t in want}  # single decode pass
    r.close()
    vecs, ivs = {}, {}
    for i in ids:
        crops = []
        for t, f in pix.items():
            m = labels[t] == i
            if not m.any():
                continue
            ys, xs = np.where(m)
            fh, fw = f.shape[:2]
            y0, y1, x0, x1 = (ys.min() * fh // H, (ys.max() + 1) * fh // H, xs.min() * fw // W, (xs.max() + 1) * fw // W)
            crops.append(f[y0:y1, x0:x1])
        if crops:
            with torch.no_grad():
                out = net(**proc(images=crops, return_tensors="pt").to(device)).last_hidden_state[:, 0]
            vecs[i] = out.mean(0).cpu().numpy()
        pres = (labels == i).any((1, 2))
        edges = np.flatnonzero(np.diff(np.r_[0, pres.astype(int), 0]))
        ivs[i] = [(a / fps, b / fps) for a, b in zip(edges[::2], edges[1::2])]
    return vecs, ivs
