"""Knowledge in layers, not in one container.

What the studio learns is stored by *kind*, per show, and then across every show of a studio:

  characters    who appears (identity from the registry, or the labelled agents of the shots) and how much
  backgrounds   the colour of the places, how open or busy the frame is, the scenery that shows up
  palettes      the colours of the whole show, of shadows / mids / highlights, and of every kind of shot
  scene_types   the grammar of the shots: framing x camera movement x length, with how often each is used
  rhythm        shot length, cuts per minute, camera and dialogue density

Per series (`layers/<series>/<layer>.json`) and for the whole studio (`layers/_studio/`), where each layer is *pooled* (palettes,
backgrounds), *averaged with its spread* (rhythm) or *compared* (scene types: what every show does = the studio signature, what only
one does = show-specific). Characters are never averaged: each keeps its series.
`compose()` then builds a **new style** from any mix of sources per layer — "the studio's palette, show A's rhythm, A+B's characters" —
and writes `layers/<name>/style.json`, which `studio create --style-layers NAME` uses as the style of the episode.
Everything is computed from the analysis the learning already produced; nothing here needs a model or a GPU."""
import json
import os
import shutil
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from studio import corpus as C

LAYERS = ("characters", "backgrounds", "palettes", "scene_types", "rhythm")
STUDIO = "_studio"
SEEN_MIN = 0.02            # a scene type counts as "used" by a show above 2 % of its shots


def _q(rgb) -> Tuple[int, int, int]:
    return tuple(int(c) >> 4 for c in rgb)


def pool_palette(entries: Sequence[Tuple[Sequence[Dict], float]], k: int = 8) -> List[Dict]:
    """[(palette [{'rgb','pct'}], weight)] -> one palette of k colours: shares are weighted, near colours (16 levels / channel) merge."""
    acc: Dict[Tuple[int, int, int], List] = defaultdict(lambda: [0.0, np.zeros(3)])
    tot = 0.0
    for pal, w in entries:
        for c in pal:
            share = c["pct"] * w
            a = acc[_q(c["rgb"])]
            a[0] += share
            a[1] += np.asarray(c["rgb"], float) * share
            tot += share
    rows = sorted(acc.values(), key=lambda a: -a[0])[:k]
    return [{"rgb": [int(round(x)) for x in a[1] / max(a[0], 1e-9)], "pct": round(100.0 * a[0] / max(tot, 1e-9), 2)} for a in rows]


def _name(rgb) -> str:
    from studio.dataset import color_name

    return color_name(rgb)


def _minutes(a: Dict) -> float:
    return float(a.get("duration", 0.0)) / 60.0


def _brightness(pal: Sequence[Dict]) -> float:
    return float(sum((0.299 * c["rgb"][0] + 0.587 * c["rgb"][1] + 0.114 * c["rgb"][2]) / 255 * c["pct"] for c in pal) / max(sum(c["pct"] for c in pal), 1e-9))


# ---- the five layers of one series, from its analyses ----------------------------------------------------------------------------------------
def layer_palettes(analyses: Sequence[Dict]) -> Dict:
    w = [max(_minutes(a), 1e-6) for a in analyses]
    cols = [a.get("color") for a in analyses]
    have = [(c, wi) for c, wi in zip(cols, w) if c]
    out = {"minutes": sum(w), "global": pool_palette([(c["palette"], wi) for c, wi in have]), "bands": {}, "by_shot_type": {}, "metrics": {}}
    for band in ("shadows", "mids", "highlights"):
        out["bands"][band] = pool_palette([(c["bands"][band]["palette"], wi) for c, wi in have if band in c.get("bands", {}) and c["bands"][band]["palette"]], 4)
    by: Dict[str, List] = defaultdict(list)
    for a, wi in zip(analyses, w):
        for s in a["shots"]:
            if s.get("color") and s["color"].get("palette"):
                by[s["framing"]["shot_type"]].append((s["color"]["palette"], s["duration"]))
    out["by_shot_type"] = {t: pool_palette(v, 5) for t, v in by.items() if t != "sin datos"}
    if have:
        keys = have[0][0]["metrics"].keys()
        out["metrics"] = {k: float(sum(c["metrics"][k] * wi for c, wi in have) / sum(wi for _, wi in have)) for k in keys}
    out["brightness"] = _brightness(out["global"])
    return out


