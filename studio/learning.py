"""Learning pipeline: material -> everything needed to generate an episode, in phases with progress.
Output is a project folder (the 'kit'): manifest, corpus, profile, plan, registry, sound bank, mouth style, story map and
`episode_kit.json` (index of it all) + `LEEME.md`."""
import json
import os
import time
from datetime import datetime
from typing import Dict, List

from studio import corpus as C
from studio import profile as P
from studio import layers as LY
from studio import overlays as OV
from studio import sources as S
from studio.absorb import absorb_corpus, default_backends
from studio.characters import Registry
from studio.ingest import ingest_paths, list_videos
from studio.pipeline import Outcome, Phase, Skip


def _p(ctx, f):
    return os.path.join(ctx["ws"], f)


def merge_candidates(ws: str, ab) -> None:
    """Episodes absorbed in earlier runs keep their candidates; only new episodes are added."""
    path = os.path.join(ws, "audio_candidates.json")
    if os.path.exists(path):
        old = json.load(open(path))
        for k, dst in (("voice", ab.voice_cands), ("ambience", ab.ambience), ("sound", ab.sound), ("prosody", ab.prosody)):
            for ep, v in old.get(k, {}).items():
                dst.setdefault(ep, v)
    ab.save(ws)


# ---- phases -------------------------------------------------------------------------------------------------
def ph_sources(ctx, prog):
    """Any input (local, URL, YouTube, playlist, list file, open directory, feed, cloud link, live stream, torrent) -> local files."""
    inputs = ctx.get("inputs") or [ctx["input"]]
    ctx["inputs"] = inputs
    opts = ctx.get("source_options") or S.Options()
    pr = S.prepare(inputs, ctx["ws"], opts, progress=lambda f, d="": prog(f, d))
    ctx["paths"], ctx["root"], ctx["source_records"] = pr.paths, pr.root, pr.records
    if pr.errors:
        ctx["source_errors"] = pr.errors
    if not pr.remote:
        return "material local, sin copiar"
    note = f"{len(pr.paths)} vídeo(s) en {opts.keep} ({opts.proxy_height} p)" if opts.keep == "proxy" else f"{len(pr.paths)} vídeo(s) originales"
    if pr.errors:
        return "parcial: " + note + f"; {len(pr.errors)} fallaron: " + "; ".join(pr.errors[:2])
    return note


def ph_scan(ctx, prog):
    paths = ctx.get("paths") or list_videos(ctx["input"])
    if not paths:
        raise RuntimeError("no se encontró ningún vídeo (mp4, mov, mkv, webm, avi, m4v ...)")
    ctx.setdefault("root", ctx["input"] if os.path.isdir(ctx["input"]) else os.path.dirname(os.path.abspath(ctx["input"])))
    ctx["vids"] = ingest_paths(paths, _p(ctx, "manifest.json"), workers=ctx.get("workers", 1),
                               progress=lambda d, t, p: prog(d / max(t, 1), os.path.basename(p)))
    return f"{len(paths)} vídeo(s), {sum(v.duration for v in ctx['vids'].values()) / 60:.1f} min"


def ph_corpus(ctx, prog):
    ctx["corpus"] = C.build_corpus(ctx["vids"], ctx["root"])
    json.dump(ctx["corpus"], open(_p(ctx, "corpus.json"), "w"), indent=1)
    n = sum(len(e) for s in ctx["corpus"].values() for e in s.values())
    return f"{sum(len(s) for s in ctx['corpus'].values())} temporada(s), {n} episodio(s)"


def ph_profile(ctx, prog):
    vids, corpus = ctx["vids"], ctx["corpus"]
    prof = P.build_profile(vids)
    prof["style_prompt"] = P.style_prompt(prof)
    prof["chapter_seconds"] = P.chapter_seconds(prof)
    prof["seasons"] = P.season_profiles(corpus, vids)
    prog(0.4)
    plan = P.training_plan(prof, ctx.get("gpu_mem_gb", 80.0))
    cuts = P.segment_cuts(vids)
    json.dump(prof, open(_p(ctx, "profile.json"), "w"), indent=1)
    json.dump(plan, open(_p(ctx, "plan.json"), "w"), indent=1)
    open(_p(ctx, "make_segments.sh"), "w").write(P.ffmpeg_script(cuts, _p(ctx, "segments")))
    ctx["prof"], ctx["plan"] = prof, plan
    return f"{prof['cuts_per_min']:.0f} cortes/min · etapas {[s['seconds'] for s in plan['stages']]} s"


