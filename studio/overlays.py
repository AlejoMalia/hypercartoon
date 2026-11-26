"""Keep the model on the *animation*: find everything burned into the picture that is not part of it — subtitles, title cards
and credits, channel logos / watermarks / TV bugs, letterbox bars — and keep it out of what the model learns.

Four independent blocks, all driven by one per-video report (`overlays/<video>.overlay.json`):
  1. DATA      clips that fall in title cards / credits are not cut; letterbox bars are cropped; optional `delogo` / `crop` cleaning
               is folded into the ffmpeg command that cuts the clips (`ffmpeg_filter`).
  2. LOSS      every clip gets a *loss mask* on the latent grid (60 x 90 per latent frame): pixels covered by an overlay carry no
               gradient, so the network is never asked to reproduce a logo or a subtitle (`clip_loss_mask`; the engine applies it).
  3. CAPTIONS  captions never mention text, subtitles, logos or symbols (`sanitize_caption`, VLM instruction).
  4. GENERATION every prompt carries a negative text (`NEGATIVE_TEXT`) and `text_intrusion` measures how much text / static overlay
               a generated video still contains (it is a metric in `studio score`).

Detection is a CPU heuristic (letter-like components lined up in a row + edges that persist across different shots), calibrated on
synthetic renders. For real footage an OCR detector can be plugged in (`ocr_detector("easyocr"|"paddle")`, not run here) — the rest
of the machinery only needs boxes.   See docs/overlays.md for the repositories this follows (video-subtitle-remover, ProPainter, EAST/DB)."""
import json
import os
import re
import subprocess
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import numpy as np
from scipy import ndimage as ndi

VERSION = 2                        # bump when the detector changes: cached reports of older versions are recomputed
NEGATIVE_TEXT = ("text, subtitles, captions, watermark, logo, channel logo, title card, credits, letters, numbers, symbols, "
                 "on-screen graphics, user interface")
LATENT_GRID = (60, 90)             # 480 x 720 / 8
CLIP_SIZE = (720, 480)             # (w, h) the clips are cut to
MODES = ("mask", "delogo", "crop", "off")

_CAPTION_TEXT = re.compile(
    r"(?:(?:the|a|an|with|and|showing|displaying|reads?|reading|saying|says)\s+)*"
    r"\b(?:subtitles?|captions?|on-?screen text|text overlay|title card|credits?|watermarks?|logos?|channel logo|lower[- ]third|"
    r"text reads|the text|words? on screen|letters?)\b[^.,;]*", re.I)