def layer_backgrounds(analyses: Sequence[Dict], k: int = 6) -> Dict:
    pts, wts, free, scenery = [], [], [], Counter()
    for a in analyses:
        for sc in a.get("scenes", []):
            if sc.get("palette"):
                top = sc["palette"][0]
                pts.append(top["rgb"])
                wts.append(max(sc["end"] - sc["start"], 0.1))
        for s in a["shots"]:
            free.append((s["framing"].get("free_space_pct", 0.0), s["duration"]))
            for e in s.get("labelled", []):
                if e["kind"] == "scenery":
                    scenery[e["label"]] += 1
    if not pts:
        return {"places": [], "open_space_pct": 0.0, "scenery": {}, "scenes": 0}
    X, W = np.asarray(pts, float), np.asarray(wts)
    cent = X[np.argsort(-W)[: min(k, len(X))]].copy()
    for _ in range(8):  # weighted k-means on the background colour of every scene
        lab = np.argmin(((X[:, None] - cent[None]) ** 2).sum(-1), 1)
        for j in range(len(cent)):
            if (lab == j).any():
                cent[j] = (X[lab == j] * W[lab == j, None]).sum(0) / W[lab == j].sum()
    lab = np.argmin(((X[:, None] - cent[None]) ** 2).sum(-1), 1)
    places = sorted(({"rgb": [int(round(v)) for v in cent[j]], "share": float(W[lab == j].sum() / W.sum()),
                      "name": _name(cent[j])} for j in range(len(cent)) if (lab == j).any()), key=lambda p: -p["share"])
    fw = sum(d for _, d in free)
    return {"places": places, "open_space_pct": float(sum(f * d for f, d in free) / max(fw, 1e-9)), "scenery": dict(scenery.most_common(15)), "scenes": len(pts)}


def pace_word(d: float) -> str:
    return "quick" if d < 1.5 else "medium" if d < 4.0 else "long"


def layer_scene_types(analyses: Sequence[Dict]) -> Dict:
    """The grammar of the shots: a type = framing x camera movement x pace; share of shots, mean length, typical subject cell, elements."""
    rows: Dict[str, Dict] = {}
    n = 0
    for a in analyses:
        for s in a["shots"]:
            if s["framing"]["shot_type"] == "sin datos":
                continue
            n += 1
            key = f"{s['framing']['shot_type']} · {s['camera']['label']} · {pace_word(s['duration'])}"
            r = rows.setdefault(key, {"n": 0, "dur": 0.0, "cells": Counter(), "kinds": Counter(), "chars": 0})
            r["n"] += 1
            r["dur"] += s["duration"]
            if s["framing"].get("subject"):
                r["cells"][s["framing"]["subject"]["cell"]] += 1
            r["chars"] += s["framing"].get("n_characters", 0)
            for e in s.get("labelled", []):
                r["kinds"][e["kind"]] += 1
    types = sorted(({"type": k, "share": r["n"] / max(n, 1), "shots": r["n"], "mean_s": r["dur"] / r["n"],
                     "subject_cell": r["cells"].most_common(1)[0][0] if r["cells"] else None, "characters": r["chars"] / r["n"],
                     "elements": dict(r["kinds"].most_common(4))} for k, r in rows.items()), key=lambda t: -t["share"])
    return {"shots": n, "types": types}


def layer_rhythm(analyses: Sequence[Dict]) -> Dict:
    d = np.array([s["duration"] for a in analyses for s in a["shots"]]) if analyses else np.zeros(0)
    minutes = sum(_minutes(a) for a in analyses)
    cam = Counter(s["camera"]["label"] for a in analyses for s in a["shots"])
    nshots = max(1, sum(cam.values()))
    return {"minutes": minutes, "shots": int(len(d)), "cuts_per_min": float(len(d) / max(minutes, 1e-9)) if len(d) else 0.0,
            "shot_len": {"median": float(np.median(d)), "p10": float(np.percentile(d, 10)), "p90": float(np.percentile(d, 90))} if len(d) else {},
            "camera": {k: v / nshots for k, v in cam.most_common()},
            "dialogue_lines_per_min": float(sum(len(a.get("dialogue", [])) for a in analyses) / max(minutes, 1e-9))}


