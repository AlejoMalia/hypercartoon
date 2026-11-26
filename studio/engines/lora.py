"""Teach a third-party engine your show: export what the studio learned as a LoRA training set in the layout used by the diffusers /
finetrainers LoRA trainers (`prompt.txt` + `videos.txt` + `videos/`, one caption per line, matched by line number).
These engines have no loss mask, so the overlay blocking is done in the data: static logos are removed with ffmpeg's delogo, clips with
title cards are never cut, and windows where more than 10 % of the picture is subtitle / logo are left out. Captions are sanitised and
start with the project's style token. Training itself is not run here: see the printed README for the trainer."""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

import numpy as np

from studio import overlays as OV
from studio.engines.registry import EngineSpec

SEG = 3.0


def export_dataset(ws: str, out_dir: str, spec: EngineSpec, window: Optional[float] = None, max_masked: float = 0.10, stage: Optional[int] = None) -> Dict:
    from studio.ingest import load_manifest

    vids = load_manifest(os.path.join(ws, "manifest.json"))
    ds = os.path.join(ws, "dataset")
    texts = json.load(open(os.path.join(ds, "text_input.json")))
    stages = sorted(int(f[len("clips_"):-len("s.json")]) for f in os.listdir(ds) if f.startswith("clips_") and f.endswith("s.json"))
    if not stages:
        raise FileNotFoundError("no hay dataset: ejecuta `studio dataset` (o el aprendizaje completo) primero")
    clips = json.load(open(os.path.join(ds, f"clips_{stage or stages[0]}s.json")))
    reports = OV.load_reports(ws)
    win = window or max(SEG, (spec.max_seconds // SEG) * SEG)
    os.makedirs(os.path.join(out_dir, "videos"), exist_ok=True)
    prompts, files, cuts, skipped = [], [], [], 0
    for c in clips:
        rep = reports.get(c["video"])
        v = vids[c["video"]]
        vf = OV.ffmpeg_filter(rep, "delogo", (v.width, v.height)) if rep else ""
        w_ = min(win, (c["dur"] // SEG) * SEG)  # never longer than the training clip it is cut from
        for k in range(int(c["dur"] // w_)):
            start = c["start"] + k * w_
            if rep and OV.overlaps_excluded(rep, start, w_):
                skipped += 1
                continue
            if rep and float(1.0 - OV.clip_loss_mask(rep, (v.width, v.height), start, w_, mode="delogo").mean()) > max_masked:
                skipped += 1
                continue
            first = int((start - c["start"]) // SEG)
            key = f"{c['name']}_c{first}"
            if key not in texts:
                continue
            name = f"{c['name']}_w{k}"
            prompts.append(OV.sanitize_caption(texts[key]["text"]).replace("\n", " "))
            files.append(f"videos/{name}.mp4")
            w, h = spec.size
            cuts.append(f'ffmpeg -loglevel error -y -ss {start} -t {w_} -i "{c["video"]}" -frames:v {spec.frames_for(w_)} -r {spec.fps} '
                        f'-vf "{vf + "," if vf else ""}scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}" -an "{os.path.join(out_dir, "videos", name + ".mp4")}"')
    open(os.path.join(out_dir, "prompt.txt"), "w", encoding="utf-8").write("\n".join(prompts) + "\n")
    open(os.path.join(out_dir, "videos.txt"), "w", encoding="utf-8").write("\n".join(files) + "\n")
    open(os.path.join(out_dir, "make_videos.sh"), "w").write("#!/bin/bash\nset -e\n" + "\n".join(cuts) + "\n")
    open(os.path.join(out_dir, "LEEME.md"), "w", encoding="utf-8").write(readme_es(spec, len(files), win, skipped))
    return {"samples": len(files), "window_s": win, "skipped_for_overlays": skipped, "out_dir": out_dir}


def readme_es(spec: EngineSpec, n: int, win: float, skipped: int) -> str:
    return "\n".join([f"# LoRA de estilo para {spec.title}", "",
                      f"{n} muestras de {win:.0f} s a {spec.size[0]}x{spec.size[1]} · {spec.fps} fps ({skipped} ventanas descartadas por rótulos/logos).", "",
                      "1. Cortar los vídeos (ffmpeg, CPU): `bash make_videos.sh`", "2. `prompt.txt` y `videos.txt` están en el formato de los entrenadores de LoRA de "
                      "diffusers / finetrainers: una línea por muestra, emparejadas por número de línea.",
                      "3. Entrenar con el entrenador de tu motor (consulta su documentación actual para las opciones exactas; este repositorio no lo ejecuta): "
                      "https://github.com/huggingface/finetrainers", f"4. Generar con el LoRA: `studio render --engine {spec.id} --lora RUTA_DEL_LORA`.", "",
                      "Estos motores no tienen máscara de pérdida: los logos fijos se quitaron con `delogo` y las ventanas con mucho texto se descartaron.",
                      "Comprueba la licencia del modelo base antes de entrenar y publicar resultados."]) + "\n"