# ---- frame sampling ------------------------------------------------------------------------------------------------------
def sample_frames(path: str, fps: float = 2.0, width: int = 480) -> Tuple[float, Tuple[int, int], Iterable[np.ndarray]]:
    """Stream small RGB frames at `fps` from any video through one ffmpeg pass (never loads the whole video).
    -> (fps, (w, h) of the sampled frames, iterator)."""
    import imageio

    from studio.audio import _ffmpeg

    r = imageio.get_reader(path, "ffmpeg")
    w0, h0 = r.get_meta_data()["size"]
    r.close()
    w = min(width, w0) // 2 * 2
    h = max(2, int(round(h0 * w / w0 / 2)) * 2)
    cmd = [_ffmpeg(), "-loglevel", "error", "-nostdin", "-i", path, "-vf", f"fps={fps},scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]

    def gen():
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        n = w * h * 3
        try:
            while True:
                b = p.stdout.read(n)
                if len(b) < n:
                    break
                yield np.frombuffer(b, np.uint8).reshape(h, w, 3)
        finally:
            p.stdout.close()
            p.wait()

    return fps, (w, h), gen()


# ---- text lines in one frame ------------------------------------------------------------------------------------------------
def _gray(f: np.ndarray) -> np.ndarray:
    return 0.299 * f[..., 0] + 0.587 * f[..., 1] + 0.114 * f[..., 2]


def _components(mask: np.ndarray, g: np.ndarray, light: bool, hmin: int, hmax: int, cap: int = 600):
    """Letter-like components: small, contrasting with their surroundings."""
    lab, n = ndi.label(mask, structure=np.ones((3, 3)))
    if n == 0 or n > cap:  # a frame full of specks is texture, not text
        return []
    out = []
    for i, sl in enumerate(ndi.find_objects(lab), 1):
        y0, y1, x0, x1 = sl[0].start, sl[0].stop, sl[1].start, sl[1].stop
        h, w = y1 - y0, x1 - x0
        if not (hmin <= h <= hmax and 1 <= w <= hmax * 1.6):
            continue
        reg = lab[max(0, y0 - 2) : y1 + 2, max(0, x0 - 2) : x1 + 2]
        gr = g[max(0, y0 - 2) : y1 + 2, max(0, x0 - 2) : x1 + 2]
        ring = gr[reg != i]
        if ring.size < 4:
            continue
        inner = g[sl][lab[sl] == i]
        contrast = (inner.mean() - ring.mean()) if light else (ring.mean() - inner.mean())
        if contrast >= 60:
            out.append((x0, y0, x1, y1))
    return out


def _rows(comps, wf: int) -> List[Tuple[int, int, int, int]]:
    """Group components into lines of text: aligned centres, similar heights, enough of them, wide enough."""
    if len(comps) < 5:
        return []
    comps = sorted(comps, key=lambda c: (c[1] + c[3]) / 2)
    lines, used = [], [False] * len(comps)
    for i, c in enumerate(comps):
        if used[i]:
            continue
        yc, hh = (c[1] + c[3]) / 2, c[3] - c[1]
        grp = [j for j, d in enumerate(comps) if not used[j] and abs((d[1] + d[3]) / 2 - yc) <= 0.6 * max(hh, 4)]
        if len(grp) < 5:
            continue
        hs = np.median([comps[j][3] - comps[j][1] for j in grp])
        grp = sorted([j for j in grp if 0.5 * hs <= comps[j][3] - comps[j][1] <= 1.9 * hs], key=lambda j: comps[j][0])
        xs0, xs1 = min(comps[j][0] for j in grp), max(comps[j][2] for j in grp)
        gaps = [comps[b][0] - comps[a][2] for a, b in zip(grp, grp[1:])]
        packed = len(gaps) > 0 and np.mean([g <= 2.0 * hs for g in gaps]) >= 0.7  # letters sit close together; scattered blobs (eyes, sparkles) do not
        if len(grp) >= 5 and (xs1 - xs0) >= 0.10 * wf and packed:
            lines.append((xs0, min(comps[j][1] for j in grp), xs1, max(comps[j][3] for j in grp)))
            for j in grp:
                used[j] = True
    return lines


def text_lines(frame: np.ndarray) -> List[Tuple[int, int, int, int]]:
    """Heuristic detector: boxes (x0, y0, x1, y1) in pixels of lines of white / yellow letter-like shapes with a darker surround
    (how burned-in subtitles and credits are drawn). Dark-on-light text is not searched: black outlines of a cartoon look like it."""
    g = _gray(frame)
    h, w = g.shape
    hmin, hmax = max(3, h // 70), max(8, h // 7)
    mn = frame.min(-1)
    # subtitle / credit fills are white or pure bright yellow; yellow *skin* (G ~ 215) and pale colours must not count (real cartoons!)
    light = (mn >= 200) | ((frame[..., 0] >= 235) & (frame[..., 1] >= 235) & (frame[..., 2] < 150))
    return _rows(_components(light, g, True, hmin, hmax), w)


def ocr_detector(name: str = "easyocr", languages=("en", "es")) -> Callable:
    """Plug a real text detector (needs `pip install easyocr` or `paddleocr`; not run in this repository's tests)."""
    if name == "easyocr":
        import easyocr

        rd = easyocr.Reader(list(languages), gpu=False)
        return lambda fr: [(int(min(p[0] for p in b)), int(min(p[1] for p in b)), int(max(p[0] for p in b)), int(max(p[1] for p in b)))
                           for b, _t, c in rd.readtext(fr) if c > 0.4]
    if name == "paddle":
        from paddleocr import PaddleOCR

        rd = PaddleOCR(use_angle_cls=False, lang="en", show_log=False)
        return lambda fr: [(int(min(p[0] for p in b[0])), int(min(p[1] for p in b[0])), int(max(p[0] for p in b[0])), int(max(p[1] for p in b[0])))
                           for b in (rd.ocr(fr, cls=False)[0] or []) if b[1][1] > 0.4]
    raise ValueError(f"detector desconocido: {name}")


# ---- video-level analysis -------------------------------------------------------------------------------------------------
def _bars(frames: List[np.ndarray]) -> Optional[List[float]]:
    """Letterbox / pillarbox: rows or columns that stay black over the whole video -> normalised crop (x0, y0, x1, y1)."""
    g = np.stack([_gray(f) for f in frames[:: max(1, len(frames) // 60)]])
    h, w = g.shape[1:]
    rows = (g.mean((0, 2)) < 14) & (g.std(2).mean(0) < 8)
    cols = (g.mean((0, 1)) < 14) & (g.std(1).mean(0) < 8)

    def run(v):
        a = 0
        while a < len(v) and v[a]:
            a += 1
        return a

    t, b, l, r = run(rows), run(rows[::-1]), run(cols), run(cols[::-1])
    if min(t + b + l + r, h) < 2 or (t < 0.02 * h and b < 0.02 * h and l < 0.02 * w and r < 0.02 * w):
        return None
    return [l / w, t / h, 1 - r / w, 1 - b / h]


def _static_boxes(frames: List[np.ndarray], bars, skip=()) -> List[dict]:
    """Logos / watermarks: edges that stay put while the picture around them changes shot after shot. `skip`: frame indices to
    ignore (title cards and credits, where channel logos usually disappear)."""
    if skip:
        keep = [f for i, f in enumerate(frames) if i not in set(skip)]
        frames = keep if len(keep) >= 8 else frames
    n = len(frames)
    if n < 8:
        return []
    gs = np.stack([_gray(f) for f in frames]).astype(np.float32)
    h, w = gs.shape[1:]
    chg = np.abs(np.diff(gs[:, ::4, ::4], axis=0)).mean((1, 2)) / 255.0
    if chg.mean() < 0.015:  # nothing moves at all: static content cannot be told from an overlay
        return []
    shot = np.concatenate([[0], np.cumsum(chg > 0.12)])
    shots = np.unique(shot)
    if len(shots) < 3:
        return []
    gx = np.abs(np.diff(gs, axis=2, prepend=gs[:, :, :1]))
    gy = np.abs(np.diff(gs, axis=1, prepend=gs[:, :1, :]))
    edge = (gx + gy) > 22
    pers = edge.mean(0)
    per_shot = np.stack([edge[shot == s].mean(0) for s in shots])
    cross = (per_shot >= 0.8).mean(0)
    m = (pers >= 0.85) & (cross >= 0.75)
    if bars:  # bar edges and everything inside the bars is not an overlay
        x0, y0, x1, y1 = bars
        keep = np.zeros_like(m)
        keep[int(y0 * h) + 2 : int(y1 * h) - 2, int(x0 * w) + 2 : int(x1 * w) - 2] = True
        m &= keep
    m = ndi.binary_closing(m, iterations=3)
    m = ndi.binary_dilation(m, iterations=2)
    lab, k = ndi.label(m)
    out = []
    for i, sl in enumerate(ndi.find_objects(lab), 1):
        y0, y1, x0, x1 = sl[0].start, sl[0].stop, sl[1].start, sl[1].stop
        area = (lab[sl] == i).sum() / (h * w)
        bw, bh = (x1 - x0) / w, (y1 - y0) / h
        if area < 0.0004 or bw > 0.45 or bh > 0.45 or (bw > 0.6 and bh < 0.02) or (bh > 0.6 and bw < 0.02):
            continue
        out.append({"box": [x0 / w, y0 / h, x1 / w, y1 / h], "kind": "logo", "persistence": float(pers[sl][lab[sl] == i].mean())})
    return out


def _flat(frame: np.ndarray) -> float:
    """Share of the frame taken by its most common (coarsely quantised) colour: credits and title cards sit on flat backgrounds."""
    q = (frame[::4, ::4] >> 5).astype(np.int32)
    return float(np.bincount((q[..., 0] * 64 + q[..., 1] * 8 + q[..., 2]).ravel(), minlength=512).max() / q[..., 0].size)


def _iou(a, b) -> float:
    iw, ih = min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])
    if iw <= 0 or ih <= 0:
        return 0.0
    i = iw * ih
    return i / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i)


def _merge_boxes(boxes, iou: float = 0.2):
    """Union boxes that overlap (the same line found as light and as dark shapes)."""
    boxes = [list(b) for b in boxes]
    changed = True
    while changed:
        changed = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                iw, ih = min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])
                if iw > 0 and ih > 0 and iw * ih / min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1])) > iou:
                    boxes[i] = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
                    boxes.pop(j)
                    changed = True
                    break
            if changed:
                break
    return [tuple(b) for b in boxes]