def layer_characters(analyses: Sequence[Dict], registry_rows: Optional[Sequence[Dict]] = None) -> Dict:
    """Agents (people, animals) seen in the shots, grouped by label and dominant colour; the registry adds identity, name and voice."""
    seen: Dict[Tuple[str, str], Dict] = {}
    for a in analyses:
        for s in a["shots"]:
            for e in s.get("labelled", []):
                if not e.get("agent"):
                    continue
                r = seen.setdefault((e["label"], e["color"]), {"label": e["label"], "color": e["color"], "shots": 0, "seconds": 0.0, "caption": e["caption"]})
                r["shots"] += 1
                r["seconds"] += s["duration"] * e["presence"]
    out = {"seen": sorted(seen.values(), key=lambda r: -r["seconds"])[:30]}
    out["registry"] = [{k: c.get(k) for k in ("id", "name", "kind", "seconds_on_screen", "episodes", "voice_id", "voice_lift")} for c in (registry_rows or [])]
    return out


def build_series_layers(analyses: Sequence[Dict], registry_rows: Optional[Sequence[Dict]] = None) -> Dict[str, Dict]:
    return {"palettes": layer_palettes(analyses), "backgrounds": layer_backgrounds(analyses), "scene_types": layer_scene_types(analyses),
            "rhythm": layer_rhythm(analyses), "characters": layer_characters(analyses, registry_rows)}


# ---- across the shows of a studio -----------------------------------------------------------------------------------------------------------------
def _w(per: Dict[str, Dict], weights: Optional[Dict[str, float]] = None) -> Dict[str, float]:
    w = {s: (weights or {}).get(s, per[s]["rhythm"].get("minutes", 0.0) or 1.0) for s in per}
    t = sum(w.values()) or 1.0
    return {s: v / t for s, v in w.items()}


def merge_palettes(per: Dict[str, Dict], w: Dict[str, float]) -> Dict:
    out = {"global": pool_palette([(per[s]["palettes"]["global"], w[s]) for s in per]), "bands": {}, "by_shot_type": {}, "metrics": {}}
    for band in ("shadows", "mids", "highlights"):
        out["bands"][band] = pool_palette([(per[s]["palettes"]["bands"].get(band, []), w[s]) for s in per if per[s]["palettes"]["bands"].get(band)], 4)
    types = {t for s in per for t in per[s]["palettes"]["by_shot_type"]}
    out["by_shot_type"] = {t: pool_palette([(per[s]["palettes"]["by_shot_type"][t], w[s]) for s in per if t in per[s]["palettes"]["by_shot_type"]], 5) for t in types}
    ms = [s for s in per if per[s]["palettes"]["metrics"]]
    if ms:
        out["metrics"] = {k: float(sum(per[s]["palettes"]["metrics"][k] * w[s] for s in ms) / sum(w[s] for s in ms)) for k in per[ms[0]]["palettes"]["metrics"]}
    out["brightness"] = _brightness(out["global"])
    return out


def merge_backgrounds(per: Dict[str, Dict], w: Dict[str, float]) -> Dict:
    places = pool_palette([([{"rgb": p["rgb"], "pct": p["share"] * 100} for p in per[s]["backgrounds"]["places"]], w[s]) for s in per], 6)
    sc: Counter = Counter()
    for s in per:
        sc.update(per[s]["backgrounds"]["scenery"])
    return {"places": [{"rgb": p["rgb"], "share": p["pct"] / 100, "name": _name(p["rgb"])} for p in places],
            "open_space_pct": float(sum(per[s]["backgrounds"]["open_space_pct"] * w[s] for s in per)), "scenery": dict(sc.most_common(15)),
            "scenes": sum(per[s]["backgrounds"]["scenes"] for s in per)}


