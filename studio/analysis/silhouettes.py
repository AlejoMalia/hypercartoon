"""Label every element of a shot: silhouette (mask) + what it is + what kind of thing it is + a short description.

Pipeline (the one the Grounded-SAM-2 family follows, with CPU fall-backs so the studio always produces something):
  1. detect + label   Grounding DINO / YOLO / (CPU) colour blobs       -> `elements.get_detector`
  2. silhouette       SAM 2 masks from the boxes (DinoSamDetector) / segmentation heads / blob masks
  3. propagate        SAM 2 video predictor along the shot (`Sam2VideoTracker`) or, without it, IoU linking between keyframes
  4. describe         Florence-2 or BLIP caption of the crop (`Florence2Captioner`, `BlipCaptioner`) or a measured description
                      (size, colour, position) that never needs a model
Output per shot: a label map (uint8, 0 = background, k = k-th element) per keyframe + an element table with kind, caption, track id.
The Florence-2 / BLIP / SAM 2 video adapters follow the public APIs and were not run here (no GPU, packages not installed)."""
import json
import os
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

PERSON = {"person", "man", "woman", "boy", "girl", "child", "kid", "people", "human", "character", "baby", "lady", "gentleman"}
ANIMAL = {"bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "rabbit", "bunny", "mouse", "pig", "duck",
          "fish", "monkey", "lion", "tiger", "wolf", "fox", "owl", "frog", "turtle", "animal", "chicken", "deer", "squirrel", "penguin"}
VEHICLE = {"car", "bus", "truck", "train", "boat", "bicycle", "motorcycle", "airplane", "ship", "spaceship", "rocket"}
SCENERY = {"tree", "house", "building", "mountain", "cloud", "sun", "moon", "star", "flower", "grass", "road", "sky", "river", "hill", "bush"}


def kind_of(label: str) -> str:
    """person | animal | vehicle | scenery | object | unlabeled. People and animals are the *agents* (characters) of a cartoon."""
    l = label.lower().strip()
    words = set(l.replace("-", " ").split()) | {l}
    for kind, vocab in (("person", PERSON), ("animal", ANIMAL), ("vehicle", VEHICLE), ("scenery", SCENERY)):
        if words & vocab:
            return kind
    return "unlabeled" if l in ("", "elemento", "element", "unknown", "object ") else "object"


def is_agent(kind: str) -> bool:
    return kind in ("person", "animal")


# ---- measured description (no model) ----------------------------------------------------------------------------------------------
def size_word(area: float) -> str:
    return "tiny" if area < 0.01 else "small" if area < 0.05 else "medium" if area < 0.18 else "large" if area < 0.45 else "huge"