def _inside_static(line, static, w: int, h: int) -> bool:
    cx, cy = (line[0] + line[2]) / 2 / w, (line[1] + line[3]) / 2 / h
    return any(s["box"][0] <= cx <= s["box"][2] and s["box"][1] <= cy <= s["box"][3] for s in static)


def _merge(times: List[float], step: float, gap: float) -> List[List[float]]:
    out: List[List[float]] = []
    for t in sorted(times):
        if out and t - out[-1][1] <= gap + step:
            out[-1][1] = t + step
        else:
            out.append([t, t + step])
    return out


def analyze_frames(frames: Iterable[np.ndarray], fps: float, detector: Optional[Callable] = None, progress=None) -> Dict:
    """-> overlay report for a sequence of small RGB frames sampled at `fps`."""
    detector = detector or text_lines
    fl = [np.asarray(f) for f in frames]
    if not fl:
        return empty_report(fps)
    h, w = fl[0].shape[:2]
    lines = []
    for i, f in enumerate(fl):
        lines.append(detector(f))
        if progress and i % 20 == 0:
            progress(0.7 * i / len(fl))
    bars = _bars(fl)
    cards_at = [i for i, ls in enumerate(lines) if (len(_merge_boxes(ls)) >= 3 or sum((l[2] - l[0]) * (l[3] - l[1]) for l in _merge_boxes(ls)) / (w * h) >= 0.08) and _flat(fl[i]) >= 0.5]
    boxes = _static_boxes(fl, bars, skip=cards_at)
    lines = [_merge_boxes([l for l in ls if not _inside_static(l, boxes, w, h)]) for ls in lines]  # a logo's letters are the logo, not subtitles
    progress and progress(0.9)
    step = 1.0 / fps
    # A subtitle is a line that (1) sits in the same narrow band in many frames of different shots, (2) keeps one font size,
    # (3) stays put for more than one sample. Specks that happen to look like letters (eyes, teeth, highlights) are scattered.
    flat = [_flat(f) for f in fl]
    cy = np.array([(l[1] + l[3]) / 2 / h for ls in lines for l in ls])
    hist = np.histogram(cy, bins=np.linspace(0, 1, 21))[0] if len(cy) else np.zeros(20)
    tot = max(1, int(hist.sum()))
    band_bins = {i for i, c in enumerate(hist) if c >= max(4, int(0.04 * len(fl))) and c >= 0.25 * tot}
    if band_bins:  # same font size in the band
        hh = np.array([(l[3] - l[1]) for ls in lines for l in ls if min(int(((l[1] + l[3]) / 2 / h) * 20), 19) in band_bins], float)
        if len(hh) and hh.std() > 0.45 * hh.mean():
            band_bins = set()
    sub_t, card_t, sub_boxes = [], [], []
    for i, ls in enumerate(lines):
        if not ls:
            continue
        t = i * step
        cover = sum((l[2] - l[0]) * (l[3] - l[1]) for l in ls) / (w * h)
        in_band = [l for l in ls if min(int(((l[1] + l[3]) / 2 / h) * 20), 19) in band_bins]
        stable = [l for l in in_band if any(_iou(l, m) >= 0.5 for j in (i - 1, i + 1) if 0 <= j < len(lines) for m in lines[j])]
        if (len(ls) >= 3 or cover >= 0.08) and flat[i] >= 0.5:  # title card / credits: several lines on a mostly flat background
            card_t.append(t)
        elif stable:
            sub_t.append(t)
            sub_boxes += stable
    subs = _merge(sub_t, step, 1.0)
    cards = [s for s in _merge(card_t, step, 1.0) if s[1] - s[0] >= 1.0]
    bands = []
    if sub_boxes:
        arr = np.array(sub_boxes, np.float32)
        yc = (arr[:, 1] + arr[:, 3]) / 2 / h
        order = np.argsort(yc)
        groups, cur = [], [order[0]]
        for j in order[1:]:
            if yc[j] - yc[cur[-1]] <= 0.06:
                cur.append(j)
            else:
                groups.append(cur)
                cur = [j]
        groups.append(cur)
        for g in groups:
            if len(g) >= 2:
                a = arr[g]
                bands.append([float(a[:, 0].min() / w), float(a[:, 1].min() / h), float(a[:, 2].max() / w), float(a[:, 3].max() / h)])
    n_bad = len({int(t * fps) for s in subs for t in np.arange(s[0], s[1], step)} | {int(t * fps) for s in cards for t in np.arange(s[0], s[1], step)})
    rep = empty_report(fps)
    rep.update(size=[w, h], frames=len(fl), duration=len(fl) / fps, bars=bars, static=boxes, subtitle_bands=bands, subtitle_intervals=subs,
               text_segments=cards, text_frame_ratio=round(n_bad / len(fl), 4), detector=getattr(detector, "__name__", "custom"))
    return rep