def merge_scene_types(per: Dict[str, Dict], w: Dict[str, float]) -> Dict:
    """Weighted share of each type; `consistency` = fraction of shows that really use it. Used by every show = studio signature."""
    names = {t["type"] for s in per for t in per[s]["scene_types"]["types"]}
    rows = []
    for n in names:
        sh = {s: next((t["share"] for t in per[s]["scene_types"]["types"] if t["type"] == n), 0.0) for s in per}
        mean_s = [next(t["mean_s"] for t in per[s]["scene_types"]["types"] if t["type"] == n) for s in per if sh[s] > 0]
        cons = sum(v >= SEEN_MIN for v in sh.values()) / len(per)
        rows.append({"type": n, "share": float(sum(sh[s] * w[s] for s in per)), "consistency": cons, "mean_s": float(np.mean(mean_s)),
                     "by_series": {s: round(v, 4) for s, v in sh.items()}, "signature": cons == 1.0 and len(per) > 1 and sum(sh[s] * w[s] for s in per) >= 0.05,
                     "specific_to": [s for s, v in sh.items() if v >= SEEN_MIN] if len(per) > 1 and cons < 1.0 else []})
    return {"shots": sum(per[s]["scene_types"]["shots"] for s in per), "types": sorted(rows, key=lambda r: -r["share"])}


def merge_rhythm(per: Dict[str, Dict], w: Dict[str, float]) -> Dict:
    def stat(get):
        v = np.array([get(per[s]) for s in per], float)
        ww = np.array([w[s] for s in per])
        m = float((v * ww).sum())
        return {"mean": m, "spread": float(np.sqrt(((v - m) ** 2 * ww).sum())), "by_series": {s: float(get(per[s])) for s in per}}

    cam: Counter = Counter()
    for s in per:
        for k, v in per[s]["rhythm"]["camera"].items():
            cam[k] += v * w[s]
    return {"minutes": sum(per[s]["rhythm"]["minutes"] for s in per), "cuts_per_min": stat(lambda p: p["rhythm"]["cuts_per_min"]),
            "median_shot_s": stat(lambda p: p["rhythm"]["shot_len"].get("median", 0.0)),
            "dialogue_lines_per_min": stat(lambda p: p["rhythm"]["dialogue_lines_per_min"]), "camera": dict(cam.most_common())}


def merge_characters(per: Dict[str, Dict]) -> Dict:
    return {"by_series": {s: per[s]["characters"] for s in per}, "agents": sum(len(per[s]["characters"]["seen"]) for s in per)}


def merge_layers(per: Dict[str, Dict], weights: Optional[Dict[str, float]] = None) -> Dict[str, Dict]:
    w = _w(per, weights)
    return {"palettes": merge_palettes(per, w), "backgrounds": merge_backgrounds(per, w), "scene_types": merge_scene_types(per, w),
            "rhythm": merge_rhythm(per, w), "characters": merge_characters(per), "sources": w}


def studio_spread(per: Dict[str, Dict]) -> Dict:
    """How different the shows are from each other (0 = identical palette): the studio has one look if this is small."""
    from studio.analysis.color import palette_change

    names = list(per)
    d = [palette_change(per[a]["palettes"]["global"], per[b]["palettes"]["global"]) for i, a in enumerate(names) for b in names[i + 1:]]
    return {"series": len(names), "palette_distance_mean": float(np.mean(d)) if d else 0.0, "palette_distance_max": float(np.max(d)) if d else 0.0}


# ---- a style out of the layers -------------------------------------------------------------------------------------------------------------------
def style_from_layers(L: Dict[str, Dict]) -> Dict:
    """The words and numbers a creation run needs: a style prompt plus the palette / rhythm / grammar it comes from."""
    from studio.profile import style_prompt

    r = L["rhythm"]
    cpm = r["cuts_per_min"]["mean"] if isinstance(r["cuts_per_min"], dict) else r["cuts_per_min"]
    from studio.dataset import EN_CAM, EN_TYPE

    cam = EN_CAM.get(max(r["camera"], key=r["camera"].get), "") if r["camera"] else ""   # the prompt the generator reads is English
    cols = list(dict.fromkeys(_name(c["rgb"]) for c in L["palettes"]["global"][:6]))[:4]
    types = [EN_TYPE.get(t["type"].split(" · ")[0], "") for t in L["scene_types"]["types"][:3]]
    types = [t for t in types if t]
    base = style_prompt({"cuts_per_min": cpm, "motion": 0.04, "brightness": L["palettes"].get("brightness", 0.5)})
    parts = [base, f"palette of {', '.join(cols[:-1])} and {cols[-1]}" if len(cols) > 1 else f"{cols[0]} palette" if cols else "",
             f"mostly {' and '.join(dict.fromkeys(types))} shots" if types else "", cam]
    sig = [t["type"] for t in L["scene_types"]["types"] if t.get("signature")]
    return {"style_prompt": ", ".join(p for p in parts if p), "palette": L["palettes"]["global"], "cuts_per_min": cpm,
            "signature_scene_types": sig, "sources": L.get("sources")}