def _cinematography(summaries):
    """Aggregate per-episode summaries into the show's visual grammar (distributions in %)."""
    from collections import Counter

    def dist(key):
        c = Counter()
        for s in summaries:
            c.update(s.get(key, {}))
        tot = sum(c.values()) or 1
        return {k: round(100.0 * v / tot, 1) for k, v in c.most_common()}

    return {"shot_types": dist("shot_types"), "camera": dist("camera"), "subject_cells": dist("subject_cells"),
            "mean_shot_s": sum(s["mean_shot_s"] for s in summaries) / len(summaries)}


EN_SHOT = {"primer plano": "close-up shots", "plano medio": "medium shots", "plano completo": "full shots", "plano general": "wide shots",
           "plano de ambiente (sin personaje)": "establishing shots"}
EN_CAM = {"fija": "static camera", "paneo derecha": "camera panning", "paneo izquierda": "camera panning", "zoom/dolly in": "slow zoom in",
          "zoom/dolly out": "slow zoom out", "tilt arriba": "camera tilting", "tilt abajo": "camera tilting"}


def cinematography_prompt(c) -> str:
    top = lambda d, m: next((m.get(k, k) for k in d if k in m), None)
    shots, cam = top(c["shot_types"], EN_SHOT), top(c["camera"], EN_CAM)
    return ", ".join(x for x in (f"mostly {shots}" if shots else None, cam) if x)


def ph_overlays(ctx, prog):
    """Burned-in subtitles, title cards / credits, logos and watermarks, letterbox bars: found per video and kept out of the learning
    (loss mask, no clips from title cards, captions never mention text). Incremental, one small JSON per video (docs/overlays.md)."""
    if ctx.get("overlay_mode", "mask") == "off":
        raise Skip("desactivado (overlay_mode=off)")
    vids = ctx["vids"]
    idx_path = os.path.join(ctx["ws"], "overlays", "index.json")
    index = json.load(open(idx_path)) if os.path.exists(idx_path) else {}
    det = None
    if ctx.get("text_detector"):
        det = OV.ocr_detector(ctx["text_detector"])
    found = []
    for n, (p, v) in enumerate(vids.items()):
        rel = os.path.relpath(OV.report_path(ctx["ws"], p), ctx["ws"])
        cached = os.path.join(ctx["ws"], rel)
        old = json.load(open(cached)) if p in index and os.path.exists(cached) else {}
        if old.get("size_bytes") == v.size and old.get("detector") == (ctx.get("text_detector") or "text_lines") and old.get("version") == OV.VERSION:
            rep = old
        else:
            rep = OV.scan_video(p, detector=det, progress=lambda f, n=n: prog((n + f) / max(len(vids), 1), os.path.basename(p)))
            rep["size_bytes"] = v.size
            rep["detector"] = ctx.get("text_detector") or "text_lines"
            OV.save_report(ctx["ws"], p, rep)
        index[p] = rel
        found.append(rep)
        prog((n + 1) / max(len(vids), 1), os.path.basename(p))
    json.dump(index, open(idx_path, "w"), indent=1)
    ctx["overlays"] = found
    bad = [r for r in found if not OV.clean(r)]
    if not bad:
        return "ningún texto ni logo incrustado"
    return f"{len(bad)}/{len(found)} vídeo(s) con elementos incrustados · " + "; ".join(dict.fromkeys(OV.describe_es(r) for r in bad[:2]))