def empty_report(fps: float = 2.0) -> Dict:
    return {"fps": fps, "size": [0, 0], "frames": 0, "duration": 0.0, "bars": None, "static": [], "subtitle_bands": [], "subtitle_intervals": [],
            "text_segments": [], "text_frame_ratio": 0.0, "detector": "none"}


def scan_video(path: str, fps: float = 2.0, width: int = 480, detector: Optional[Callable] = None, progress=None) -> Dict:
    f, _, it = sample_frames(path, fps, width)
    rep = analyze_frames(it, f, detector, progress)
    rep["video"] = path
    rep["version"] = VERSION
    return rep


def clean(rep: Dict) -> bool:
    return not (rep["static"] or rep["subtitle_intervals"] or rep["text_segments"] or rep["bars"])


def describe_es(rep: Dict) -> str:
    bits = []
    if rep["static"]:
        bits.append(f"{len(rep['static'])} logo(s)/marca(s) de agua fijos")
    if rep["subtitle_intervals"]:
        bits.append(f"subtítulos incrustados en {sum(b - a for a, b in rep['subtitle_intervals']):.0f} s")
    if rep["text_segments"]:
        bits.append(f"{len(rep['text_segments'])} rótulo(s)/créditos ({sum(b - a for a, b in rep['text_segments']):.0f} s, excluidos)")
    if rep["bars"]:
        bits.append("barras negras (se recortan)")
    return "; ".join(bits) or "sin texto ni logos incrustados"


