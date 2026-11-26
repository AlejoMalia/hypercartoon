"""Style fusion: from two or more learned projects build an *intermediate* one.

Three independent levels (use any):
 1. Concept level (CPU, deterministic): blend the learned profiles - pacing in log space, motion/brightness linearly, palette
    mixed in linear light, mouth convention, cast and voices united - into a new project that `create` can use directly.
 2. Embedding level (sampler): every segment is described in style A and in style B; the sampler interpolates the T5 text
    embeddings with weight `mix` (`alt_text` / `mix` in the prompt files, see hypercartoon/models/cogvideo/prompts.py).
 3. Weight level: interpolate two fine-tuned checkpoints of the same base (model soup) or add their task vectors.
Levels 2 and 3 only give a convincing in-between if the model has actually learned both styles (train on both, with a
distinct style token per source in the captions). Nothing in 2 and 3 has been run on a GPU here."""
import json
import math
import os
import shutil
from typing import Dict, List, Optional, Sequence

import numpy as np

from studio import profile as P
from studio.characters import Registry
from studio.pipeline import Phase, Skip

# ---- 1. concept level ----------------------------------------------------------------------------------------
def _norm(w: Sequence[float]) -> List[float]:
    s = float(sum(w))
    if s <= 0:
        raise ValueError("weights must sum to > 0")
    return [x / s for x in w]


def _geo(vals, w):
    return float(math.exp(sum(wi * math.log(max(v, 1e-9)) for v, wi in zip(vals, w))))


def _lin(c):
    c = np.asarray(c, float) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _srgb(l):
    l = np.clip(l, 0, 1)
    return (np.where(l <= 0.0031308, l * 12.92, 1.055 * l ** (1 / 2.4) - 0.055) * 255).round().astype(int)


def mix_colors(colors: Sequence[Sequence[int]], w: Sequence[float]) -> List[int]:
    """Weighted mix in linear light (mixing in sRGB makes muddy, too-dark midpoints)."""
    return [int(x) for x in _srgb(sum(wi * _lin(c) for c, wi in zip(colors, w)))]


def blend_profiles(profiles: Sequence[dict], weights: Sequence[float], names: Sequence[str]) -> dict:
    w = _norm(weights)
    out = {
        "n_videos": sum(p["n_videos"] for p in profiles), "total_seconds": sum(p["total_seconds"] for p in profiles),
        "fps": float(sum(wi * p["fps"] for wi, p in zip(w, profiles))), "aspect": float(sum(wi * p["aspect"] for wi, p in zip(w, profiles))),
        "motion": float(sum(wi * p["motion"] for wi, p in zip(w, profiles))), "brightness": float(sum(wi * p["brightness"] for wi, p in zip(w, profiles))),
        "shot_len": {k: _geo([p["shot_len"][k] for p in profiles], w) for k in ("median", "p10", "p90")},
        "cuts_per_min": _geo([p["cuts_per_min"] for p in profiles], w),
        "episode_seconds": [e for p in profiles for e in p["episode_seconds"]],
    }
    k = min(len(p.get("palette") or []) for p in profiles)
    out["palette"] = [mix_colors([p["palette"][i] for p in profiles], w) for i in range(min(k, 6))]
    out["chapter_seconds"] = _geo([p.get("chapter_seconds") or 1.0 for p in profiles], w)
    out["seasons"] = {f"{n}/{s}": v for n, p in zip(names, profiles) for s, v in (p.get("seasons") or {}).items()}
    out["sources"] = [{"name": n, "weight": round(wi, 4), "style_prompt": p.get("style_prompt"), "profile": {
        "cuts_per_min": p["cuts_per_min"], "motion": p["motion"], "brightness": p["brightness"], "shot_len": p["shot_len"]["median"]}}
        for n, wi, p in zip(names, w, profiles)]
    if all(p.get("cinematography") for p in profiles):  # blend the visual grammar (distributions weighted by the fusion weights)
        cin = {}
        for key in ("shot_types", "camera", "subject_cells"):
            agg = {}
            for wi, p in zip(w, profiles):
                for k, v in p["cinematography"][key].items():
                    agg[k] = agg.get(k, 0.0) + wi * v
            cin[key] = {k: round(v, 1) for k, v in sorted(agg.items(), key=lambda kv: -kv[1])}
        cin["mean_shot_s"] = _geo([p["cinematography"]["mean_shot_s"] for p in profiles], w)
        out["cinematography"] = cin
    desc = " and ".join(f"{n} ({wi * 100:.0f}%)" for n, wi in zip(names, w))
    out["style_prompt"] = P.style_prompt(out) + f", a blend of {desc} animation styles"
    return out