def _norm(spec_v, names: Sequence[str]) -> Dict[str, float]:
    if isinstance(spec_v, str):
        spec_v = {spec_v: 1.0}
    elif isinstance(spec_v, (list, tuple)):
        spec_v = {s: 1.0 for s in spec_v}
    bad = [s for s in spec_v if s not in names]
    if bad:
        raise ValueError(f"fuente desconocida {bad}; disponibles: {list(names)}")
    t = sum(spec_v.values()) or 1.0
    return {s: v / t for s, v in spec_v.items()}


def compose(per: Dict[str, Dict], spec: Dict, name: str) -> Dict:
    """spec: {layer: source | [sources] | {source: weight}}, sources = series names or '_studio'. Layers not named use the studio blend.
    -> {'layers', 'style', 'spec'}: a new style that may take its palette from one show, its rhythm from another, its cast from both."""
    studio = merge_layers(per)
    pool = list(per) + [STUDIO]
    fns = {"palettes": merge_palettes, "backgrounds": merge_backgrounds, "scene_types": merge_scene_types, "rhythm": merge_rhythm}
    out: Dict[str, Dict] = {}
    for layer in LAYERS:
        srcs = _norm(spec.get(layer, STUDIO), pool)
        if srcs == {STUDIO: 1.0}:
            out[layer] = studio[layer]
            continue
        if STUDIO in srcs:  # the studio inside a mix = every show, equally
            share = srcs.pop(STUDIO)
            for s_ in per:
                srcs[s_] = srcs.get(s_, 0.0) + share / len(per)
        sub = {s_: per[s_] for s_ in srcs}
        out[layer] = fns[layer](sub, _w(sub, srcs)) if layer in fns else merge_characters(sub)
    out["sources"] = {l: _norm(spec.get(l, STUDIO), pool) for l in LAYERS}
    style = style_from_layers(out)
    style.update(name=name, kind="composed", spec={k: spec.get(k, STUDIO) for k in LAYERS})
    return {"layers": out, "style": style}


# ---- on disk --------------------------------------------------------------------------------------------------------------------------------------------
def _dir(ws: str, *p) -> str:
    return os.path.join(ws, "layers", *p)


def save_layers(ws: str, scope: str, layers: Dict, style: Optional[Dict] = None) -> None:
    os.makedirs(_dir(ws, scope), exist_ok=True)
    for k, v in layers.items():
        json.dump(v, open(_dir(ws, scope, f"{k}.json"), "w"), ensure_ascii=False, indent=1)
    if style:
        json.dump(style, open(_dir(ws, scope, "style.json"), "w"), ensure_ascii=False, indent=1)


def load_series_layers(ws: str) -> Dict[str, Dict]:
    root = _dir(ws)
    per: Dict[str, Dict] = {}
    if not os.path.isdir(root):
        return per
    for s in sorted(os.listdir(root)):
        d = os.path.join(root, s)
        if s.startswith("_") or not os.path.isdir(d) or not all(os.path.exists(os.path.join(d, f"{l}.json")) for l in LAYERS):
            continue
        if os.path.exists(os.path.join(d, "style.json")) and json.load(open(os.path.join(d, "style.json"))).get("kind") == "composed":
            continue
        per[s] = {l: json.load(open(os.path.join(d, f"{l}.json"))) for l in LAYERS}
    return per