def ph_analysis(ctx, prog):
    """Shots, scenes, camera movement, framing, elements and space, colour and dialogue for every episode (docs/analysis.md)."""
    from studio.analysis import video as AV
    from studio.analysis import elements as EL
    from studio.analysis.color import descriptor_es

    out_dir = _p(ctx, "analysis")
    os.makedirs(out_dir, exist_ok=True)
    eps = C.flat_order(ctx["corpus"])
    det = EL.get_detector(ctx.get("detector", "auto"), ctx.get("prompts"), ctx.get("device", "cuda"))
    from studio.analysis import silhouettes as SIL

    cap = SIL.get_captioner(ctx.get("element_captioner", "measured"), ctx.get("device", "cuda"))
    index, sums, cols = {}, [], []
    for n, e in enumerate(eps):
        res = AV.analyze_video(e["path"], out_dir, info=ctx["vids"].get(e["path"]), detector=det, dialogue=ctx.get("dialogue", "auto"), ws=ctx["ws"],
                               device=ctx.get("device", "cuda"), captioner=cap, silhouettes_dir=_p(ctx, "silhouettes"),
                               progress=lambda f, n=n: prog((n + f) / max(len(eps), 1), os.path.basename(e["path"])))
        stem = os.path.splitext(os.path.basename(e["path"]))[0]
        index[e["path"]] = os.path.join("analysis", f"{stem}.analysis.json")
        sums.append(res["summary"])
        if res.get("color"):
            cols.append(res["color"]["metrics"])
    json.dump(index, open(_p(ctx, "analysis/index.json"), "w"), indent=1)
    cin = _cinematography(sums)
    prof = _load(ctx["ws"], "profile.json") or {}
    if cols:
        cin["color"] = {k: sum(c[k] for c in cols) / len(cols) for k in cols[0]}
    cin["prompt"] = cinematography_prompt(cin)
    prof["cinematography"] = cin
    base = prof.get("style_prompt", "").split(", mostly ")[0]
    prof["style_prompt"] = base + (", " + cin["prompt"] if cin["prompt"] else "")
    json.dump(prof, open(_p(ctx, "profile.json"), "w"), indent=1)
    ctx["prof"] = prof
    note = f"{len(eps)} episodio(s) · detector {det.name} · " + (cin["prompt"] or "sin datos de plano")
    return note if det.name != "blobs" else "parcial: " + note + " · elementos sin nombre (instala ultralytics o usa prompts con Grounding DINO)"


def ph_layers(ctx, prog):
    """Knowledge by kind, not in one container: characters, backgrounds, palettes, scene types and rhythm — per series and for the whole
    studio — plus the studio style a creation run can use (`create --style-layers _studio`). docs/layers.md."""
    try:
        r = LY.build(ctx["ws"], progress=lambda f: prog(f))
    except FileNotFoundError as e:
        raise Skip(str(e))
    sp = r["spread"]
    more = f" · distancia de paleta entre series {sp['palette_distance_mean']:.2f}" if sp["series"] > 1 else ""
    ctx["layers"] = r
    return f"{len(r['series'])} serie(s) en 5 capas + estilo del estudio{more}"


def ph_characters(ctx, prog):
    reg = Registry.load(_p(ctx, "registry.json"))
    tracker, embedder, speech, ab, notes = default_backends(ctx.get("device", "cuda"), ctx.get("voice", "auto"), ctx.get("vision", True))
    st = absorb_corpus(C.flat_order(ctx["corpus"]), reg, tracker, embedder, speech,
                       on_episode=lambda e, r: r.save(_p(ctx, "registry.json")),
                       progress=lambda d, t, p: prog(d / max(t, 1), os.path.basename(p)))
    reg.save(_p(ctx, "registry.json"))
    merge_candidates(ctx["ws"], ab)
    ctx["reg"] = reg
    msg = f"{st['new']} episodio(s) nuevos, {st['skipped']} ya conocidos · {len(reg.characters())} personaje(s)"
    return ("parcial: " + msg + " · " + "; ".join(notes)) if notes else msg


def ph_soundbank(ctx, prog):
    from studio.emotion.profile import build_emotion_profile
    from studio.sound.bank import build_bank

    if not os.path.exists(_p(ctx, "audio_candidates.json")):
        raise Skip("no hay candidatos de audio")
    reg = ctx.get("reg") or Registry.load(_p(ctx, "registry.json"))
    prog(0.2)
    m = build_bank(ctx["ws"], reg.voice)
    prog(0.8)
    build_emotion_profile(ctx["ws"], reg.voice)
    return f"{sum(len(v) for v in m['voices'].values())} referencias de voz, {len(m['ambience'])} ambientes"