def _resample(levels, k):
    return np.interp(np.linspace(0, 1, k), np.linspace(0, 1, len(levels)), levels)


def blend_mouth_styles(styles: Sequence[Optional[dict]], weights: Sequence[float]) -> Optional[dict]:
    pairs = [(s, w) for s, w in zip(styles, weights) if s]
    if not pairs:
        return None
    w = _norm([x for _, x in pairs])
    k = max(len(s["levels"]) for s, _ in pairs)
    levels = sum(wi * _resample(s["levels"], k) for (s, _), wi in zip(pairs, w))
    return {"fps": int(round(sum(wi * s["fps"] for (s, _), wi in zip(pairs, w)))), "hold_frames": max(1, int(round(_geo([s["hold_frames"] for s, _ in pairs], w)))),
            "levels": [float(x) for x in levels], "lead_s": float(sum(wi * s["lead_s"] for (s, _), wi in zip(pairs, w))),
            "gain": float(sum(wi * s["gain"] for (s, _), wi in zip(pairs, w))), "n_samples": sum(s.get("n_samples", 0) for s, _ in pairs)}


def merge_registries(regs: Sequence[dict], tags: Sequence[str]):
    """Union of registries (JSON dicts). Visual / voice ids are shifted so they never clash; a character name that exists
    in several sources is suffixed with its source tag."""
    out = {"visual": {"thr": regs[0]["visual"]["thr"], "next": 1, "c": {}}, "voice": {"thr": regs[0]["voice"]["thr"], "next": 1, "c": {}},
           "overlap": {}, "presence": {}, "speech": {}, "total_time": 0.0, "names": {}, "labels": {}, "episodes": {}, "done": {}}
    counts: Dict[str, int] = {}
    for r in regs:
        for n in r.get("names", {}).values():
            counts[n] = counts.get(n, 0) + 1
    voff = aoff = 0
    maps = []
    for r, tag in zip(regs, tags):
        vm = {int(k): int(k) + voff for k in r["visual"]["c"]}
        am = {int(k): int(k) + aoff for k in r["voice"]["c"]}
        maps.append((vm, am))
        for k, v in r["visual"]["c"].items():
            out["visual"]["c"][str(vm[int(k)])] = v
        for k, v in r["voice"]["c"].items():
            out["voice"]["c"][str(am[int(k)])] = v
        for key, sec in r["overlap"].items():
            v, a = map(int, key.split("|"))
            out["overlap"][f"{vm.get(v, v + voff)}|{am.get(a, a + aoff)}"] = sec
        for k, v in r["presence"].items():
            out["presence"][str(vm.get(int(k), int(k) + voff))] = v
        for k, v in r["speech"].items():
            out["speech"][str(am.get(int(k), int(k) + aoff))] = v
        for k, v in r["names"].items():
            out["names"][str(vm.get(int(k), int(k) + voff))] = f"{v}_{tag.upper()}" if counts[v] > 1 else v
        for k, v in r["labels"].items():
            out["labels"][str(vm.get(int(k), int(k) + voff))] = v
        for k, v in r["episodes"].items():
            out["episodes"][str(vm.get(int(k), int(k) + voff))] = v
        out["done"].update(r.get("done", {}))
        out["total_time"] += r["total_time"]
        voff += max([int(k) for k in r["visual"]["c"]] + [r["visual"]["next"] - 1, 0])
        aoff += max([int(k) for k in r["voice"]["c"]] + [r["voice"]["next"] - 1, 0])
    out["visual"]["next"], out["voice"]["next"] = voff + 1, aoff + 1
    return out, maps


