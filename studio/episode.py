"""Creation pipeline: script/prompt -> episode folder (prompts, compute plan, voices, mouth tracks, mix, report) in phases.
Uses the learning kit in `ws`; writes into `out` (an episode folder, or ws itself for the legacy CLI)."""
import json
import os
from datetime import datetime

from studio import budget as B
from studio import script as S
from studio.characters import Registry
from studio.hires import stage_a_flags
from studio.pipeline import Phase, Skip


def _w(ctx, f):
    return os.path.join(ctx["out"], f)


def _ws(ctx, f):
    return os.path.join(ctx["ws"], f)


def read_story(text, chars, max_seconds, mode="auto"):
    """Script reader: vendored script-hypercartoon engines when Node is present, native otherwise; validate and auto-fix."""
    from studio.story import plan as SP

    bridge = None
    if mode != "native":
        try:
            from studio.story.script_engine import ScriptEngineBridge

            bridge = ScriptEngineBridge()
        except Exception as e:
            if mode == "script":
                raise SystemExit(f"Motores de script-hypercartoon no disponibles: {e}")
    try:
        res = SP.analyze(text, bridge)
    finally:
        if bridge:
            bridge.close()
    return res, SP.validate(res, set(chars), max_seconds)


# ---- phases ---------------------------------------------------------------------------------------------------
def c_story(ctx, prog):
    for f in ("profile.json", "plan.json"):
        if not os.path.exists(_ws(ctx, f)):
            raise RuntimeError("faltan los datos de aprendizaje; ejecuta primero el aprendizaje del material")
    ctx["prof"], ctx["plan"] = json.load(open(_ws(ctx, "profile.json"))), json.load(open(_ws(ctx, "plan.json")))
    reg = Registry.load(_ws(ctx, "registry.json"))
    ctx["chars"] = {c["name"]: c for c in reg.characters() if c["id"] in reg.names}
    ctx["cast"] = {n: f"{n.title()}, a {c['kind']} character" for n, c in ctx["chars"].items()}
    prog(0.2)
    res, issues = read_story(ctx["text"], ctx["chars"], ctx["plan"]["max_seconds"], ctx["opts"].get("story", "auto"))
    ctx["res"], ctx["issues"] = res, issues
    ctx["scenes"] = S.parse_script(res["script"], max(3.0, round(ctx["prof"]["shot_len"]["median"] / 3) * 3), known=set(ctx["chars"]))
    if len(ctx["scenes"]) == len(res["reading"]["scenes"]):
        for sc, rs in zip(ctx["scenes"], res["reading"]["scenes"]):
            sc.tension = rs.get("tension")
    return f"{len(ctx['scenes'])} escenas · lectura {res['source']} · {len(issues)} observaciones"


def c_emotion(ctx, prog):
    kind = ctx["opts"].get("emotion", "auto")
    flat = [ln for sc in ctx["scenes"] for ln in sc.lines]
    if kind == "off" or not flat:
        raise Skip("sin diálogos o desactivada")
    from studio.emotion.engine import make_bridge, measure_dialogue

    bridge, used = make_bridge(kind)
    try:
        res = measure_dialogue(flat, bridge, cast=list(ctx["chars"]))
    finally:
        bridge.close()
    i = 0
    for sc in ctx["scenes"]:
        sc.emo, i = res[i : i + len(sc.lines)], i + len(sc.lines)
    ctx["emotion_engine"] = used
    return f"{len(flat)} líneas medidas con {used}"


def _fusion(ctx):
    """Fusion recipe of the project, if it is a fused one and embedding mixing applies."""
    p = _ws(ctx, "fusion.json")
    if not os.path.exists(p):
        return None
    f = json.load(open(p))
    return f if f.get("mode") == "embedding" and f.get("embedding_pair") else None


def _write_prompts(ctx):
    """prompts.jsonl (all videos) + one prompts file per step count (sample.py takes one step count per run)."""
    videos, comp = ctx["videos"], ctx["comp"]
    S.write_jsonl(videos, _w(ctx, "prompts.jsonl"))
    for st in comp["runs"]:
        S.write_jsonl([videos[it["video"]] for it in comp["videos"] if it["steps"] == st and not it["cached"]], _w(ctx, f"prompts_s{st}.jsonl"))