# ---- using a report ----------------------------------------------------------------------------------------------------------
def excluded_ranges(rep: Dict, pad: float = 0.5) -> List[Tuple[float, float]]:
    """Time ranges (seconds) that must not become training clips: title cards / credits."""
    return [(max(0.0, a - pad), b + pad) for a, b in rep.get("text_segments", [])]


def overlaps_excluded(rep: Dict, start: float, dur: float) -> bool:
    return any(a < start + dur and b > start for a, b in excluded_ranges(rep))


def _pixel_boxes_at(rep: Dict, t: float, margin: float = 0.012) -> List[List[float]]:
    """Normalised boxes (in the source frame) that are overlay at time t."""
    out = [list(s["box"]) for s in rep.get("static", [])]
    if any(a - 0.5 <= t <= b + 0.5 for a, b in rep.get("subtitle_intervals", [])):
        out += [list(b) for b in rep.get("subtitle_bands", [])]
    out += [[0.0, 0.0, 1.0, 1.0]] if any(a <= t <= b for a, b in excluded_ranges(rep, 0.0)) else []
    return [[max(0.0, b[0] - margin), max(0.0, b[1] - margin), min(1.0, b[2] + margin), min(1.0, b[3] + margin)] for b in out]


def crop_rect(rep: Dict, mode: str, src_wh: Tuple[int, int]) -> Tuple[int, int, int, int]:
    """Pixels of the source that are kept: bars are always cropped; in `crop` mode a subtitle band touching the top / bottom too."""
    sw, sh = src_wh
    x0, y0, x1, y1 = rep["bars"] if rep.get("bars") else (0.0, 0.0, 1.0, 1.0)
    px0, py0, px1, py1 = int(x0 * sw), int(y0 * sh), int(x1 * sw) // 2 * 2, int(y1 * sh) // 2 * 2
    if mode == "crop" and rep.get("subtitle_bands"):
        tops = [b[3] for b in rep["subtitle_bands"] if b[3] < 0.4]
        bots = [b[1] for b in rep["subtitle_bands"] if b[1] > 0.6]
        ny0, ny1 = max([py0] + [int(t * sh) for t in tops]), min([py1] + [int(t * sh) for t in bots])
        if ny1 - ny0 >= 0.6 * (py1 - py0):  # never cut away more than 40 % of the picture
            py0, py1 = ny0, ny1 // 2 * 2
    return px0, py0, px1, py1


