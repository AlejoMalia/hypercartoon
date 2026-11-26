"""Timing catalog: how long each phase takes per minute of material, measured on synthetic shows of several sizes and fitted
as  seconds = fixed + per_minute * content_minutes  (least squares). Run it on YOUR machine: `python -m studio bench`.

Measured here: the CPU phases of learning (scan, corpus, profile, voices/sound, banks, mouth, dataset) and of episode creation
(story, emotion, plan, voices, mix). NOT measured: anything that needs a GPU or optional packages (vision, captioning with a
VLM, transcription, video generation, training) -> those rows are formulas you calibrate with `--sec-per-step-segment`."""
import io
import json
import os
import platform
import shutil
import tempfile
import time
from typing import Dict, List, Optional

import numpy as np

from studio import episode as EP
from studio import learning as L
from studio import pipeline as PL
from studio import requirements as RQ
from studio import tui


class Timer(PL.Reporter):
    def __init__(self):
        self.t = {}

    def phase_end(self, i, out):
        self.t[out.key] = (out.seconds, out.status)


def make_show(dst: str, total_seconds: float, n_videos: int = 3, fps: int = 16, with_audio: bool = True, size=(320, 180)) -> str:
    """Synthetic show: coloured shots, a moving square, and a spoken-like track (guide voice + silences + a noise bed)."""
    import imageio

    from studio.audio import _ffmpeg
    from studio.sound.mix import write_wav
    from studio.sound.speak import ScratchVoice
    import subprocess

    rng = np.random.default_rng(0)
    voice = ScratchVoice()
    phrase = voice.say("hola soy el zorro y vengo del bosque oscuro").astype(np.float32)
    per = max(4.0, total_seconds / n_videos)
    for e in range(n_videos):
        d = os.path.join(dst, "Show", f"S0{1 + e // 4}")
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f"E{e + 1:02d}.mp4")
        w = imageio.get_writer(path, fps=fps, macro_block_size=1)
        for t in range(int(per * fps)):
            k = t // (fps * 2)
            W, H = size
            f = np.zeros((H, W, 3), np.uint8)
            f[:, :, k % 3] = 60 + 40 * (k % 4)
            f[H // 5 : H // 3, (t * (1 + k % 2)) % (W * 3 // 4) : (t * (1 + k % 2)) % (W * 3 // 4) + W // 8] = 255
            w.append_data(f)
        w.close()
        if with_audio:
            sr, parts, n = voice.sr, [], 0
            while n < per * sr:
                seg = np.concatenate([phrase, np.zeros(sr // 3, np.float32)]) if rng.random() < 0.7 else (rng.normal(size=sr) * 0.02).astype(np.float32)
                parts.append(seg)
                n += len(seg)
            wav = os.path.join(d, "a.wav")
            write_wav(wav, np.concatenate(parts)[: int(per * sr)], sr)
            tmp = path + ".tmp.mp4"
            subprocess.run([_ffmpeg(), "-v", "error", "-y", "-i", path, "-i", wav, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-shortest", tmp], check=True)
            os.replace(tmp, path)
            os.remove(wav)
    return os.path.join(dst, "Show")


def fit(xs: List[float], ys: List[float]) -> Dict:
    """seconds = fixed + per_unit * x, per_unit and fixed clamped at >= 0; r2 reported."""
    x, y = np.array(xs, float), np.array(ys, float)
    if len(x) < 2 or np.ptp(x) == 0:
        return {"fixed_s": float(y.mean()) if len(y) else 0.0, "per_unit_s": 0.0, "r2": 0.0}
    b, a = np.polyfit(x, y, 1)
    b = max(float(b), 0.0)
    a = max(float(y.mean() - b * x.mean()), 0.0)
    pred = a + b * x
    ss = float(((y - y.mean()) ** 2).sum())
    return {"fixed_s": a, "per_unit_s": b, "r2": float(1 - ((y - pred) ** 2).sum() / ss) if ss > 0 else 1.0}


def bench_learning(sizes_s: List[float], work: Optional[str] = None, keep: bool = False, size=(320, 180)) -> Dict:
    work = work or tempfile.mkdtemp(prefix="hc_bench_")
    rows = {}
    for sz in sizes_s:
        root = os.path.join(work, f"size_{int(sz)}")
        shutil.rmtree(root, ignore_errors=True)
        show = make_show(root, sz, size=size)
        tm = Timer()
        ctx = {"input": show, "ws": os.path.join(root, "ws"), "device": "cpu", "workers": 1, "vision": False, "voice": "logmel", "gpu_mem_gb": 80.0}
        os.makedirs(ctx["ws"], exist_ok=True)
        t0 = time.time()
        PL.run(L.LEARNING_PHASES, ctx, tm)
        rows[sz] = {"phases": tm.t, "total": time.time() - t0, "content_min": sum(v.duration for v in ctx.get("vids", {}).values()) / 60}
        rows[sz]["requirements"] = RQ.run(ctx["ws"], write=False)["summary"]
    phases = {}
    for key in {k for r in rows.values() for k in r["phases"]}:
        pts = [(r["content_min"], r["phases"][key][0]) for r in rows.values() if key in r["phases"] and r["phases"][key][1] in ("ok", "partial")]
        st = {r["phases"][key][1] for r in rows.values() if key in r["phases"]}
        phases[key] = dict(fit([p[0] for p in pts], [p[1] for p in pts]), measured=bool(pts), status=sorted(st))
    if not keep and not work.startswith("/Users"):
        shutil.rmtree(work, ignore_errors=True)
    return {"resolution": list(size), "sizes_s": sizes_s, "rows": {str(k): v for k, v in rows.items()}, "phases": phases}


def bench_creation(line_counts: List[int]) -> Dict:
    """Episode creation timed on a throw-away project, vs number of dialogue lines."""
    work = tempfile.mkdtemp(prefix="hc_bench_ep_")
    show = make_show(work, 24, 2)
    ws = os.path.join(work, "ws")
    os.makedirs(ws)
    L_ctx = {"input": show, "ws": ws, "device": "cpu", "workers": 1, "vision": False, "voice": "logmel", "gpu_mem_gb": 80.0}
    PL.run(L.LEARNING_PHASES, L_ctx, PL.Reporter())
    rows = {}
    for n in line_counts:
        script = "INT. SALA - DIA\n\n" + "\n\n".join(f"{'ZORRO' if i % 2 else 'BUHO'}\nEsta es la línea número {i}, con algunas palabras más.\n" for i in range(n))
        tm = Timer()
        ctx = EP.make_ctx(ws, os.path.join(ws, "episodes", f"e{n}"), script, emotion="auto", story="auto", speaker="scratch")
        PL.run(EP.EPISODE_PHASES, ctx, tm)
        rows[n] = tm.t
    phases = {}
    for key in {k for r in rows.values() for k in r}:
        pts = [(n, r[key][0]) for n, r in rows.items() if key in r and r[key][1] in ("ok", "partial")]
        phases[key] = dict(fit([p[0] for p in pts], [p[1] for p in pts]), measured=bool(pts))
    shutil.rmtree(work, ignore_errors=True)
    return {"line_counts": line_counts, "phases": phases}


def bench_finish(formats=("hd", "fhd"), secs: int = 4, size=(480, 320)) -> Dict:
    """CPU finishing path (ffmpeg Lanczos + unsharp) timed per second of video. The AI path needs a GPU and is not measured."""
    from studio import finish as FN

    work = tempfile.mkdtemp(prefix="hc_bench_fin_")
    show = make_show(work, secs, 1, size=size)
    src = [os.path.join(dp, f) for dp, _, fs in os.walk(show) for f in fs if f.endswith(".mp4")][0]
    rows = {}
    for f in formats:
        t0 = time.time()
        FN.finish_video(src, os.path.join(work, f"o_{f}.mp4"), f, use_ai=False)
        rows[f] = {"seconds_per_video_second": (time.time() - t0) / secs, "source": f"{size[0]}x{size[1]}"}
    shutil.rmtree(work, ignore_errors=True)
    return rows


def generation_table(sec_per_step_segment: Optional[float] = None, steps=(25, 35, 50), minutes=(1, 5, 22)) -> List[dict]:
    """Video generation cost of an output of `minutes` at each step count, in step-segments (steps x 3 s segments) and, if you give a
    measured seconds per step-segment, in GPU seconds. Nothing here is measured."""
    rows = []
    for m in minutes:
        for st in steps:
            seg = m * 60 / 3
            ss = seg * st
            rows.append({"output_min": m, "steps": st, "step_segments": ss, "gpu_seconds": ss * sec_per_step_segment if sec_per_step_segment else None})
    return rows


def project(cat: Dict, content_minutes: List[float]) -> Dict:
    return {str(m): {k: v["fixed_s"] + v["per_unit_s"] * m for k, v in cat["phases"].items()} for m in content_minutes}


def catalog_es(learn: Dict, create: Dict, sec_per_step_segment: Optional[float] = None, finish: Optional[Dict] = None) -> str:
    titles = {p.key: p.title for p in L.LEARNING_PHASES}
    etitles = {p.key: p.title for p in EP.EPISODE_PHASES}
    proj = project(learn, [10, 60, 420])
    fmt = lambda s: f"{s / 60:.1f} min" if s >= 90 else f"{s:.1f} s"
    out = ["# Catálogo de tiempos", "",
           f"Máquina: {platform.platform()} · {os.cpu_count()} CPU · Python {platform.python_version()}. Medido con material sintético "
           f"({', '.join(f'{s:.0f} s' for s in learn['sizes_s'])} de contenido, fotogramas de {learn['resolution'][0]}x{learn['resolution'][1]}; "
           "el vídeo real, p. ej. 720x480 o mayor, se decodifica más despacio: «Escaneo» y «Personajes, objetos y voces» crecen aprox. con los píxeles) y ajustado como *fijo + por minuto de contenido*. "
           "Extrapolar fuera de este rango es una estimación; mide en tu máquina con `python -m studio bench`.", "",
           "## Aprendizaje (CPU)", "", "| Fase | Fijo | Por minuto de material | 10 min | 1 h | 7 h | Medida |", "|---|---|---|---|---|---|---|"]
    order = [p.key for p in L.LEARNING_PHASES]
    for k, v in sorted(learn["phases"].items(), key=lambda kv: order.index(kv[0]) if kv[0] in order else 99):
        out.append(f"| {titles.get(k, k)} | {v['fixed_s']:.2f} s | {v['per_unit_s']:.2f} s | {fmt(proj['10'][k])} | {fmt(proj['60'][k])} | {fmt(proj['420'][k])} | "
                   f"{'sí' if v['measured'] else 'no (' + ', '.join(v['status']) + ')'} |")
    tot = {m: sum(proj[m].values()) for m in proj}
    out += ["", f"**Total CPU estimado**: 10 min → {fmt(tot['10'])} · 1 h → {fmt(tot['60'])} · 7 h → {fmt(tot['420'])}.",
            "No incluye visión (YOLO/DINOv2), transcripción, subtítulos con VLM ni entrenamiento: necesitan GPU y no se midieron.", "",
            "## Creación de un episodio (CPU), por número de líneas de diálogo", "", "| Fase | Fijo | Por línea |", "|---|---|---|"]
    eorder = [p.key for p in EP.EPISODE_PHASES]
    for k, v in sorted(create["phases"].items(), key=lambda kv: eorder.index(kv[0]) if kv[0] in eorder else 99):
        out.append(f"| {etitles.get(k, k)} | {v['fixed_s']:.2f} s | {v['per_unit_s']:.3f} s |")
    if finish:
        out += ["", "## Afinado y escalado (CPU: ffmpeg Lanczos + unsharp), por segundo de vídeo", "", "| Formato | Segundos por segundo de vídeo |", "|---|---|"]
        out += [f"| {k} (desde {v['source']}) | {v['seconds_per_video_second']:.2f} s |" for k, v in finish.items()]
        out += ["", "La super-resolución con Real-ESRGAN necesita GPU y no se midió: su coste crece con los píxeles *de entrada* de cada fotograma "
                "(`studio.finish.estimate`, calibra con segundos por megapíxel medidos)."]
    out += ["", "## Generación de vídeo (GPU, sin medir)", "", "| Salida | Pasos | Pasos×segmento | GPU |", "|---|---|---|---|"]
    for r in generation_table(sec_per_step_segment):
        out.append(f"| {r['output_min']} min | {r['steps']} | {r['step_segments']:.0f} | {fmt(r['gpu_seconds']) if r['gpu_seconds'] else 'calibra con --sec-per-step-segment'} |")
    out += ["", "Referencia: el entrenamiento original (≈7 h de material, currículo de 3 a 63 s) tardó el equivalente a 50 h en 256 H100 "
            "según su paper (arXiv 2504.05298)."]
    return "\n".join(out) + "\n"


def run_bench(sizes_s=(16, 32, 64), lines=(2, 6, 12), out: Optional[str] = None, sec_per_step_segment: Optional[float] = None, size=(320, 180)) -> Dict:
    learn, create = bench_learning(list(sizes_s), size=size), bench_creation(list(lines))
    res = {"learning": learn, "creation": create, "finish_cpu": bench_finish(), "generation": generation_table(sec_per_step_segment), "machine": platform.platform(),
           "cpus": os.cpu_count()}
    if out:
        os.makedirs(out, exist_ok=True)
        json.dump(res, open(os.path.join(out, "timings.json"), "w"), indent=1, default=str)
        open(os.path.join(out, "TIEMPOS.md"), "w", encoding="utf-8").write(catalog_es(learn, create, sec_per_step_segment, res["finish_cpu"]))
    return res
