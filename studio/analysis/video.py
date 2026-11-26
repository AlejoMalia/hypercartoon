"""One call that measures a video: shots and scenes, camera movement, framing and subject position, scene elements and the space they
occupy, colour, and labelled dialogue. Frames are decoded once and only the ones needed are kept (a few flow pairs and keyframes per shot).
Output: <out>/<stem>.analysis.json, .md (Spanish report), .srt (labelled dialogue), colour pictures."""
import json
import os
from collections import Counter
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np

from studio.analysis import camera as CAM
from studio.analysis import color as CL
from studio.analysis import dialogue as DLG
from studio.analysis import elements as EL
from studio.analysis import framing as FR
from studio.analysis import scenes as SC
from studio.analysis import silhouettes as SIL


def _plan_frames(shots: Sequence[Dict], fps: float, n_frames: int, pairs_per_shot: int, keyframes: int, color_samples: int):
    step = max(1, int(round(fps / 4)))                                  # flow pairs ~0.25 s apart
    need_pair, need_key, need_color = {}, {}, set()
    for i, s in enumerate(shots):
        a, b = int(s["start"] * fps), min(n_frames, int(s["end"] * fps))
        span = b - a - step
        pairs = [] if span <= 0 else sorted({a + int(x) for x in np.linspace(0, span - 1, min(pairs_per_shot, span))})
        need_pair[i] = [(p, p + step) for p in pairs]
        need_key[i] = [min(b - 1, a + int((b - a) * f)) for f in np.linspace(1 / (keyframes + 1), keyframes / (keyframes + 1), keyframes)] if b > a else []
    total_s = n_frames / fps
    for t in np.linspace(0, max(0.0, total_s - 1 / fps), color_samples):
        need_color.add(int(t * fps))
    return step, need_pair, need_key, need_color