def merge_banks(src_ws: Sequence[str], maps, out_ws: str) -> dict:
    """Copy reference voices / ambience beds into the fused project with the shifted voice ids."""
    man = {"voices": {}, "ambience": []}
    for ws, (_, am) in zip(src_ws, maps):
        p = os.path.join(ws, "bank", "manifest.json")
        if not os.path.exists(p):
            continue
        m = json.load(open(p))
        for vid, lst in m["voices"].items():
            nid = am.get(int(vid), int(vid))
            for i, c in enumerate(lst):
                dst = os.path.join(out_ws, "bank", "voices", str(nid), f"ref_{len(man['voices'].get(str(nid), []))}.wav")
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if os.path.exists(c["wav"]):
                    shutil.copy(c["wav"], dst)
                man["voices"].setdefault(str(nid), []).append(dict(c, wav=dst))
        for c in m["ambience"]:
            dst = os.path.join(out_ws, "bank", "ambience", f"amb_{len(man['ambience'])}.wav")
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if os.path.exists(c["wav"]):
                shutil.copy(c["wav"], dst)
            man["ambience"].append(dict(c, wav=dst))
    os.makedirs(os.path.join(out_ws, "bank"), exist_ok=True)
    json.dump(man, open(os.path.join(out_ws, "bank", "manifest.json"), "w"), indent=1)
    return man


# ---- 3. weight level -------------------------------------------------------------------------------------------
def merge_state_dicts(dicts: Sequence[dict], weights: Sequence[float], base: Optional[dict] = None) -> dict:
    """Without base: weighted average (model soup). With base: base + sum_i w_i (theta_i - base) (task arithmetic), so weights
    need not sum to 1 and an unrelated part of the base is left untouched. Keys and shapes must match exactly."""
    w = list(weights) if base is not None else _norm(weights)
    keys = set(dicts[0])
    for d in dicts[1:]:
        if set(d) != keys:
            raise ValueError("checkpoints have different parameter names")
    if base is not None and set(base) != keys:
        raise ValueError("base has different parameter names")
    out = {}
    for k in sorted(keys):
        shapes = {tuple(getattr(d[k], "shape", ())) for d in dicts}
        if len(shapes) != 1:
            raise ValueError(f"shape mismatch for {k}: {shapes}")
        if base is None:
            out[k] = sum(wi * d[k] for wi, d in zip(w, dicts))
        else:
            out[k] = base[k] + sum(wi * (d[k] - base[k]) for wi, d in zip(w, dicts))
    return out


def load_state(path: str) -> dict:
    if path.endswith(".safetensors"):
        from safetensors.torch import load_file

        return load_file(path)
    import torch

    sd = torch.load(path, map_location="cpu", weights_only=True)
    return sd.get("model", sd) if isinstance(sd, dict) else sd


def save_state(sd: dict, path: str) -> None:
    if path.endswith(".safetensors"):
        from safetensors.torch import save_file

        save_file({k: v.contiguous() for k, v in sd.items()}, path)
    else:
        import torch

        torch.save(sd, path)


# ---- project fusion pipeline ---------------------------------------------------------------------------------------
def _w(ctx, f):
    return os.path.join(ctx["out"], f)


def _load(ws, name):
    p = os.path.join(ws, name)
    return json.load(open(p)) if os.path.exists(p) else None


def f_load(ctx, prog):
    ctx["names"] = [os.path.basename(os.path.normpath(s)) for s in ctx["srcs"]]
    ctx["profiles"] = []
    for s in ctx["srcs"]:
        p = _load(s, "profile.json")
        if not p:
            raise RuntimeError(f"{s} no tiene profile.json (ejecuta primero el aprendizaje)")
        ctx["profiles"].append(p)
    if len(set(ctx["names"])) != len(ctx["names"]):
        raise RuntimeError("los proyectos deben tener nombres de carpeta distintos")
    os.makedirs(ctx["out"], exist_ok=True)
    return f"{len(ctx['srcs'])} proyectos: " + ", ".join(f"{n} {w:.0%}" for n, w in zip(ctx["names"], _norm(ctx["weights"])))


def f_style(ctx, prog):
    prof = blend_profiles(ctx["profiles"], ctx["weights"], ctx["names"])
    plan = P.training_plan(prof, ctx.get("gpu_mem_gb", 80.0))
    ctx["blend"] = prof
    json.dump(prof, open(_w(ctx, "profile.json"), "w"), indent=1)
    json.dump(plan, open(_w(ctx, "plan.json"), "w"), indent=1)
    corpus, manifest = {}, {}
    for s, n in zip(ctx["srcs"], ctx["names"]):
        for series, seasons in (_load(s, "corpus.json") or {}).items():
            corpus[f"{n}/{series}"] = seasons
        manifest.update(_load(s, "manifest.json") or {})
    json.dump(corpus, open(_w(ctx, "corpus.json"), "w"), indent=1)
    json.dump(manifest, open(_w(ctx, "manifest.json"), "w"), indent=1)
    return f"{prof['cuts_per_min']:.0f} cortes/min · movimiento {prof['motion']:.3f} · {len(prof['palette'])} colores mezclados"


