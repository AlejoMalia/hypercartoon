"""Scene elements and the space they take. Detectors share one interface: `detect(frame_rgb_uint8) -> [element]`.

  BlobDetector      CPU, no model: foreground vs the dominant background colour, connected components. Works on flat-colour cartoons;
                    elements are unlabeled ('elemento') but their bbox / mask / area are real.
  YoloDetector      Ultralytics YOLO(-seg) (closed vocabulary: person, car, chair...). pip install ultralytics
  DinoSamDetector   Grounding DINO boxes from a text prompt (any element you name) + SAM 2 masks for the exact area. transformers + sam2
The YOLO / DINO / SAM adapters follow the public APIs of those projects and were not run here (no GPU / packages)."""
from typing import Dict, List, Optional, Sequence

import numpy as np
from scipy import ndimage


def _element(label, score, box_px, shape, mask=None) -> Dict:
    h, w = shape[:2]
    x0, y0, x1, y1 = box_px
    area = float(mask.mean()) if mask is not None else max(0.0, (x1 - x0) * (y1 - y0)) / (w * h)
    return {"label": label, "score": float(score), "bbox": [x0 / w, y0 / h, x1 / w, y1 / h], "area": area, "mask": mask}


class BlobDetector:
    name = "blobs"

    def __init__(self, thr: float = 0.12, min_area: float = 0.004, max_side: int = 160, max_elements: int = 12):
        self.thr, self.min_area, self.max_side, self.max_elements = thr, min_area, max_side, max_elements

    def detect(self, frame: np.ndarray) -> List[Dict]:
        st = max(1, max(frame.shape[:2]) // self.max_side)
        f = frame[::st, ::st].astype(np.float32) / 255.0
        q = (f * 15.999).astype(np.int32)
        key = q[..., 0] * 256 + q[..., 1] * 16 + q[..., 2]
        bg = np.bincount(key.ravel()).argmax()                       # the most common quantised colour is the background
        bg_rgb = f[key == bg].mean(0)
        mask = np.abs(f - bg_rgb).max(-1) > self.thr
        mask = ndimage.binary_opening(mask, iterations=1)
        lab, n = ndimage.label(mask)
        out = []
        for i, sl in enumerate(ndimage.find_objects(lab), start=1):
            m = lab[sl] == i
            if m.sum() / mask.size < self.min_area:
                continue
            full = np.zeros(mask.shape, bool)
            full[sl] = m
            out.append(_element("elemento", 1.0, (sl[1].start, sl[0].start, sl[1].stop, sl[0].stop), mask.shape, full))
        out.sort(key=lambda e: -e["area"])
        return out[: self.max_elements]


class YoloDetector:
    name = "yolo"

    def __init__(self, weights: str = "yolo11n-seg.pt", device: str = "cuda", conf: float = 0.25):
        from ultralytics import YOLO

        self.m, self.device, self.conf = YOLO(weights), device, conf

    def detect(self, frame: np.ndarray) -> List[Dict]:
        r = self.m(frame, verbose=False, device=self.device, conf=self.conf)[0]
        h, w = frame.shape[:2]
        out = []
        masks = r.masks.data.cpu().numpy() if getattr(r, "masks", None) is not None else None
        for i, (b, c, s) in enumerate(zip(r.boxes.xyxy.cpu().numpy(), r.boxes.cls.cpu().numpy(), r.boxes.conf.cpu().numpy())):
            m = None
            if masks is not None:
                mh, mw = masks[i].shape
                m = masks[i][np.ix_(np.arange(h) * mh // h, np.arange(w) * mw // w)] > 0.5
            out.append(_element(r.names[int(c)], s, b, (h, w), m))
        return out


class DinoSamDetector:
    name = "dino+sam2"

    def __init__(self, prompts: Sequence[str], dino_id: str = "IDEA-Research/grounding-dino-tiny", sam2_cfg: Optional[str] = None,
                 sam2_ckpt: Optional[str] = None, device: str = "cuda", box_thr: float = 0.35, text_thr: float = 0.25):
        import torch
        from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor

        self.torch, self.device, self.box_thr, self.text_thr = torch, device, box_thr, text_thr
        self.text = ". ".join(p.lower().strip(" .") for p in prompts) + "."
        self.proc = AutoProcessor.from_pretrained(dino_id)
        self.dino = AutoModelForZeroShotObjectDetection.from_pretrained(dino_id).to(device).eval()
        self.sam = None
        if sam2_cfg and sam2_ckpt:
            from sam2.build_sam import build_sam2
            from sam2.sam2_image_predictor import SAM2ImagePredictor

            self.sam = SAM2ImagePredictor(build_sam2(sam2_cfg, sam2_ckpt, device=device))

    def detect(self, frame: np.ndarray) -> List[Dict]:
        from PIL import Image

        h, w = frame.shape[:2]
        img = Image.fromarray(frame)
        with self.torch.no_grad():
            out = self.dino(**self.proc(images=img, text=self.text, return_tensors="pt").to(self.device))
        try:  # transformers renamed `box_threshold` -> `threshold` across versions
            det = self.proc.post_process_grounded_object_detection(out, threshold=self.box_thr, text_threshold=self.text_thr, target_sizes=[(h, w)])[0]
        except TypeError:
            det = self.proc.post_process_grounded_object_detection(out, None, box_threshold=self.box_thr, text_threshold=self.text_thr, target_sizes=[(h, w)])[0]
        boxes, scores, labels = det["boxes"].cpu().numpy(), det["scores"].cpu().numpy(), det["labels"]
        masks = [None] * len(boxes)
        if self.sam is not None and len(boxes):
            self.sam.set_image(frame)
            masks = [self.sam.predict(box=b, multimask_output=False)[0][0].astype(bool) for b in boxes]
        return [_element(str(l), s, b, (h, w), m) for b, s, l, m in zip(boxes, scores, labels, masks)]


def _has(*mods) -> bool:
    import importlib.util

    return all(importlib.util.find_spec(m) is not None for m in mods)


def get_detector(kind: str = "auto", prompts: Optional[Sequence[str]] = None, device: str = "cuda", **kw):
    """auto: DINO(+SAM2) if prompts are given and available, else YOLO if installed, else the CPU blob detector."""
    if kind == "auto":
        kind = "dino" if prompts and _has("transformers", "torch") else "yolo" if _has("ultralytics") else "blobs"
    if kind == "blobs":
        return BlobDetector()
    if kind == "yolo":
        return YoloDetector(device=device)
    if kind == "dino":
        if not prompts:
            raise ValueError("Grounding DINO needs prompts (the elements to look for)")
        return DinoSamDetector(prompts, device=device, **kw)
    raise ValueError("detector: auto | blobs | yolo | dino")


def inventory(per_keyframe: Sequence[Sequence[Dict]]) -> List[Dict]:
    """Merge the detections of the keyframes of a shot by label: mean area, mean position, how many keyframes show it."""
    from studio.analysis.framing import describe

    agg: Dict[str, List[Dict]] = {}
    for kf in per_keyframe:
        seen = {}
        for e in kf:
            d = describe(e)
            if d["label"] not in seen or d["area_pct"] > seen[d["label"]]["area_pct"]:
                seen[d["label"]] = d
        for l, d in seen.items():
            agg.setdefault(l, []).append(d)
    n = max(1, len(per_keyframe))
    out = []
    for l, ds in agg.items():
        cx = float(np.mean([d["center"][0] for d in ds]))
        cy = float(np.mean([d["center"][1] for d in ds]))
        from studio.analysis.framing import third_cell

        out.append({"label": l, "keyframes": len(ds), "presence": len(ds) / n, "area_pct": float(np.mean([d["area_pct"] for d in ds])),
                    "center": [cx, cy], **third_cell(cx, cy)})
    return sorted(out, key=lambda x: -x["area_pct"])