def build(ws: str, progress=None) -> Dict:
    """Layers for every series of the project + the studio-wide merge + the studio style."""
    corpus = json.load(open(os.path.join(ws, "corpus.json")))
    idx_path = os.path.join(ws, "analysis", "index.json")
    if not os.path.exists(idx_path):
        raise FileNotFoundError("falta el análisis de vídeo (fase «Cámara, encuadre…»)")
    index = json.load(open(idx_path))
    reg_rows = None
    try:
        from studio.characters import Registry

        rp = os.path.join(ws, "registry.json")
        reg_rows = Registry.load(rp).characters() if os.path.exists(rp) else None
    except Exception:
        reg_rows = None
    per: Dict[str, Dict] = dict(load_series_layers(ws))   # series imported from other projects stay
    for n, (series, seasons) in enumerate(corpus.items()):
        analyses = []
        for eps in seasons.values():
            for e in eps:
                p = os.path.join(ws, index.get(e["path"], ""))
                if index.get(e["path"]) and os.path.exists(p):
                    analyses.append(json.load(open(p)))
        if analyses:
            per[series] = build_series_layers(analyses, reg_rows)
            save_layers(ws, series, per[series], style_from_layers({**per[series], "rhythm": per[series]["rhythm"]}))
        progress and progress((n + 1) / max(len(corpus), 1))
    if not per:
        raise RuntimeError("sin análisis utilizable para construir capas")
    studio = merge_layers(per)
    style = style_from_layers(studio)
    style.update(name=STUDIO, kind="studio", spread=studio_spread(per))
    save_layers(ws, STUDIO, {l: studio[l] for l in LAYERS}, style)
    json.dump({"series": sorted(per), "studio": STUDIO, "spread": style["spread"]}, open(_dir(ws, "index.json"), "w"), indent=1)
    return {"series": sorted(per), "style": style, "spread": style["spread"]}


def import_series(src_ws: str, dst_ws: str, prefix: str = "") -> List[str]:
    """Bring the per-series layers of another project (another show of the same studio) into this one; `build` then re-merges."""
    got = []
    for s, L in load_series_layers(src_ws).items():
        name = f"{prefix}{s}"
        save_layers(dst_ws, name, L)
        got.append(name)
    return got


def compose_project(ws: str, spec: Dict, name: str) -> Dict:
    per = load_series_layers(ws)
    if not per:
        raise RuntimeError("no hay capas: ejecuta `studio layers` primero")
    res = compose(per, spec, name)
    save_layers(ws, name, {l: res["layers"][l] for l in LAYERS}, res["style"])
    return res


def load_style(ws: str, name: str) -> Dict:
    p = _dir(ws, name, "style.json")
    if not os.path.exists(p):
        raise FileNotFoundError(f"no existe el estilo «{name}» en {_dir(ws)} (disponibles: {sorted(os.listdir(_dir(ws))) if os.path.isdir(_dir(ws)) else []})")
    return json.load(open(p))


def report_es(ws: str) -> str:
    per = load_series_layers(ws)
    st = json.load(open(_dir(ws, STUDIO, "style.json")))
    sc = json.load(open(_dir(ws, STUDIO, "scene_types.json")))
    L = ["# Capas del estudio", "", f"Series: {', '.join(per)}.", "", f"**Estilo del estudio:** {st['style_prompt']}", ""]
    sp = st.get("spread") or {}
    if sp.get("series", 0) > 1:
        L += [f"Distancia de paleta entre series: media {sp['palette_distance_mean']:.2f}, máxima {sp['palette_distance_max']:.2f} (0 = idénticas).", ""]
    L += ["## Gramática de planos", "", "| Tipo | Cuota | Consistencia | Nota |", "|---|---|---|---|"]
    for t in sc["types"][:10]:
        note = "firma del estudio" if t.get("signature") else (f"solo en {', '.join(t['specific_to'])}" if t.get("specific_to") else "")
        L.append(f"| {t['type']} | {t['share']:.0%} | {t['consistency']:.0%} | {note} |")
    share: Dict[str, float] = {}
    for c in st["palette"]:
        share[_name(c["rgb"])] = share.get(_name(c["rgb"]), 0.0) + c["pct"]
    L += ["", "## Paleta", "", " ".join(f"`{n} {v:.0f}%`" for n, v in sorted(share.items(), key=lambda kv: -kv[1])), ""]
    comp = [d for d in os.listdir(_dir(ws)) if os.path.isfile(_dir(ws, d, "style.json")) and json.load(open(_dir(ws, d, "style.json"))).get("kind") == "composed"]
    if comp:
        L += ["## Estilos compuestos", ""] + [f"- **{c}**: {json.load(open(_dir(ws, c, 'style.json')))['style_prompt']}" for c in comp]
    return "\n".join(L) + "\n"