def f_mouth(ctx, prog):
    st = blend_mouth_styles([_load(s, "mouth_style.json") for s in ctx["srcs"]], ctx["weights"])
    if st is None:
        raise Skip("ningún proyecto tiene convención de boca")
    json.dump(st, open(_w(ctx, "mouth_style.json"), "w"), indent=1)
    return f"{st['fps']} fps, mantiene {st['hold_frames']} fotogramas, {len(st['levels'])} aperturas"


def f_cast(ctx, prog):
    regs = [_load(s, "registry.json") for s in ctx["srcs"]]
    if not any(regs):
        raise Skip("ningún proyecto tiene reparto aprendido")
    regs = [r for r in regs if r]
    tags = [n for n, s in zip(ctx["names"], ctx["srcs"]) if _load(s, "registry.json")]
    merged, maps = merge_registries(regs, tags)
    json.dump(merged, open(_w(ctx, "registry.json"), "w"))
    srcs = [s for s in ctx["srcs"] if _load(s, "registry.json")]
    man = merge_banks(srcs, maps, ctx["out"])
    cands = {"voice": {}, "ambience": {}, "sound": {}, "prosody": {}}
    for s in srcs:
        c = _load(s, "audio_candidates.json") or {}
        for k in cands:
            cands[k].update(c.get(k, {}))
    json.dump(cands, open(_w(ctx, "audio_candidates.json"), "w"))
    emo = {}
    for s, (_, am) in zip(srcs, maps):
        for vid, b in (_load(s, "emotion_profile.json") or {}).items():
            emo[str(am.get(int(vid), int(vid)))] = b
    json.dump(emo, open(_w(ctx, "emotion_profile.json"), "w"))
    n = len(Registry.load(_w(ctx, "registry.json")).characters())
    return f"{n} personajes · {sum(len(v) for v in man['voices'].values())} voces de referencia"


def f_recipe(ctx, prog):
    w = _norm(ctx["weights"])
    order = sorted(range(len(w)), key=lambda i: -w[i])
    a, b = order[0], order[1] if len(order) > 1 else None
    recipe = {
        "version": 1, "sources": [{"name": n, "path": os.path.abspath(s), "weight": round(wi, 4)} for n, s, wi in zip(ctx["names"], ctx["srcs"], w)],
        "mode": ctx.get("mode", "embedding") if b is not None else "text",
        "embedding_pair": None if b is None else {"primary": ctx["names"][a], "alt": ctx["names"][b], "mix": round(w[b] / (w[a] + w[b]), 4)},
        "style_prompts": {n: p.get("style_prompt") for n, p in zip(ctx["names"], ctx["profiles"])},
        "note": "El modo embedding mezcla los embeddings de texto de dos estilos; con más de dos fuentes usa las dos de mayor peso. "
                "Para que el modelo conozca ambos estilos, entrena con un token de estilo distinto por fuente en los subtítulos.",
    }
    json.dump(recipe, open(_w(ctx, "fusion.json"), "w"), indent=1, ensure_ascii=False)
    return f"modo {recipe['mode']}" + (f" · mix {recipe['embedding_pair']['mix']}" if b is not None else "")


def f_kit(ctx, prog):
    from studio import learning as L

    L.write_kit({"ws": ctx["out"], "input": " + ".join(ctx["names"]), "vids": {}}, ctx.get("_outcomes", []), final=False)
    return "episode_kit.json"


FUSION_PHASES = [
    Phase("load", "Cargar proyectos", 5, f_load, essential=True),
    Phase("style", "Fusionar estilo, ritmo y color", 25, f_style, essential=True),
    Phase("mouth", "Fusionar convención de boca", 10, f_mouth),
    Phase("cast", "Unir reparto, voces y sonido", 30, f_cast),
    Phase("recipe", "Receta de generación (embeddings)", 10, f_recipe, essential=True),
    Phase("kit", "Paquete del proyecto fusionado", 5, f_kit),
]