def dominant_color(frame: np.ndarray, mask: Optional[np.ndarray], box: Sequence[float]) -> str:
    from studio.dataset import color_name

    h, w = frame.shape[:2]
    if mask is not None and mask.any():
        mh, mw = mask.shape
        ys, xs = (np.arange(h) * mh // h), (np.arange(w) * mw // w)
        px = frame[mask[np.ix_(ys, xs)]]
    else:
        x0, y0, x1, y1 = box
        px = frame[int(y0 * h) : max(int(y1 * h), int(y0 * h) + 1), int(x0 * w) : max(int(x1 * w), int(x0 * w) + 1)].reshape(-1, 3)
    if len(px) == 0:
        return ""
    q = (px >> 5).astype(np.int32)  # 3 bits per channel: the most common colour, not the mean (outlines would turn it grey)
    key = q[:, 0] * 64 + q[:, 1] * 8 + q[:, 2]
    top = int(np.bincount(key, minlength=512).argmax())
    return color_name((top // 64 * 32 + 16, top // 8 % 8 * 32 + 16, top % 8 * 32 + 16))


class HeuristicElementCaptioner:
    """Size, colour, label and place in the frame: honest, instant, no model."""

    name = "measured"

    def caption(self, frame: np.ndarray, el: Dict) -> str:
        from studio.analysis.framing import third_cell

        l = el["label"] if el["label"] not in ("elemento",) else "shape"
        from studio.dataset import EN_H, EN_V

        cx, cy = (el["bbox"][0] + el["bbox"][2]) / 2, (el["bbox"][1] + el["bbox"][3]) / 2
        cell = third_cell(cx, cy)
        where = f"{EN_V.get(cell['vertical'], cell['vertical'])} {EN_H.get(cell['horizontal'], cell['horizontal'])}"
        where = "center" if where == "middle center" else where
        col = dominant_color(frame, el.get("mask"), el["bbox"])
        return " ".join(x for x in (f"a {size_word(el['area'])}", col, l, f"in the {where}" if where else "") if x)


class Florence2Captioner:
    """Microsoft Florence-2 (`<MORE_DETAILED_CAPTION>` on the crop). pip install transformers torch; trust_remote_code is required by
    the model card. Not run here."""

    name = "florence2"

    def __init__(self, model_id: str = "microsoft/Florence-2-base", device: str = "cuda"):
        import torch
        from transformers import AutoModelForCausalLM, AutoProcessor

        self.torch, self.device = torch, device
        self.proc = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
        self.model = AutoModelForCausalLM.from_pretrained(model_id, trust_remote_code=True).to(device).eval()

    def caption(self, frame: np.ndarray, el: Dict) -> str:
        from PIL import Image

        h, w = frame.shape[:2]
        x0, y0, x1, y1 = el["bbox"]
        crop = Image.fromarray(frame[int(y0 * h) : max(int(y1 * h), int(y0 * h) + 8), int(x0 * w) : max(int(x1 * w), int(x0 * w) + 8)])
        task = "<MORE_DETAILED_CAPTION>"
        inp = self.proc(text=task, images=crop, return_tensors="pt").to(self.device)
        with self.torch.no_grad():
            ids = self.model.generate(input_ids=inp["input_ids"], pixel_values=inp["pixel_values"], max_new_tokens=60, num_beams=3)
        text = self.proc.batch_decode(ids, skip_special_tokens=False)[0]
        return self.proc.post_process_generation(text, task=task, image_size=crop.size)[task].strip()


class BlipCaptioner:
    """Salesforce BLIP image captioning on the crop (transformers). Not run here."""

    name = "blip"

    def __init__(self, model_id: str = "Salesforce/blip-image-captioning-base", device: str = "cuda"):
        from transformers import BlipForConditionalGeneration, BlipProcessor

        self.device = device
        self.proc = BlipProcessor.from_pretrained(model_id)
        self.model = BlipForConditionalGeneration.from_pretrained(model_id).to(device).eval()

    def caption(self, frame: np.ndarray, el: Dict) -> str:
        from PIL import Image

        h, w = frame.shape[:2]
        x0, y0, x1, y1 = el["bbox"]
        crop = Image.fromarray(frame[int(y0 * h) : max(int(y1 * h), int(y0 * h) + 8), int(x0 * w) : max(int(x1 * w), int(x0 * w) + 8)])
        inp = self.proc(crop, return_tensors="pt").to(self.device)
        return self.proc.decode(self.model.generate(**inp, max_new_tokens=40)[0], skip_special_tokens=True).strip()


def get_captioner(kind: str = "measured", device: str = "cuda"):
    if kind in ("measured", "", None):
        return HeuristicElementCaptioner()
    if kind == "florence2":
        return Florence2Captioner(device=device)
    if kind == "blip":
        return BlipCaptioner(device=device)
    raise ValueError("captioner: measured | florence2 | blip")


# ---- labelling one frame ------------------------------------------------------------------------------------------------------------
def label_frame(frame: np.ndarray, dets: Sequence[Dict], captioner=None, max_elements: int = 24) -> List[Dict]:
    """Detections -> labelled elements: kind, caption, colour, area, bbox, mask (kept, for the label map)."""
    captioner = captioner or HeuristicElementCaptioner()
    out = []
    for d in sorted(dets, key=lambda e: -e["area"])[:max_elements]:
        el = dict(d)
        el["kind"] = kind_of(el["label"])
        el["agent"] = is_agent(el["kind"])
        el["color"] = dominant_color(frame, el.get("mask"), el["bbox"])
        try:
            el["caption"] = captioner.caption(frame, el)
        except Exception:  # a failing captioning model must not lose the silhouettes
            el["caption"] = HeuristicElementCaptioner().caption(frame, el)
        out.append(el)
    return out


def label_map(elements: Sequence[Dict], shape: Tuple[int, int]) -> np.ndarray:
    """uint8 [H, W]: 0 background, k = k-th element (1-based). Large elements are painted first so small ones stay visible on top."""
    h, w = shape
    lm = np.zeros((h, w), np.uint8)
    for k, e in sorted(enumerate(elements, 1), key=lambda t: -t[1]["area"]):
        if e.get("mask") is not None:
            m = e["mask"]
            if m.shape != (h, w):
                m = m[np.ix_(np.arange(h) * m.shape[0] // h, np.arange(w) * m.shape[1] // w)]
            lm[m] = min(k, 255)
        else:
            x0, y0, x1, y1 = e["bbox"]
            lm[int(y0 * h) : int(np.ceil(y1 * h)), int(x0 * w) : int(np.ceil(x1 * w))] = min(k, 255)
    return lm


# ---- tracking across the keyframes of a shot --------------------------------------------------------------------------------------------
def _iou(a, b) -> float:
    iw, ih = min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])
    if iw <= 0 or ih <= 0:
        return 0.0
    i = iw * ih
    return i / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i)


def link_tracks(per_frame: Sequence[List[Dict]], thr: float = 0.25) -> int:
    """Give each element a persistent `track` id across consecutive keyframes (same label, best IoU). Adds the key in place; -> #tracks.
    SAM 2's video predictor does this far better on moving subjects (`Sam2VideoTracker`); this is the CPU fall-back."""
    nxt, prev = 0, []
    for els in per_frame:
        used = set()
        for e in els:
            best, bi = 0.0, None
            for j, p in enumerate(prev):
                if j in used or p["label"] != e["label"]:
                    continue
                v = _iou(e["bbox"], p["bbox"])
                if v > best:
                    best, bi = v, j
            if bi is not None and best >= thr:
                e["track"] = prev[bi]["track"]
                used.add(bi)
            else:
                e["track"] = nxt
                nxt += 1
        prev = list(els)
    return nxt


class Sam2VideoTracker:
    """SAM 2 video predictor: boxes on one frame -> masks on every frame of the shot (facebookresearch/sam2, `init_state`,
    `add_new_points_or_box`, `propagate_in_video`). `frames_dir` holds the shot's frames as numbered JPEGs. Not run here."""

    name = "sam2-video"

    def __init__(self, cfg: str, ckpt: str, device: str = "cuda"):
        from sam2.build_sam import build_sam2_video_predictor

        self.pred = build_sam2_video_predictor(cfg, ckpt, device=device)

    def propagate(self, frames_dir: str, first_frame_boxes: Sequence[Sequence[float]], frame_idx: int = 0) -> Dict[int, Dict[int, np.ndarray]]:
        import torch

        out: Dict[int, Dict[int, np.ndarray]] = {}
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
            state = self.pred.init_state(video_path=frames_dir)
            for oid, box in enumerate(first_frame_boxes, 1):
                self.pred.add_new_points_or_box(inference_state=state, frame_idx=frame_idx, obj_id=oid, box=np.asarray(box, np.float32))
            for fi, ids, logits in self.pred.propagate_in_video(state):
                out[fi] = {int(i): (logits[k] > 0).cpu().numpy()[0] for k, i in enumerate(ids)}
        return out


# ---- per-shot result ------------------------------------------------------------------------------------------------------------------------
def shot_elements(keyframes: Sequence[np.ndarray], detections: Sequence[Sequence[Dict]], captioner=None) -> Tuple[List[List[Dict]], List[np.ndarray]]:
    """-> (labelled elements per keyframe with track ids, label map per keyframe)."""
    lab = [label_frame(f, d, captioner) for f, d in zip(keyframes, detections)]
    link_tracks(lab)
    return lab, [label_map(e, f.shape[:2]) for e, f in zip(lab, keyframes)]


def summarize(labelled: Sequence[Sequence[Dict]]) -> List[Dict]:
    """One row per track: label, kind, caption of its largest appearance, mean area, how many keyframes it is in."""
    rows: Dict[int, List[Dict]] = {}
    for els in labelled:
        for e in els:
            rows.setdefault(e["track"], []).append(e)
    n = max(1, len(labelled))
    out = []
    for t, es in rows.items():
        big = max(es, key=lambda e: e["area"])
        out.append({"track": t, "label": big["label"], "kind": big["kind"], "agent": big["agent"], "caption": big["caption"], "color": big["color"],
                    "area_pct": float(np.mean([e["area"] for e in es]) * 100), "presence": len(es) / n,
                    "bbox": [round(float(x), 3) for x in big["bbox"]]})
    return sorted(out, key=lambda r: -r["area_pct"])


def save_silhouettes(path: str, video: str, shots: Sequence[Dict]) -> str:
    """shots: [{'index', 'times', 'maps': [uint8 HxW], 'elements': [row...]}] -> one .npz (maps) + .json (table) per video."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    arrays = {f"s{s['index']:04d}_k{k}": m for s in shots for k, m in enumerate(s["maps"])}
    np.savez_compressed(path + ".npz", **arrays)
    json.dump({"video": video, "shots": [{"index": s["index"], "times": s["times"], "keyframes": len(s["maps"]), "elements": s["elements"]} for s in shots]},
              open(path + ".json", "w"), ensure_ascii=False, indent=1)
    return path