def c_plan(ctx, prog):
    os.makedirs(ctx["out"], exist_ok=True)
    scenes, plan, prof, o = ctx["scenes"], ctx["plan"], ctx["prof"], ctx["opts"]
    fus = _fusion(ctx)
    style = fus["style_prompts"][fus["embedding_pair"]["primary"]] if fus else prof["style_prompt"]
    if o.get("style_layers") and not fus:  # a studio / show / composed style from the knowledge layers
        from studio import layers as LY

        style = LY.load_style(ctx["ws"], o["style_layers"])["style_prompt"]
    segs, voices = S.to_segments(scenes, style, ctx["cast"])
    if fus:  # style fusion: describe every segment in the second style too; the sampler interpolates the text embeddings
        alt, _ = S.to_segments(scenes, fus["style_prompts"][fus["embedding_pair"]["alt"]], ctx["cast"])
        for sg, al in zip(segs, alt):
            sg["alt_text"], sg["mix"] = al["text"], fus["embedding_pair"]["mix"]
    videos = S.pack_videos(segs, plan["max_seconds"])
    prompts = _w(ctx, "prompts.jsonl")
    S.write_jsonl(videos, prompts)
    prog(0.3)
    sidx, per = S.segment_scene_index(scenes), int(plan["max_seconds"] // S.SEG)
    tens = [[scenes[i].tension for i in sidx[k : k + per]] for k in range(0, len(sidx), per)]
    vt = [(sum(x for x in t if x is not None) / max(1, sum(x is not None for x in t))) if any(x is not None for x in t) else None for t in tens]
    cache = B.ShotCache(_ws(ctx, "shot_cache.json"), cfg=f"{plan['stages'][-1]['layer']}")
    comp = B.plan_compute(videos, vt, cache, o.get("compute", "adaptive"), sec_per_step_segment=o.get("sec_per_step_segment"))
    ctx.update(videos=videos, comp=comp)
    _write_prompts(ctx)
    json.dump(comp, open(_w(ctx, "compute_plan.json"), "w"), indent=1)
    from studio.story.plan import report_es

    open(_w(ctx, "story_report.md"), "w", encoding="utf-8").write(report_es(ctx["res"], ctx["issues"], comp))
    open(_w(ctx, "script.studio.txt"), "w", encoding="utf-8").write(ctx["res"]["script"])
    vmap = {n: c["voice_id"] for n, c in ctx["chars"].items()}
    from studio import voices as VX

    speakers = sorted({ln[0] for sc in ctx["scenes"] for ln in sc.lines})
    bind = VX.binding(ctx["ws"], speakers, {n.upper(): c["voice_id"] for n, c in ctx["chars"].items()})   # clone profile > voice from the episodes > guide
    vmap.update({k: v["voice_id"] for k, v in bind.items() if v["voice_id"] is not None})
    ctx["voice_binding"] = bind
    json.dump(bind, open(_w(ctx, "voice_binding.json"), "w"), ensure_ascii=False, indent=1)
    side = [[[{"character": ln[0], "voice_id": vmap.get(ln[0].upper()), "line": ln[1], **({"emotion": ln[2]} if len(ln) > 2 else {})}
              for ln in seg] for seg in v] for v in S.split_voices(voices, plan["max_seconds"])]
    json.dump(side, open(_w(ctx, "voices.json"), "w"), ensure_ascii=False, indent=1)
    stage = S.stage_for(max(len(v) for v in videos), plan["max_seconds"])
    json.dump({"stage": stage, "overrides": S.eval_overrides(stage, o.get("steps", 50)), "prompts": prompts}, open(_w(ctx, "create.json"), "w"), indent=1)
    ctx.update(segs=segs, videos=videos, comp=comp, stage=stage, side=side)
    mixed = f" · fusión {fus['embedding_pair']['primary']}/{fus['embedding_pair']['alt']} mix {fus['embedding_pair']['mix']}" if fus else ""
    return f"{len(segs)} segmentos → {len(videos)} vídeo(s) · {comp['saving_pct']:.0f}% menos pasos que todo a 50{mixed}"


def c_voices(ctx, prog):
    from studio.sound import mix as M
    from studio.sound.bank import Bank
    from studio.sound.speak import get_speaker

    o = ctx["opts"]
    bank, speaker = Bank(ctx["ws"]), get_speaker(o.get("speaker", "scratch"), o.get("device", "cuda"))
    bind = ctx.get("voice_binding", {})
    clones = [k for k, v in bind.items() if v["source"] == "clone"]
    ctx["rendered"] = []
    for vi, segs in enumerate(ctx["side"]):
        prog(vi / max(len(ctx["side"]), 1), f"vídeo {vi + 1}/{len(ctx['side'])}")
        dlg, rep = M.render_dialogue(segs, bank, speaker, 24000)
        ctx["rendered"].append((dlg, rep))
    n = sum(r["lines"] for _, r in ctx["rendered"])
    late = sum(len(r["late_lines"]) for _, r in ctx["rendered"])
    if not n:
        raise Skip("el guion no tiene diálogos")
    note = f"{n} líneas con voz {type(speaker).__name__} · {late} fuera de su segmento"
    if clones:
        note += f" · clones: {', '.join(clones)}"
    guide = [k for k, v in bind.items() if v["source"] == "guide"]
    if type(speaker).__name__ == "ScratchVoice" and clones:
        return "parcial: " + note + " · la voz guía no clona; usa --speaker auto|chatterbox|coqui|f5 para usar los clones"
    if guide and type(speaker).__name__ != "ScratchVoice":
        return "parcial: " + note + f" · sin voz clonada para {', '.join(guide)} (añádela con `studio voices add`)"
    return note


def c_mix(ctx, prog):
    from studio.sound import mix as M
    from studio.sound.bank import Bank

    if not ctx.get("rendered"):
        raise Skip("sin diálogo que mezclar")
    bank, o = Bank(ctx["ws"]), ctx["opts"]
    os.makedirs(_w(ctx, "sound"), exist_ok=True)
    for vi, (dlg, rep) in enumerate(ctx["rendered"]):
        prog(vi / len(ctx["rendered"]))
        dlg = lip_sync(ctx["ws"], ctx["out"], vi, dlg, rep, 24000, o.get("video", ""), o.get("sync", False))
        bed = M.ambience_bed(bank.ambience_wav(), len(dlg), 24000)
        M.write_wav(_w(ctx, f"sound/video_{vi:03d}.wav"), M.mix(dlg, bed, 24000), 24000)
        if o.get("video") and vi == 0:
            M.mux(o["video"], _w(ctx, f"sound/video_{vi:03d}.wav"), o["video"].rsplit(".", 1)[0] + "_sound.mp4")
    return f"{len(ctx['rendered'])} mezcla(s) + pistas de boca"


def c_control(ctx, prog):
    """Audio-side control for the video model (speech / loudness [/ emotion] per latent frame), from the regenerated voices.
    Written next to the prompts and referenced from them; ignored by a model trained without control adapters."""
    from hypercartoon.models.cogvideo import control_data as CD
    from studio.control import video_control

    if not ctx.get("rendered") or not ctx["opts"].get("control", True):
        raise Skip("sin voces regeneradas o desactivado")
    emotion = bool(ctx["opts"].get("control_emotion", False))
    os.makedirs(_w(ctx, "control"), exist_ok=True)
    n = 0
    for vi, (dlg, rep) in enumerate(ctx["rendered"]):
        lines = [ln for seg in ctx["side"][vi] for ln in seg]
        ff = video_control(rep["clips"], 24000, len(ctx["videos"][vi]), [ln.get("emotion", {}) for ln in lines], emotion)
        path = _w(ctx, f"control/video_{vi:03d}.npz")
        CD.save_control(path, frame_feats=ff)
        ctx["videos"][vi][0]["control"] = os.path.abspath(path)
        n += 1
    _write_prompts(ctx)
    return f"{n} archivo(s) de control (habla/volumen{'/emoción' if emotion else ''}) · activa con model.control_frame_dim=4 si lo entrenaste"


def c_package(ctx, prog):
    comp, plan = ctx["comp"], ctx["plan"]
    cfg = plan["stages"][-1]["layer"].replace("_", "-").replace("ttt", "hyper")
    cmds = [f"torchrun sample.py --job.config_file configs/eval/{cfg}/{ctx['stage']}s.toml --eval.input_file {_w(ctx, f'prompts_s{st}.jsonl')} "
            f"--eval.num_denoising_steps={st} --guider.num_steps={st}"
            + (" " + " ".join(stage_a_flags(ctx["opts"]["enhance_weight"])) if ctx["opts"].get("enhance_weight") else "") for st in comp["runs"]]
    ep = {"created": datetime.now().isoformat(timespec="seconds"), "scenes": len(ctx["scenes"]), "segments": len(ctx["segs"]),
          "videos": len(ctx["videos"]), "stage_seconds": ctx["stage"], "story_source": ctx["res"]["source"],
          "emotion_engine": ctx.get("emotion_engine"), "compute": {k: comp[k] for k in ("strategy", "baseline", "expected", "saving_pct")},
          "issues": [i["msg"] for i in ctx["issues"]],
          "files": sorted(f for f in os.listdir(ctx["out"])), "generate_video_commands": cmds,
          "stage_b": {"note": "alta resolución en dos etapas (docs/hires.md): la etapa A es la generación de arriba; la B refina por piezas",
                      "esrgan": "python -m studio hires <video.mp4> --refiner esrgan --mode full_overlap",
                      "generative": "python -m studio hires <video.mp4> --refiner generative --mode seam_aware --dry   # imprime el comando de refine_video.py (GPU)"},
          "finish": {"example": "python -m studio finish <video.mp4> --format fhd --model anime-video",
                     "note": "el modelo genera 480x720; esto afina y escala al formato de entrega (Real-ESRGAN si está instalado, ffmpeg si no)"},
          "control_flags": "--model.control_frame_dim=4 (solo si el modelo se entrenó con control de audio; si no, el archivo se ignora)",
          "needs_gpu_for": "generación de vídeo (los comandos anteriores)"}
    json.dump(ep, open(_w(ctx, "episode.json"), "w"), indent=1, ensure_ascii=False)
    return "episode.json"


# ---- lip-sync helpers (moved from the CLI) ----------------------------------------------------------------------
def video_mouth(path, bbox=None):
    import imageio

    from studio.lips.sync import mouth_series_from_video

    r = imageio.get_reader(path, "ffmpeg")
    fps = int(round(r.get_meta_data()["fps"]))
    series = mouth_series_from_video([f[::8, ::8] for f in r], bbox)
    r.close()
    return series, fps


def mouth_for_clip(w, sr, text, style, backend="auto"):
    """-> (openness per frame at style.fps, method). Priority: Rhubarb cues (audio-accurate) > word-timed visemes
    (faster-whisper word timestamps) > text visemes warped to the loudness envelope. Failures fall through to the next."""
    from studio.lips import rhubarb as RB
    from studio.lips import sync as LS
    from studio.lips import visemes as V
    from studio.sound import mix as M

    dur = len(w) / sr
    if backend in ("auto", "rhubarb") and RB.find_binary():
        try:
            import tempfile

            with tempfile.TemporaryDirectory() as tmp:
                wav = os.path.join(tmp, "line.wav")
                M.write_wav(wav, w, sr)
                return RB.cues_track(RB.run_rhubarb(wav, text), dur, style.fps), "rhubarb"
        except Exception:
            pass
    if backend in ("auto", "words"):
        try:
            import importlib.util

            if importlib.util.find_spec("faster_whisper") is not None:
                import tempfile

                from studio.audio import transcribe_words

                with tempfile.TemporaryDirectory() as tmp:
                    wav = os.path.join(tmp, "line.wav")
                    M.write_wav(wav, w, sr)
                    words = transcribe_words(wav)
                if words:
                    return V.viseme_track_words(words, dur, style.fps, None), "words"
        except Exception:
            pass
    env = LS.audio_envelope(w, sr, style.fps)
    return V.viseme_track(text, 0.0, dur, style.fps, env), "text"


def lip_sync(ws, out, vi, dlg, rep, sr, video="", sync=False, backend="auto"):
    """Mouth track for animators (always) + re-timing to the generated video's mouth activity (when a video is given)."""
    from studio.lips import sync as LS
    from studio.lips import visemes as V
    from studio.lips.style import MouthStyle, apply_style
    from studio.sound import mix as M

    sp = os.path.join(ws, "mouth_style.json")
    style = MouthStyle.load(sp) if os.path.exists(sp) else MouthStyle()
    shifts = [0.0] * len(rep["clips"])
    if sync and video and vi == 0:
        mouth, vfps = video_mouth(video)
        before = LS.sync_score(mouth, LS.audio_envelope(dlg, sr, vfps), vfps)
        shifts = LS.align_lines(mouth, rep["clips"], sr, vfps)
        dlg = M.compose(rep["clips"], shifts, len(dlg) / sr, sr)
        after = LS.sync_score(mouth, LS.audio_envelope(dlg, sr, vfps), vfps)
        print(f"  lip-sync vs video: {before['score']:.2f} -> {after['score']:.2f} (shifts {[round(x, 2) for x in shifts]})")
    tracks = []
    for (start, w), sh, (who, text) in zip(rep["clips"], shifts, rep["meta"]):
        raw, method = mouth_for_clip(w, sr, text, style, backend)
        trk = apply_style(raw, style, style.fps)
        tracks.append({"character": who, "start": round(start + sh, 3), "fps": style.fps, "method": method,
                       "openness": [round(float(x), 2) for x in trk]})
    os.makedirs(os.path.join(out, "sound"), exist_ok=True)
    json.dump({"style": vars(style), "tracks": tracks}, open(os.path.join(out, "sound", f"video_{vi:03d}_mouths.json"), "w"))
    return dlg


EPISODE_PHASES = [
    Phase("story", "Lectura del guion (script-hypercartoon)", 20, c_story, essential=True),
    Phase("emotion", "Emoción de los personajes (emotions-hypercartoon)", 12, c_emotion),
    Phase("plan", "Prompts y plan de cómputo", 18, c_plan, essential=True),
    Phase("voices", "Voz de los personajes", 25, c_voices),
    Phase("mix", "Boca, ambiente y mezcla", 20, c_mix),
    Phase("control", "Control de audio para el vídeo", 4, c_control),
    Phase("package", "Paquete del episodio", 5, c_package),
]


def make_ctx(ws, out, text, **opts):
    return {"ws": ws, "out": out, "text": text, "opts": opts}