def _clip_geometry(rep: Dict, src_wh: Tuple[int, int], mode: str = "mask"):
    """Source pixel -> clip pixel: crop, then scale-to-fill and centre-crop to 720 x 480."""
    x0, y0, x1, y1 = crop_rect(rep, mode, src_wh)
    cw, ch = x1 - x0, y1 - y0
    s = max(CLIP_SIZE[0] / cw, CLIP_SIZE[1] / ch)
    return x0, y0, s, (cw * s - CLIP_SIZE[0]) / 2, (ch * s - CLIP_SIZE[1]) / 2


def clip_loss_mask(rep: Dict, src_wh: Tuple[int, int], start: float, dur: float, grid: Tuple[int, int] = LATENT_GRID, thr: float = 0.15,
                   mode: str = "mask") -> np.ndarray:
    """[T_latent, 60, 90] float32: 1 = learn, 0 = overlay (no gradient). Latent frame t shows time start + t / 4."""
    from hypercartoon.models.cogvideo.control_data import latent_frames  # same convention as the control files

    T = latent_frames(dur)
    sw, sh = src_wh
    cx0, cy0, s, ox, oy = _clip_geometry(rep, src_wh, mode)
    gh, gw = grid
    out = np.ones((T, gh, gw), np.float32)
    ph, pw = CLIP_SIZE[1], CLIP_SIZE[0]
    for t in range(T):
        cov = np.zeros((ph, pw), bool)
        for b in _pixel_boxes_at(rep, start + t / 4.0):
            x0 = (b[0] * sw - cx0) * s - ox
            x1 = (b[2] * sw - cx0) * s - ox
            y0 = (b[1] * sh - cy0) * s - oy
            y1 = (b[3] * sh - cy0) * s - oy
            x0, x1, y0, y1 = int(max(0, np.floor(x0))), int(min(pw, np.ceil(x1))), int(max(0, np.floor(y0))), int(min(ph, np.ceil(y1)))
            if x1 > x0 and y1 > y0:
                cov[y0:y1, x0:x1] = True
        if cov.any():
            frac = cov.reshape(gh, ph // gh, gw, pw // gw).mean((1, 3))
            out[t][frac >= thr] = 0.0
    return out


def ffmpeg_filter(rep: Dict, mode: str, src_wh: Tuple[int, int]) -> str:
    """Filters (before the scale/crop to 720x480) that clean the picture while cutting a clip. mask: bars only; delogo: + static
    logos; crop: + subtitle bands at the top/bottom edge; off: nothing. The loss mask is independent of this."""
    if mode == "off" or not rep:
        return ""
    sw, sh = src_wh
    x0, y0, x1, y1 = crop_rect(rep, mode, src_wh)
    f: List[str] = []
    if (x0, y0, x1, y1) != (0, 0, sw, sh):
        f.append(f"crop={x1 - x0}:{y1 - y0}:{x0}:{y0}")
    if mode == "delogo":
        for s_ in rep.get("static", []):
            bx0, by0, bx1, by1 = s_["box"]
            x, y = max(1, int(bx0 * sw) - x0), max(1, int(by0 * sh) - y0)
            w, h = min(int((bx1 - bx0) * sw), (x1 - x0) - x - 1), min(int((by1 - by0) * sh), (y1 - y0) - y - 1)
            if w > 2 and h > 2:
                f.append(f"delogo=x={x}:y={y}:w={w}:h={h}")
    return ",".join(f)


def sanitize_caption(text: str) -> str:
    """Captions describe the animation only: drop any mention of text, subtitles, logos, watermarks, credits or letters."""
    t = _CAPTION_TEXT.sub("", text)
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r"\s+([.,;])", r"\1", t)
    t = re.sub(r"([.,;])\s*([.,;])+", r"\1", t)
    return t.strip(" ,;")