def analyze_video(path: str, out_dir: Optional[str] = None, info=None, detector=None, prompts: Optional[Sequence[str]] = None, dialogue: str = "auto",
                  ws: Optional[str] = None, device: str = "cuda", hf_token: Optional[str] = None, pairs_per_shot: int = 6, keyframes: int = 2,
                  color_samples: int = 120, color_interval: float = 5.0, progress: Optional[Callable] = None, write: bool = True,
                  captioner=None, silhouettes_dir: Optional[str] = None) -> Dict:
    import imageio

    from studio.ingest import analyze_video as ingest_analyze

    info = info or ingest_analyze(path)
    shots = [{"start": s.start, "end": s.end, "motion": s.motion, "brightness": s.brightness, "palette": s.palette} for s in info.shots]
    fps, n_frames = info.fps, max(1, int(round(info.duration * info.fps)))
    detector = detector if detector is not None else EL.get_detector("auto", prompts, device)
    step, need_pair, need_key, need_color = _plan_frames(shots, fps, n_frames, pairs_per_shot, keyframes, color_samples)
    want = set(need_color) | {i for v in need_pair.values() for pr in v for i in pr} | {i for v in need_key.values() for i in v}
    gray, small, key_rgb = {}, {}, {}
    key_set = {i for v in need_key.values() for i in v}
    r = imageio.get_reader(path, "ffmpeg")
    last = max(want) if want else 0
    for i, f in enumerate(r):
        if i in want:
            gray[i] = CAM.to_gray_small(f)
            st = max(1, max(f.shape[:2]) // 160)
            small[i] = np.ascontiguousarray(f[::st, ::st])
            if i in key_set:
                st2 = max(1, max(f.shape[:2]) // 480)
                key_rgb[i] = np.ascontiguousarray(f[::st2, ::st2])
        if progress and i % 50 == 0:
            progress(min(0.6, 0.6 * i / max(last, 1)))
        if i >= last:
            break
    r.close()
    h_s, w_s = next(iter(gray.values())).shape if gray else (1, 1)
    res_shots, sil_shots = [], []
    for si, sh in enumerate(shots):
        cam = CAM.classify([CAM.pair_motion(gray[a], gray[b]) for a, b in need_pair[si] if a in gray and b in gray], (w_s, h_s), fps / step)
        kk = [k for k in need_key[si] if k in key_rgb]
        kfs = [detector.detect(key_rgb[k]) for k in kk]
        labelled, maps = SIL.shot_elements([key_rgb[k] for k in kk], kfs, captioner)   # silhouettes + kind + description + track per element
        comps = [FR.composition(k) for k in kfs]
        main = max(comps, key=lambda c: (c["subject"] or {"area_pct": -1})["area_pct"]) if comps else None
        framing = {"shot_type": Counter(c["shot_type"] for c in comps).most_common(1)[0][0] if comps else "sin datos",
                   "subject": main["subject"] if main else None, "subject_source": main["subject_source"] if main else "ninguno",
                   "coverage_pct": float(np.mean([c["coverage_pct"] for c in comps])) if comps else 0.0,
                   "free_space_pct": float(np.mean([c["free_space_pct"] for c in comps])) if comps else 100.0,
                   "occupancy_3x3": np.mean([c["occupancy_3x3"] for c in comps], 0).round(3).tolist() if comps else None,
                   "n_characters": max((c["n_characters"] for c in comps), default=0)}
        res_shots.append({"index": si, "start": sh["start"], "end": sh["end"], "duration": sh["end"] - sh["start"], "camera": cam, "framing": framing,
                          "elements": EL.inventory(kfs), "labelled": SIL.summarize(labelled)})
        sil_shots.append({"index": si, "times": [k / fps for k in kk], "maps": maps, "elements": res_shots[-1]["labelled"]})
    samples = sorted(((i / fps, small[i]) for i in need_color if i in small), key=lambda x: x[0])
    color = CL.analyze_colors(samples, shots, color_interval) if samples else None
    for rs, cs in zip(res_shots, (color["per_shot"] if color else [None] * len(res_shots))):
        rs["color"] = cs
    shot_pal = [{"palette": [c["rgb"] for c in (rs["color"] or {"palette": []})["palette"]], "brightness": shots[i]["brightness"]} for i, rs in enumerate(res_shots)]
    scene_of = SC.group_scenes(shot_pal)
    for rs, sc in zip(res_shots, scene_of):
        rs["scene"] = sc
    dia, items = {"backend": "off", "segments": []}, []
    if dialogue != "off":
        dia = DLG.get_transcript(path, ws, dialogue, device, hf_token=hf_token)
        if dia["segments"]:
            if any(not s.get("speaker") for s in dia["segments"]):
                from studio.audio import SR, load_audio

                DLG.assign_speakers(dia["segments"], load_audio(path, SR), SR)
            items = DLG.label_dialogue(dia["segments"], shots, scene_of)
    scenes = []
    by = DLG.by_scene(items)
    for sc in sorted(set(scene_of)):
        idx = [i for i, x in enumerate(scene_of) if x == sc]
        scenes.append({"index": sc, "shots": idx, "start": shots[idx[0]]["start"], "end": shots[idx[-1]]["end"],
                       "palette": CL.dominant_colors(np.concatenate([small[i].reshape(-1, 3) for i in need_color if i in small and shots[idx[0]]["start"] <= i / fps < shots[idx[-1]]["end"]] or [np.zeros((1, 3))]), 4),
                       "dialogue": by.get(sc)})
    cams = Counter(rs["camera"]["label"] for rs in res_shots)
    types = Counter(rs["framing"]["shot_type"] for rs in res_shots)
    cells = Counter(rs["framing"]["subject"]["cell"] for rs in res_shots if rs["framing"]["subject"])
    out = {"video": path, "fps": fps, "duration": info.duration, "size": [info.width, info.height], "detector": getattr(detector, "name", "custom"),
           "shots": res_shots, "scenes": scenes, "dialogue": items, "dialogue_backend": dia["backend"], "color": color,
           "summary": {"n_shots": len(res_shots), "n_scenes": len(scenes), "mean_shot_s": float(np.mean([s["duration"] for s in res_shots])),
                       "camera": dict(cams), "shot_types": dict(types), "subject_cells": dict(cells), "dialogue_lines": len(items),
                       "speakers": sorted({i["speaker"] for i in items if i["speaker"]}),
                       "color": CL.descriptor_es(color) if color else None}}
    if silhouettes_dir:
        out["silhouettes"] = SIL.save_silhouettes(os.path.join(silhouettes_dir, os.path.splitext(os.path.basename(path))[0] + ".sil"), path, sil_shots)
    if write and out_dir:
        write_outputs(out, out_dir, samples)
    progress and progress(1.0)
    return out


def write_outputs(res: Dict, out_dir: str, samples=None) -> Dict[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(res["video"]))[0]
    paths = {"json": os.path.join(out_dir, f"{stem}.analysis.json"), "md": os.path.join(out_dir, f"{stem}.md")}
    pics = CL.write_pictures(res["color"], samples, out_dir, stem + ".color") if res.get("color") and samples else {}
    slim = json.loads(json.dumps(res, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))
    for s in slim["shots"]:
        sub = s["framing"].get("subject")
        if sub:
            sub.pop("mask", None)
    json.dump(slim, open(paths["json"], "w"), ensure_ascii=False, indent=1)
    if res["dialogue"]:
        paths["srt"] = os.path.join(out_dir, f"{stem}.srt")
        open(paths["srt"], "w", encoding="utf-8").write(DLG.to_srt(res["dialogue"]))
    open(paths["md"], "w", encoding="utf-8").write(report_es(res, pics))
    return {**paths, **{f"color_{k}": v for k, v in pics.items()}}


def report_es(res: Dict, pics: Optional[Dict[str, str]] = None) -> str:
    sm = res["summary"]
    L = [f"# Análisis de {os.path.basename(res['video'])}", "",
         f"{res['size'][0]}×{res['size'][1]} · {res['duration']:.1f} s · {res['fps']:.0f} fps · detector de elementos: **{res['detector']}**", "",
         f"- Tomas: {sm['n_shots']} (duración media {sm['mean_shot_s']:.1f} s) · escenas (heurística por color): {sm['n_scenes']}",
         f"- Cámara: " + ", ".join(f"{k} {v}" for k, v in sm["camera"].items()),
         f"- Planos: " + ", ".join(f"{k} {v}" for k, v in sm["shot_types"].items()),
         f"- Posición del sujeto (tercios): " + (", ".join(f"{k} {v}" for k, v in sm["subject_cells"].items()) or "—"),
         f"- Color: {sm['color'] or '—'}", f"- Diálogo: {sm['dialogue_lines']} líneas · hablantes: {', '.join(sm['speakers']) or '—'} · transcripción: {res['dialogue_backend']}", "",
         "## Tomas", "", "| # | Escena | Inicio–fin | Plano | Cámara | Sujeto (posición, % altura) | Espacio ocupado | Elementos |", "|---|---|---|---|---|---|---|---|"]
    for s in res["shots"]:
        sub = s["framing"]["subject"]
        L.append(f"| {s['index'] + 1} | {s['scene'] + 1} | {DLG.timecode(s['start'])}–{DLG.timecode(s['end'])} | {s['framing']['shot_type']} | {s['camera']['label']} | "
                 + (f"{sub['cell']}, {sub['height_pct']:.0f}%" if sub else "—") + f" | {s['framing']['coverage_pct']:.0f}% (libre {s['framing']['free_space_pct']:.0f}%) | "
                 + (", ".join(f"{e['label']} {e['area_pct']:.0f}%" for e in s["elements"][:4]) or "—") + " |")
    if res["color"]:
        c = res["color"]
        L += ["", "## Color", "", f"Paleta global: " + ", ".join(f"`{p['hex']}` {p['pct']:.0f}%" for p in c["palette"][:6]),
              f"Ritmo de color: {c['rhythm']['label']} (cambio medio {c['rhythm']['mean_change']:.2f}). Cálido {c['metrics']['warm_pct']:.0f}% · frío {c['metrics']['cool_pct']:.0f}% · "
              f"saturación {c['metrics']['saturation']:.2f} · contraste {c['metrics']['contrast']:.2f}.", "",
              "| Banda de luminancia | % de píxeles | Paleta |", "|---|---|---|"]
        L += [f"| {k} | {v['pixel_pct']:.0f}% | " + ", ".join(f"`{p['hex']}`" for p in v["palette"]) + " |" for k, v in c["bands"].items()]
        if pics:
            L += ["", "Imágenes: " + ", ".join(f"[{k}]({os.path.basename(v)})" for k, v in pics.items())]
    if res["dialogue"]:
        L += ["", "## Diálogo", "", "| Tiempo | Escena | Toma | Hablante | Texto |", "|---|---|---|---|---|"]
        L += [f"| {d['timecode']} | {d['scene'] + 1} | {d['shot'] + 1} | {d['speaker'] or '?'} | {d['text']} |" for d in res["dialogue"][:200]]
    L += ["", "*Las etiquetas de plano y escena son heurísticas (altura del sujeto, color); el movimiento de cámara se estima por flujo; sin detector entrenado los elementos no tienen nombre.*"]
    return "\n".join(L) + "\n"