def ph_lips(ctx, prog):
    from studio.lips.learn import learn_corpus_style

    if not os.path.exists(_p(ctx, "audio_candidates.json")):
        raise Skip("sin tramos de habla detectados")
    try:
        st = learn_corpus_style(ctx["ws"])
    except ValueError as e:
        raise Skip(str(e))
    return f"{st.fps} fps, mantiene {st.hold_frames} fotogramas, {len(st.levels)} aperturas, adelanto {st.lead_s * 1000:.0f} ms"


def ph_dataset(ctx, prog):
    from studio.dataset import build_training_set, get_captioner

    plan = _load(ctx["ws"], "plan.json")
    if not plan:
        raise Skip("sin plan de entrenamiento")
    kind = ctx.get("captioner", "heuristic")
    cap = get_captioner(kind, ctx.get("device", "cuda"))
    name = os.path.basename(os.path.normpath(ctx["ws"]))
    r = build_training_set(ctx["ws"], [s["seconds"] for s in plan["stages"]], cap, f"{name} animation style",
                           progress=lambda f, d: prog(f, d), overlay_mode=ctx.get("overlay_mode", "mask"))
    msg = f"{sum(v['clips'] for v in r['stages'].values())} clips en {len(r['stages'])} etapa(s) · token «{r['style_token']}»"
    if r["overlays"]["videos_with_reports"]:
        msg += f" · {r['overlays']['clips_dropped']} clips con rótulos/créditos descartados, {r['overlays']['clips_with_masked_area']} con zona enmascarada"
    return msg if kind != "heuristic" else "parcial: " + msg + " · subtítulos genéricos; usa captioner=qwen en GPU para descripciones reales"


def ph_sufficiency(ctx, prog):
    from studio import requirements as RQ

    r = RQ.run(ctx["ws"])
    sm = r["summary"]
    prog(1.0)
    msg = f"veredicto {sm['overall']} (limita: {sm['limiting']}) · REQUISITOS.md"
    return msg if sm["overall"] in ("bueno", "óptimo") else "parcial: " + msg


def ph_kit(ctx, prog):
    write_kit(ctx, ctx.get("_outcomes", []), final=False)
    return "episode_kit.json"


# ---- kit ----------------------------------------------------------------------------------------------------
def _load(ws, name):
    p = os.path.join(ws, name)
    return json.load(open(p)) if os.path.exists(p) else None


