"""Colour analysis of a video, native (numpy): dominant colours by k-means in Lab, palettes per luminance band (shadows / mids /
highlights), per interval and per shot, and the usual colour-timeline pictures:

  colour strip      one dominant colour per time bin (Cinechroma / colour-strip style)
  fingerprint       stacked bars: the top-k colours of every time bin with their proportions (moviesColorFingerprint style)
  hue timeline      x = time, y = hue-ordered colour distribution (colorduce style)
  treemap           the global palette as a treemap of proportions (vidcolortree style)
Also colour metrics: warm/cool ratio, saturation, luminance contrast and how fast the palette changes (colour rhythm).
Those projects were the inspiration (their CLIs were not verified); this module implements the same views itself, no extra dependency."""
import colorsys
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

# ---- colour spaces ------------------------------------------------------------------------------------------------
_M = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]])
_WHITE = np.array([0.95047, 1.0, 1.08883])


def rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    c = np.asarray(rgb, float) / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    xyz = lin @ _M.T / _WHITE
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def luma(rgb: np.ndarray) -> np.ndarray:
    """Rec.709 luma of sRGB values (0..1)."""
    c = np.asarray(rgb, float) / 255.0
    return c @ np.array([0.2126, 0.7152, 0.0722])


def rgb_to_hsv(rgb: np.ndarray) -> np.ndarray:
    c = np.asarray(rgb, float) / 255.0
    mx, mn = c.max(-1), c.min(-1)
    d = mx - mn
    h = np.zeros_like(mx)
    m = d > 1e-9
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    h = np.where(m & (mx == r), ((g - b) / np.where(m, d, 1)) % 6, h)
    h = np.where(m & (mx == g), (b - r) / np.where(m, d, 1) + 2, h)
    h = np.where(m & (mx == b), (r - g) / np.where(m, d, 1) + 4, h)
    return np.stack([h * 60.0 % 360.0, np.where(mx > 0, d / np.where(mx > 0, mx, 1), 0), mx], -1)


# ---- k-means ---------------------------------------------------------------------------------------------------------
def kmeans(x: np.ndarray, k: int, iters: int = 20, seed: int = 0):
    """Deterministic k-means++ / Lloyd. -> (centres [k,d], labels [n])."""
    n = len(x)
    k = max(1, min(k, n))
    rng = np.random.default_rng(seed)
    c = [x[rng.integers(n)]]
    for _ in range(1, k):
        d2 = np.min(((x[:, None] - np.array(c)[None]) ** 2).sum(-1), 1)
        if d2.sum() <= 0:
            break
        c.append(x[rng.choice(n, p=d2 / d2.sum())])
    c = np.array(c)
    for _ in range(iters):
        lab = ((x[:, None] - c[None]) ** 2).sum(-1).argmin(1)
        new = np.array([x[lab == j].mean(0) if (lab == j).any() else c[j] for j in range(len(c))])
        if np.allclose(new, c, atol=1e-3):
            break
        c = new
    return c, ((x[:, None] - c[None]) ** 2).sum(-1).argmin(1)


def dominant_colors(pixels: np.ndarray, k: int = 5, max_pixels: int = 6000, seed: int = 0) -> List[Dict]:
    """Dominant colours of RGB pixels [N,3] (0..255): clustered in Lab, reported as RGB with their share, biggest first."""
    px = np.asarray(pixels, float).reshape(-1, 3)
    if len(px) == 0:
        return []
    if len(px) > max_pixels:
        px = px[np.random.default_rng(seed).choice(len(px), max_pixels, replace=False)]
    _, lab = kmeans(rgb_to_lab(px), k, seed=seed)
    out = []
    for j in np.unique(lab):
        m = lab == j
        rgb = px[m].mean(0)
        out.append({"rgb": [int(round(v)) for v in rgb], "pct": 100.0 * float(m.mean()), "hex": "#%02x%02x%02x" % tuple(int(round(v)) for v in rgb)})
    return sorted(out, key=lambda c: -c["pct"])


BANDS = (("sombras", 0.0, 1 / 3), ("medios", 1 / 3, 2 / 3), ("luces", 2 / 3, 1.0001))


def band_palettes(pixels: np.ndarray, k: int = 3) -> Dict[str, Dict]:
    """Palette per luminance band: shadows / mids / highlights, with the share of pixels in each band."""
    px = np.asarray(pixels, float).reshape(-1, 3)
    y = luma(px)
    out = {}
    for name, lo, hi in BANDS:
        m = (y >= lo) & (y < hi)
        out[name] = {"pixel_pct": 100.0 * float(m.mean()) if len(px) else 0.0, "palette": dominant_colors(px[m], k) if m.sum() >= 5 else []}
    return out