# ---- generated video -----------------------------------------------------------------------------------------------------------
def text_intrusion(frames: Iterable[np.ndarray], detector: Optional[Callable] = None) -> Dict[str, float]:
    """How much text / static overlay a *generated* video contains. 0 = none. Uses the same detectors as learning."""
    fl = list(frames)
    rep = analyze_frames(fl, 2.0, detector)
    return {"text_frames": rep["text_frame_ratio"], "static_overlays": float(len(rep["static"])),
            "intrusion": float(min(1.0, rep["text_frame_ratio"] + 0.25 * len(rep["static"])))}


def score_video_intrusion(path: str, detector: Optional[Callable] = None) -> Dict[str, float]:
    f, _, it = sample_frames(path, 2.0, 480)
    return text_intrusion(it, detector)


# ---- project files ---------------------------------------------------------------------------------------------------------------
def report_path(ws: str, video: str) -> str:
    return os.path.join(ws, "overlays", os.path.splitext(os.path.basename(video))[0] + ".overlay.json")


def save_report(ws: str, video: str, rep: Dict) -> str:
    p = report_path(ws, video)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(rep, open(p, "w"), indent=1)
    return p


def load_reports(ws: str) -> Dict[str, Dict]:
    idx = os.path.join(ws, "overlays", "index.json")
    if not os.path.exists(idx):
        return {}
    out = {}
    for video, rel in json.load(open(idx)).items():
        p = os.path.join(ws, rel)
        if os.path.exists(p):
            out[video] = json.load(open(p))
    return out