def write_kit(ctx: Dict, outcomes: List[Outcome], final: bool = True, seconds: float = 0.0) -> str:
    ws = ctx["ws"]
    prof, plan = _load(ws, "profile.json") or {}, _load(ws, "plan.json") or {}
    reg = Registry.load(os.path.join(ws, "registry.json"))
    mouth = _load(ws, "mouth_style.json")
    bank = _load(ws, "bank/manifest.json") or {"voices": {}, "ambience": []}
    cand = _load(ws, "audio_candidates.json") or {}
    files = {k: v for k, v in {
        "manifest": "manifest.json", "corpus": "corpus.json", "profile": "profile.json", "plan": "plan.json",
        "registry": "registry.json", "segments_script": "make_segments.sh", "sound_bank": "bank/manifest.json",
        "emotion_profile": "emotion_profile.json", "mouth_style": "mouth_style.json",
        "requirements": "requirements.json", "requirements_report": "REQUISITOS.md", "analysis_index": "analysis/index.json", "training_commands": "dataset/COMANDOS.md", "overlays_index": "overlays/index.json", "layers_index": "layers/index.json", "voice_library": "voices/index.json", "studio_style": "layers/_studio/style.json", "training_text_input": "dataset/text_input.json",
        "audio_candidates": "audio_candidates.json"}.items() if os.path.exists(os.path.join(ws, v))}
    kit = {
        "version": 1, "created": datetime.now().isoformat(timespec="seconds"), "complete": final,
        "source": {"input": ctx.get("input"), "inputs": ctx.get("inputs"), "remote": any(r.get("kind") != "local" for r in ctx.get("source_records", [])), "videos": len(ctx.get("vids", {})), "total_seconds": prof.get("total_seconds")},
        "phases": [{"key": o.key, "title": o.title, "status": o.status, "seconds": round(o.seconds, 1), "note": o.note} for o in outcomes],
        "total_seconds_run": round(seconds, 1),
        "style": {"prompt": prof.get("style_prompt"), "shot_length": prof.get("shot_len"), "cuts_per_min": prof.get("cuts_per_min"),
                  "motion": prof.get("motion"), "brightness": prof.get("brightness"), "palette": prof.get("palette"),
                  "chapter_seconds": prof.get("chapter_seconds"), "seasons": list((prof.get("seasons") or {}).keys())},
        "training_plan": plan,
        "characters": reg.characters(),
        "sound": {"voice_references": {k: len(v) for k, v in bank["voices"].items()}, "ambience_beds": len(bank["ambience"]),
                  "soundtrack_mix": {os.path.basename(k): v for k, v in (cand.get("sound") or {}).items()}},
        "mouth_style": mouth,
        "ready": {"style": bool(prof), "plan": bool(plan), "characters": bool(reg.characters()), "voices": bool(bank["voices"]),
                  "mouth_style": mouth is not None, 
                  "training_dataset": os.path.exists(os.path.join(ws, "dataset", "COMANDOS.md"))},
        "sufficiency": (_load(ws, "requirements.json") or {}).get("summary"),
        "files": files,
        "next": {"create_episode": f"python -m studio --workdir {ws} create GUION.txt",
                 "name_characters": f"python -m studio --workdir {ws} characters && python -m studio --workdir {ws} name ID NOMBRE"},
    }
    path = os.path.join(ws, "episode_kit.json")
    json.dump(kit, open(path, "w"), indent=1, ensure_ascii=False)
    done = {o.key: o for o in outcomes}
    lines = ["# Paquete de aprendizaje", "",
             f"Creado: {kit['created']} · material: `{ctx.get('input')}` · {kit['source']['videos']} vídeo(s)", "",
             "Este directorio contiene todo lo que el sistema ha aprendido y necesita para generar un episodio.", "",
             "## Fases", "", "| Fase | Estado | Tiempo | Nota |", "|---|---|---|---|"]
    lines += [f"| {o.title} | {o.status} | {o.seconds:.0f}s | {o.note} |" for o in outcomes]
    lines += ["", "## Para crear un episodio", "", f"```bash\n{kit['next']['create_episode']}\n```", "",
              "El guion puede ser un guion, texto con `NOMBRE: línea` o prosa con diálogos. Si algún personaje aparece sin aspecto "
              "aprendido, nómbralo con `name`. La generación de vídeo requiere GPU (el comando se imprime al crear el episodio)."]
    open(os.path.join(ws, "LEEME.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    return path


def finalize_kit(ctx, outcomes, seconds):
    return write_kit(ctx, outcomes, final=True, seconds=seconds)


LEARNING_PHASES = [
    Phase("sources", "Fuentes de entrada (local, enlaces, listas, torrent)", 10, ph_sources, essential=True),
    Phase("scan", "Escaneo y análisis de vídeo", 20, ph_scan, essential=True),
    Phase("corpus", "Temporadas y episodios", 2, ph_corpus, essential=True),
    Phase("profile", "Estilo, ritmo y plan de entrenamiento", 5, ph_profile, essential=True),
    Phase("overlays", "Texto, logos y rótulos incrustados (se excluyen)", 8, ph_overlays),
    Phase("analysis", "Cámara, encuadre, elementos, color y diálogo", 18, ph_analysis),
    Phase("characters", "Personajes, objetos y voces", 40, ph_characters),
    Phase("soundbank", "Banco de sonido y emoción de la voz", 8, ph_soundbank),
    Phase("layers", "Capas del estilo: personajes, fondos, paletas, escenas", 4, ph_layers),
    Phase("lips", "Convención de boca (labios)", 8, ph_lips),
    Phase("dataset", "Subtítulos y dataset de entrenamiento", 6, ph_dataset),
    Phase("sufficiency", "Suficiencia del material", 2, ph_sufficiency),
    Phase("kit", "Paquete del episodio", 5, ph_kit),
]