# ---- metrics ---------------------------------------------------------------------------------------------------------
def color_metrics(pixels: np.ndarray) -> Dict[str, float]:
    hsv = rgb_to_hsv(np.asarray(pixels, float).reshape(-1, 3))
    h, s, v = hsv[:, 0], hsv[:, 1], hsv[:, 2]
    colorful = s > 0.12
    warm = colorful & ((h <= 70) | (h >= 330))
    cool = colorful & (h >= 160) & (h <= 260)
    y = luma(pixels)
    return {"warm_pct": 100.0 * float(warm.mean()), "cool_pct": 100.0 * float(cool.mean()), "neutral_pct": 100.0 * float((~colorful).mean()),
            "saturation": float(s.mean()), "luminance": float(y.mean()), "contrast": float(y.std())}


def palette_change(p1: Sequence[Dict], p2: Sequence[Dict]) -> float:
    """0..1 distance between two palettes (nearest-colour, proportion-weighted, in Lab / 100)."""
    if not p1 or not p2:
        return 1.0
    a, b = rgb_to_lab(np.array([c["rgb"] for c in p1])), rgb_to_lab(np.array([c["rgb"] for c in p2]))
    wa, wb = np.array([c["pct"] for c in p1]) / 100, np.array([c["pct"] for c in p2]) / 100
    d = np.linalg.norm(a[:, None] - b[None], axis=-1) / 100.0
    return float(min(1.0, 0.5 * (d.min(1) @ wa + d.min(0) @ wb)))


# ---- per-video analysis ----------------------------------------------------------------------------------------------
def analyze_colors(samples: Sequence[Tuple[float, np.ndarray]], shots: Sequence[Dict], interval: float = 5.0, k: int = 5) -> Dict:
    """samples: [(time_s, frame_rgb_uint8_small)]; shots: [{start, end}] -> global / band / interval / per-shot palettes + metrics."""
    if not samples:
        raise ValueError("no frames to analyse")
    allpx = np.concatenate([f.reshape(-1, 3) for _, f in samples])
    t_end = max(t for t, _ in samples) + 1e-6
    bins: Dict[int, List[np.ndarray]] = {}
    for t, f in samples:
        bins.setdefault(int(t // interval), []).append(f.reshape(-1, 3))
    intervals = []
    for b in sorted(bins):
        px = np.concatenate(bins[b])
        intervals.append({"start": b * interval, "end": (b + 1) * interval, "palette": dominant_colors(px, k), "metrics": color_metrics(px)})
    per_shot = []
    for i, s in enumerate(shots):
        px = [f.reshape(-1, 3) for t, f in samples if s["start"] <= t < s["end"]]
        per_shot.append({"shot": i, "palette": dominant_colors(np.concatenate(px), k) if px else [], "metrics": color_metrics(np.concatenate(px)) if px else None})
    rhythm = [palette_change(a["palette"], b["palette"]) for a, b in zip(intervals, intervals[1:])]
    return {"palette": dominant_colors(allpx, 8), "bands": band_palettes(allpx), "metrics": color_metrics(allpx), "intervals": intervals,
            "per_shot": per_shot, "interval_s": interval, "duration_s": t_end,
            "rhythm": {"mean_change": float(np.mean(rhythm)) if rhythm else 0.0, "max_change": float(np.max(rhythm)) if rhythm else 0.0,
                       "label": ("paleta muy cambiante" if rhythm and np.mean(rhythm) > 0.25 else "paleta estable" if rhythm and np.mean(rhythm) < 0.08 else "paleta moderada") if rhythm else "sin datos"}}


# ---- pictures --------------------------------------------------------------------------------------------------------
def strip_image(intervals: Sequence[Dict], width: int = 960, height: int = 80) -> np.ndarray:
    """One dominant colour per time bin, stretched to `width` (a colour strip)."""
    cols = np.array([iv["palette"][0]["rgb"] if iv["palette"] else (0, 0, 0) for iv in intervals], np.uint8)
    idx = np.minimum(np.arange(width) * len(cols) // width, len(cols) - 1)
    return np.repeat(cols[idx][None], height, 0)


def fingerprint_image(intervals: Sequence[Dict], width: int = 960, height: int = 240) -> np.ndarray:
    """Per time bin the top-k colours stacked by proportion (the chromatic fingerprint over time)."""
    img = np.zeros((height, width, 3), np.uint8)
    n = len(intervals)
    for x in range(width):
        iv = intervals[min(x * n // width, n - 1)]
        y = 0
        for c in iv["palette"]:
            h = max(1, int(round(c["pct"] / 100 * height)))
            img[y : y + h, x] = c["rgb"]
            y += h
            if y >= height:
                break
    return img


def hue_timeline_image(samples: Sequence[Tuple[float, np.ndarray]], width: int = 480, height: int = 180, hue_bins: int = 90) -> np.ndarray:
    """x = time, y = hue (0..360, red at the top); a pixel's brightness is how much of that hue (weighted by saturation and value) the frame holds."""
    t0, t1 = min(t for t, _ in samples), max(t for t, _ in samples) + 1e-6
    cols = np.zeros((width, hue_bins))
    cnt = np.zeros(width)
    for t, f in samples:
        x = min(width - 1, int((t - t0) / (t1 - t0) * width))
        hsv = rgb_to_hsv(f.reshape(-1, 3))
        w = hsv[:, 1] * hsv[:, 2]
        cols[x] += np.bincount(np.minimum((hsv[:, 0] / 360 * hue_bins).astype(int), hue_bins - 1), weights=w, minlength=hue_bins)
        cnt[x] += 1
    filled = np.flatnonzero(cnt)
    for x in range(width):  # empty columns copy the previous one
        if cnt[x] == 0 and len(filled):
            cols[x], cnt[x] = cols[filled[filled < x][-1]] if (filled < x).any() else cols[filled[0]], 1
    cols = cols / np.maximum(cnt[:, None], 1)
    cols = cols / (cols.max() + 1e-9)
    img = np.zeros((height, width, 3), np.uint8)
    for yb in range(hue_bins):
        y0, y1 = yb * height // hue_bins, (yb + 1) * height // hue_bins
        base = np.array(colorsys.hsv_to_rgb((yb + 0.5) / hue_bins, 1, 1))
        img[y0:y1] = (base[None, None] * np.sqrt(cols[:, yb])[None, :, None] * 255).astype(np.uint8)
    return img


def squarify(sizes: Sequence[float], x: float, y: float, w: float, h: float) -> List[Tuple[float, float, float, float]]:
    """Squarified treemap layout (Bruls et al.): rectangles in input order for sizes sorted descending."""
    tot = float(sum(sizes))
    areas = [s / tot * w * h for s in sizes] if tot > 0 else [0] * len(sizes)
    rects: List[Tuple[float, float, float, float]] = []

    def worst(row, side):
        s = sum(row)
        return max(max(side * side * r / (s * s), s * s / (side * side * r)) for r in row if r > 0) if s > 0 else 1e9

    i = 0
    while i < len(areas):
        side = min(w, h)
        row = [areas[i]]
        j = i + 1
        while j < len(areas) and worst(row + [areas[j]], side) <= worst(row, side):
            row.append(areas[j])
            j += 1
        s = sum(row)
        if w >= h:           # lay the row as a column on the left
            cw = s / h if h > 0 else 0
            yy = y
            for a in row:
                hh = a / cw if cw > 0 else 0
                rects.append((x, yy, cw, hh))
                yy += hh
            x, w = x + cw, w - cw
        else:                # lay the row along the top
            rh = s / w if w > 0 else 0
            xx = x
            for a in row:
                ww = a / rh if rh > 0 else 0
                rects.append((xx, y, ww, rh))
                xx += ww
            y, h = y + rh, h - rh
        i = j
    return rects


def treemap_image(palette: Sequence[Dict], width: int = 640, height: int = 360) -> np.ndarray:
    pal = sorted(palette, key=lambda c: -c["pct"])
    img = np.zeros((height, width, 3), np.uint8)
    for c, (x, y, w, h) in zip(pal, squarify([c["pct"] for c in pal], 0, 0, width, height)):
        x0, y0, x1, y1 = int(round(x)), int(round(y)), int(round(x + w)), int(round(y + h))
        img[y0:y1, x0:x1] = c["rgb"]
        if y1 - y0 > 3 and x1 - x0 > 3:
            img[y0, x0:x1] = img[y1 - 1, x0:x1] = 255  # thin separators
            img[y0:y1, x0] = img[y0:y1, x1 - 1] = 255
    return img


def write_pictures(res: Dict, samples: Sequence[Tuple[float, np.ndarray]], out_dir: str, stem: str = "color") -> Dict[str, str]:
    import os

    import imageio

    os.makedirs(out_dir, exist_ok=True)
    paths = {}
    for name, img in (("strip", strip_image(res["intervals"])), ("fingerprint", fingerprint_image(res["intervals"])),
                      ("hue_timeline", hue_timeline_image(samples)), ("treemap", treemap_image(res["palette"]))):
        p = os.path.join(out_dir, f"{stem}_{name}.png")
        imageio.imwrite(p, img)
        paths[name] = p
    return paths


def descriptor_es(res: Dict) -> str:
    """Short phrase for prompts / captions: temperature, saturation, contrast, main colours."""
    m = res["metrics"]
    names = {"red": (220, 40, 40), "orange": (240, 140, 30), "yellow": (240, 220, 50), "green": (50, 180, 70), "teal": (40, 170, 170), "blue": (50, 80, 220),
             "purple": (140, 60, 190), "pink": (240, 130, 190), "brown": (130, 80, 40), "white": (240, 240, 240), "gray": (128, 128, 128), "black": (20, 20, 20)}

    def nm(rgb):
        return min(names, key=lambda k: sum((a - b) ** 2 for a, b in zip(rgb, names[k])))

    cols = list(dict.fromkeys(nm(c["rgb"]) for c in res["palette"][:4]))
    temp = "warm" if m["warm_pct"] > 1.5 * m["cool_pct"] else "cool" if m["cool_pct"] > 1.5 * m["warm_pct"] else "balanced"
    sat = "vivid" if m["saturation"] > 0.5 else "muted" if m["saturation"] < 0.25 else "moderately saturated"
    return f"{temp} {sat} palette of {', '.join(cols[:3])}"
