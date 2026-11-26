"""python -m studio            -> terminal panel (choose a video or a folder)
python -m studio learn <folder|url|list|magnet ...> | sources | characters | name <id> <NAME> | create <script> | story <script> | sound | lips | cache | fuse | fuse-weights | dataset | post | check | bench | finish | formats | score | ab | pick | analyze | hires"""
import argparse
import glob
import json
import os

from studio import episode as EP
from studio import learning as L
from studio import pipeline as PL
from studio.characters import Registry


def _p(a, f):
    return os.path.join(a.workdir, f)


class _LineReporter(PL.Reporter):
    """Plain progress lines for scripted use."""

    def __init__(self, phases=None):
        self.phases = phases

    def begin(self, phases):
        self.phases = phases

    def phase_end(self, i, out):
        print(f"[{out.status:>7}] {out.title} ({out.seconds:.0f}s) {out.note}")


def source_options(a):
    from studio.sources import Options

    return Options(name=a.name or "", proxy_height=a.proxy_height, keep=a.keep, max_seconds=a.max_seconds, max_gb=a.max_gb, cookies=a.cookies or "", fetch_workers=a.fetch_workers)


def sources_cmd(a):
    """Dry run of the universal input: what would be learned (nothing is fetched)."""
    from studio import sources as S

    items = S.preview(a.inputs, source_options(a), a.workdir)
    for it in items:
        print(f"{it.kind:8} S{it.season:02d}E{it.episode:03d}  {it.rel}  <-  {it.uri}")
    print(f"{len(items)} vídeo(s); series: {sorted({i.rel.split('/')[0] for i in items})}")


def learn(a):
    os.makedirs(a.workdir, exist_ok=True)
    ctx = {"input": a.inputs[0], "inputs": a.inputs, "source_options": source_options(a), "detector": a.detector, "prompts": [x.strip() for x in a.prompts.split(",") if x.strip()] or None, "element_captioner": a.element_captioner, "overlay_mode": a.overlay_mode, "text_detector": a.text_detector or None, "ws": a.workdir, "device": a.device, "gpu_mem_gb": a.gpu_mem_gb, "workers": a.workers,
           "voice": a.voice, "vision": a.characters}
    phases = [p for p in L.LEARNING_PHASES if a.characters or p.key not in ("characters",)]
    outs = PL.run(phases, ctx, _LineReporter())
    L.finalize_kit(ctx, outs, sum(o.seconds for o in outs))
    print("paquete:", os.path.join(a.workdir, "episode_kit.json"))
    characters(a)


def sound(a):
    """Regenerate the dialogue of a `create` run and mix it with ambience."""
    from studio.sound import mix as M
    from studio.sound.bank import Bank
    from studio.sound.speak import get_speaker

    side = json.load(open(_p(a, "voices.json")))
    bank, speaker, sr = Bank(a.workdir), get_speaker(a.speaker, a.device), 24000
    for vi, segs in enumerate(side):
        dlg, rep = M.render_dialogue(segs, bank, speaker, sr)
        dlg = EP.lip_sync(a.workdir, a.workdir, vi, dlg, rep, sr, a.video, a.sync)
        bed = M.ambience_bed(bank.ambience_wav(), len(dlg), sr)
        out = _p(a, f"sound/video_{vi:03d}.wav")
        M.write_wav(out, M.mix(dlg, bed, sr), sr)
        print(f"video {vi}: {rep['lines']} lines, overflow {rep['overflow_s']}s, late {len(rep['late_lines'])} -> {out}")
        if a.video and vi == 0:
            M.mux(a.video, out, a.video.rsplit(".", 1)[0] + "_sound.mp4")
            print("muxed:", a.video.rsplit(".", 1)[0] + "_sound.mp4")


def fuse(a):
    """Blend two or more learned projects into an intermediate style."""
    from studio import fusion as F

    w = a.weights or [1.0] * len(a.projects)
    if len(w) != len(a.projects):
        raise SystemExit("hace falta un peso por proyecto")
    ctx = {"srcs": a.projects, "weights": w, "out": a.out, "mode": a.mode}
    outs = PL.run(F.FUSION_PHASES, ctx, _LineReporter())
    if any(o.status == "error" for o in outs):
        raise SystemExit("; ".join(o.note for o in outs if o.status == "error"))
    print("proyecto fusionado:", a.out, "· crea episodios con: python -m studio --workdir", a.out, "create GUION.txt")


def fuse_weights(a):
    """Interpolate fine-tuned checkpoints of the same base: model soup, or task arithmetic with --base."""
    from studio import fusion as F

    paths, ws = zip(*[(c.rsplit(":", 1)[0], float(c.rsplit(":", 1)[1])) for c in a.ckpt])
    sd = F.merge_state_dicts([F.load_state(p) for p in paths], ws, F.load_state(a.base) if a.base else None)
    F.save_state(sd, a.out)
    print(f"{len(sd)} tensores -> {a.out} ({'tarea aritmética sobre la base' if a.base else 'media ponderada'})")


def dataset(a):
    """Captions + clips + train jsonl for the stages of the plan (docs/dataset.md)."""
    from studio.dataset import build_training_set, get_captioner

    plan = json.load(open(_p(a, "plan.json")))
    secs = a.stage or [s["seconds"] for s in plan["stages"]]
    r = build_training_set(a.workdir, secs, get_captioner(a.captioner, a.device), a.style_token, max_clips=a.max_clips, overlay_mode=a.overlay_mode)
    ov = r["overlays"]
    if ov["videos_with_reports"]:
        print(f"texto/logos incrustados ({ov['mode']}): {ov['clips_dropped']} clips descartados, {ov['clips_with_masked_area']} con zona enmascarada")
    print(f"{r['captions']} subtítulos ({r['captioner']}) · token «{r['style_token']}» · etapas "
          + ", ".join(f"{k}s: {v['clips']} clips" for k, v in r["stages"].items()) + f" -> {_p(a, 'dataset/COMANDOS.md')}")


def check(a):
    from studio import requirements as RQ

    r = RQ.run(a.workdir)
    sm = r["summary"]
    print(f"Veredicto: {sm['overall'].upper()} (lo limita: {sm['limiting']}) -> {_p(a, 'REQUISITOS.md')}")
    for c in r["checks"]:
        print(f"  [{c['verdict']:>12}] {c['title']}: {c['have']:.1f} {c['unit']}  {c['missing']}")


def bench(a):
    from studio import timing as TM

    res = TM.run_bench(a.sizes, a.lines, a.out, a.sec_per_step_segment, tuple(a.resolution))
    print(f"catálogo -> {os.path.join(a.out, 'TIEMPOS.md')}")
    for k, v in res["learning"]["phases"].items():
        print(f"  {k:<12} fijo {v['fixed_s']:.2f}s + {v['per_unit_s']:.2f}s/min de material (r²={v['r2']:.2f})")


def finish(a):
    """Sharpen + scale generated videos to a delivery format (Real-ESRGAN when installed, ffmpeg otherwise)."""
    from studio import finish as FN

    for v in a.videos:
        dst = os.path.join(a.out, os.path.splitext(os.path.basename(v))[0] + f"_{a.format}.mp4") if a.out else os.path.splitext(v)[0] + f"_{a.format}.mp4"
        r = FN.finish_video(v, dst, a.format, a.fit, a.model, a.tile, not a.no_half, a.device, a.sharpen, a.denoise, a.crf,
                            use_ai=not a.cpu, allow_download=a.allow_download, weights_dir=a.weights, dry=a.dry)
        p = r["plan"]
        print(f"{os.path.basename(v)}: {p['src'][0]}x{p['src'][1]} -> {p['target'][0]}x{p['target'][1]} ({p['fit']}) · modo {r['mode']}"
              + (f" · {r['seconds']:.1f}s -> {dst}" if "seconds" in r else " · (simulación)"))


def analyze(a):
    """Measure a video: shots/scenes, camera, framing, elements and space, colour, labelled dialogue."""
    from studio.analysis import video as AV
    from studio.analysis import elements as EL

    det = EL.get_detector(a.detector, a.prompts.split(",") if a.prompts else None, a.device)
    for v in a.videos:
        r = AV.analyze_video(v, a.out, detector=det, dialogue=a.dialogue, ws=a.out, device=a.device, hf_token=a.hf_token or os.environ.get("HF_TOKEN"))
        sm = r["summary"]
        print(f"{os.path.basename(v)}: {sm['n_shots']} tomas · {sm['n_scenes']} escenas · cámara {sm['camera']} · planos {sm['shot_types']} · "
              f"diálogos {sm['dialogue_lines']} · color: {sm['color']} -> {a.out}")


def hires(a):
    """Stage B of docs/hires.md. Post-process refiners run here; the generative refiner is a GPU job (prints the refine_video.py command);
    enhance_a_video belongs to stage A (prints the generation flags)."""
    from studio import hires as HR
    from studio import tiling as TL

    if a.refiner == "enhance_a_video":
        print("enhance_a_video actúa en la FASE A (dentro de la generación base), no sobre un vídeo ya generado. Añade al comando de sample.py:",
              " ".join(HR.stage_a_flags(a.enhance_weight)))
        return
    refiner = None
    if a.refiner == "esrgan":
        from studio import finish as FN

        refiner = HR.make_refiner("esrgan", a.scale, upscaler=FN.RealESRGANUpscaler(a.model, a.tile, not a.no_half, a.device, a.weights, a.allow_download))
    elif a.refiner == "identity":
        refiner = HR.make_refiner("identity")
    for v in a.videos:
        dst = os.path.join(a.out, os.path.splitext(os.path.basename(v))[0] + f"_x{a.scale:g}.mp4") if a.out else os.path.splitext(v)[0] + f"_x{a.scale:g}.mp4"
        if a.refiner == "generative":
            r = HR.hires_video(v, dst, a.scale, a.mode, a.overlap_pixels, None, dry=True, steps=a.steps, base_vram_gb=a.base_vram_gb)
            extra = f" --refine.overlap_pixels {a.overlap_pixels}" if a.overlap_pixels else ""
            print(f"torchrun --nproc_per_node=1 refine_video.py --job.config_file configs/eval/hyper-mlp/3s.toml --eval.input_file PROMPTS.jsonl "
                  f"--eval.num_denoising_steps={a.steps} --refine.input {v} --refine.output {dst} --refine.scale {a.scale:g} --refine.mode {a.mode} "
                  f"--refine.strength {a.strength} --refine.lam {a.lam}{extra}")
        else:
            r = HR.hires_video(v, dst, a.scale, a.mode, a.overlap_pixels, refiner, not a.no_exposure_matching, a.allow_visible_seams, a.seam_threshold,
                               a.window, dry=a.dry, steps=a.steps, base_vram_gb=a.base_vram_gb)
        c = r["cost"]
        print(f"{os.path.basename(v)}: {r['source'][0]}x{r['source'][1]} -> {r['target'][0]}x{r['target'][1]} · modo {r['mode']} · piezas {r['tiles']} · "
              f"refinador {r['refiner']} (fase {r['stage']}) · {c['passes_per_step']:.1f} pasadas/paso = {c['relative_to_base']:.1f}x una pasada base · "
              f"{c['step_segments']:.0f} pasos×segmento (base {c['base_step_segments']:.0f}) · estado latente {c['state_gb'] * 1000:.0f} MB"
              + (f" · VRAM {c['vram_gb']:.0f} GB" if c["vram_gb"] else "")
              + (f" · costura {r['seam_visibility']['ratio']:.2f}" if "seam_visibility" in r else " · (simulación)")
              + (f" · vs Lanczos: temporal x{r['metrics_vs_lanczos']['temporal_ratio']:.2f}, bajas frecuencias {r['metrics_vs_lanczos']['lowfreq_psnr_db']:.1f} dB" if "metrics_vs_lanczos" in r else ""))
        for w in r["warnings"]:
            print("  aviso:", w)
    if a.dry or a.refiner == "generative":
        print("  costes por modo (pasadas de pieza por paso):")
        for mode in TL.MODES:
            p = TL.plan_tiles(tuple(r["target"]), tuple(r["source"]), mode, None)
            print(f"    {mode:<13} {p.passes_per_step:>4.1f}")


def score(a):
    from studio import quality as Q

    for v in a.videos:
        m = Q.score_video(v)
        line = f"{os.path.basename(v)}: " + " · ".join(f"{k} {m[k]:.4f}" for k in Q.DIRECTION)
        if a.text:  # text / logos / subtitles the generator drew by itself (0 = none)
            from studio import overlays as OV

            t = OV.score_video_intrusion(v)
            line += f" · intrusión de texto {t['intrusion']:.2f} (fotogramas con texto {t['text_frames']:.0%}, logos fijos {t['static_overlays']:.0f})"
        print(line)


def layers_cmd(a):
    """Knowledge in layers: per series and for the whole studio; compose a new style from any mix; bring in shows learned elsewhere."""
    from studio import layers as LY

    for src in a.import_from or []:
        got = LY.import_series(src, a.workdir, a.prefix)
        print(f"importadas {len(got)} serie(s) de {src}: {', '.join(got)}")
    if not a.no_build:
        r = LY.build(a.workdir)
        print(f"series: {', '.join(r['series'])}")
        print(f"estilo del estudio: {r['style']['style_prompt']}")
    if a.compose:
        spec = {}
        for item in a.set or []:
            layer, _, src = item.partition("=")
            if layer not in LY.LAYERS:
                raise SystemExit(f"capa desconocida «{layer}»; capas: {', '.join(LY.LAYERS)}")
            spec[layer] = {k.split(":")[0]: float(k.split(":")[1]) if ":" in k else 1.0 for k in src.split(",")}
        res = LY.compose_project(a.workdir, spec, a.compose)
        print(f"estilo «{a.compose}»: {res['style']['style_prompt']}\n  usa:  studio create guion.txt --style-layers {a.compose}")
    open(os.path.join(a.workdir, "layers", "CAPAS.md"), "w", encoding="utf-8").write(LY.report_es(a.workdir))
    print(f"informe -> {os.path.join(a.workdir, 'layers', 'CAPAS.md')}")


def _engine(a, hw=None):
    from studio.engines import hardware as HW
    from studio.engines.diffusers_engine import DiffusersEngine
    from studio.engines.registry import get

    hw = hw or HW.detect()
    eid = a.engine
    if eid == "auto":
        from studio.engines.registry import disk_problem

        pick = next((r for r in HW.recommend(hw) if r["fit"] != "no" and not disk_problem(get(r["id"]))), None)
        if pick is None:
            raise SystemExit("ningún motor cabe en esta máquina (GPU o disco insuficientes). Usa --dry para preparar el plan, o genera en otra máquina con GPU.\n"
                             + "\n".join(HW.advice_es(hw)) + f"\nDisco libre para pesos: {hw['disk_free_gb']} GB en {hw['hf_cache']}")
        eid = pick["id"]
        print(f"motor elegido para esta máquina: {eid}")
    return DiffusersEngine(get(eid), device=a.device_gen, offload=not a.no_offload, repo=a.repo, lora=a.lora, low_memory=a.low_memory)


def voices_cmd(a):
    """Voice cloning library: clone each character from audio alone (any source), link it to the character, test and verify it."""
    import numpy as np

    from studio import voices as VX
    from studio.audio import load_audio

    lib = VX.VoiceLibrary(a.workdir)
    act, args = a.action, a.args
    if act == "add":
        if len(args) < 2:
            raise SystemExit("uso: studio voices add NOMBRE FUENTE [FUENTE ...]   (ficheros de audio/vídeo, carpetas, URLs, YouTube, listas…)")
        from studio.sources import Options

        p = lib.add_inputs(args[0], args[1:], Options(max_seconds=a.max_seconds, cookies=a.cookies or "", fetch_workers=a.fetch_workers), separate=a.separate,
                           language=a.language, embedder=a.embedder, aliases=a.alias or [])
        sf = p["sufficiency"]
        print(f"{p['display']}: {p['seconds']:.1f} s de habla limpia en {len(p['clips'])} frases (referencia principal {p['primary_seconds']:.1f} s) · "
              f"veredicto {sf['verdict'].upper()}" + (f" · faltan {sf['missing_s']} s para el siguiente nivel" if sf["missing_s"] else "") + f" · {p['rejected']} frases descartadas (otras voces / ruido)")
        for e in p.get("fetch_errors", []):
            print("  !", e)
    elif act == "list":
        for n in lib.names():
            p = lib.profile(n)
            print(f"{n:<16} {p['seconds']:>5.1f}s  {p['sufficiency']['verdict']:<13} {p['language']:<5} alias {p.get('aliases') or '-'}  enlaces {p.get('links') or '-'}")
        if not lib.names():
            print("sin voces: studio voices add NOMBRE FUENTE …  |  studio voices from-corpus")
    elif act == "show":
        print(json.dumps({k: v for k, v in lib.profile(args[0]).items() if k not in ("embedding", "clips")}, ensure_ascii=False, indent=1))
    elif act == "alias":
        lib.link(args[0], args[1:])
        print(f"{args[0]} responde también a: {', '.join(args[1:])}")
    elif act == "from-corpus":
        made = lib.from_corpus(a.workdir)
        print(f"{len(made)} voz(ces) promovidas desde los episodios: {', '.join(made) or '—'}")
    elif act == "remove":
        lib.remove(args[0])
        print("eliminada", args[0])
    elif act == "say":
        from studio.sound.mix import write_wav
        from studio.sound.speak import get_speaker

        ref = lib.reference(args[0])
        if not ref:
            raise SystemExit(f"no hay voz «{args[0]}»")
        sp = get_speaker(a.speaker, a.device)
        w = sp.say(" ".join(args[1:]), ref, VX.PREFIX + args[0], None)
        write_wav(a.out, w, sp.sr)
        print("->", a.out, f"({type(sp).__name__})")
        if type(sp).__name__ == "ScratchVoice":
            print("  (voz guía: no clona; usa --speaker chatterbox|coqui|f5 en una máquina con esos paquetes)")
    elif act == "verify":
        r = lib.verify(args[0], load_audio(args[1], VX.SR))
        print(f"distancia a {args[0]}: {r['distance']:.2f} · otra voz más cercana: {r['closest_other']} ({r['closest_other_distance'] and round(r['closest_other_distance'], 2)}) · veredicto: {r['verdict']}")
    else:
        raise SystemExit("acciones: add | list | show | alias | from-corpus | say | verify | remove")


def engines_cmd(a):
    """Local generation engines (no paid platform): what each needs and which ones this machine can run."""
    from studio.engines import hardware as HW
    from studio.engines.registry import ENGINES

    hw = HW.detect()
    print(f"máquina: {hw['device']} · {hw['name']} · VRAM {hw['vram_gb']} GB · RAM {hw['ram_gb']} GB · torch {hw['torch']} · diffusers {hw['diffusers']}")
    for line in HW.advice_es(hw):
        print("  !", line)
    print(f"disco libre para pesos: {hw['disk_free_gb']} GB en {hw['hf_cache']}")
    print(f"\n{'motor':<20} {'cabe':<8} {'descarga':<14} {'VRAM mín/cómoda':<16} {'tamaño/fps':<14} {'máx':<7} licencia")
    print(f"{'hypercartoon':<20} {'—':<8} {'(tus pesos)':<14} {'H100 / ≥24 GB':<16} {'720x480/16':<14} {'63 s':<7} MIT (pesos CogVideoX: licencia propia) · tu motor, entrenado con tu serie")
    for r in HW.recommend(hw):
        e = ENGINES[r["id"]]
        from studio.engines.registry import disk_problem

        dl = f"{e.download_gb:g} GB" + (" ✗disco" if disk_problem(e) else " ✓" if e.download_gb else "")
        print(f"{e.id:<20} {r['fit']:<8} {dl:<14} {f'{e.min_vram_gb:g}/{e.ok_vram_gb:g} GB':<16} {f'{e.size[0]}x{e.size[1]}/{e.fps}':<14} {f'{e.max_seconds:.0f} s':<7} {e.license}")
    print("\nGenera con:  python -m studio render --engine auto   (o --engine wan22-ti2v-5b, ltx-video, …; --dry para ver el plan sin cargar nada)")


def render_cmd(a):
    from studio.engines import render as RD

    eps = sorted(glob.glob(_p(a, "episodes/episodio_*")))
    ep = a.episode or (eps[-1] if eps else None)
    if not ep:
        raise SystemExit("no hay episodios: ejecuta `studio create guion.txt` primero")
    if a.engine == "hypercartoon":
        print("El motor Hypercartoon se ejecuta con su propio sample.py (GPU, pesos entrenados); comandos de este episodio:")
        for c in RD.native_commands(ep):
            print("  ", c)
        return
    eng = _engine(a)
    size = tuple(int(x) for x in a.size.split("x"))
    rep = RD.render_episode(ep, eng, a.out, a.seed, a.steps, a.guidance, size, a.fps_out, dry=a.dry,
                            progress=lambda f, d="": print(f"  [{f * 100:3.0f}%] {d}", flush=True), only_video=a.only_video)
    e = rep["estimate"]
    print(f"{eng.spec.title}: {e['clips']} clips · {e['seconds']:.0f} s de vídeo · {e['denoising_steps_total']} pasos de difusión"
          + (f" · {e['hard_cuts_inside_scenes']} cortes dentro de escenas (el motor no continúa desde el último fotograma)" if e["hard_cuts_inside_scenes"] else ""))
    if a.dry:
        for c in rep["clips"][:12]:
            print(f"   {c['name']}  {c['seconds']:.0f}s  {c['prompt'][:90]}")
        return
    print("vídeo(s):", *rep["videos"], sep="\n  ")


def export_lora_cmd(a):
    from studio.engines.lora import export_dataset
    from studio.engines.registry import get

    r = export_dataset(a.workdir, a.out, get(a.engine), a.window, stage=a.stage)
    print(f"{r['samples']} muestras de {r['window_s']:.0f} s ({r['skipped_for_overlays']} descartadas por rótulos/logos) -> {r['out_dir']}  (ver LEEME.md)")


def train_lora_cmd(a):
    from studio.engines.registry import get
    from studio.engines.train_lora import train_ltx_lora

    spec = get(a.engine)
    if spec.lora_trainer != "builtin":
        raise SystemExit(f"{spec.title}: el entrenador integrado solo cubre ltx-video; para este motor entrena los mismos ficheros (prompt.txt + videos.txt) "
                         "con https://github.com/huggingface/finetrainers")
    w, h = (int(x) for x in a.size.split("x"))
    r = train_ltx_lora(a.data, a.out, a.repo or spec.repo, a.steps, a.rank, a.lr, (w, h), a.frames, spec.fps, a.device_gen if a.device_gen != "auto" else "cuda")
    print(f"LoRA guardado: {r['lora']}  ({r['samples']} muestras, {r['steps']} pasos, pérdida {r['losses'][0]:.3f} -> {r['losses'][-1]:.3f})")
    print(f"úsalo con:  studio render --engine {a.engine} --lora {a.out}")


def overlays_cmd(a):
    """What is burned into these videos (subtitles, title cards / credits, logos, bars) and would be kept out of the learning."""
    from studio import overlays as OV

    det = OV.ocr_detector(a.text_detector) if a.text_detector else None
    for v in a.videos:
        rep = OV.scan_video(v, detector=det)
        if a.save:
            OV.save_report(a.workdir, v, rep)
        print(f"{os.path.basename(v)}: {OV.describe_es(rep)}")
        for s in rep["static"]:
            print("   logo fijo en", [round(x, 2) for x in s["box"]])
        for t0, t1 in rep["text_segments"]:
            print(f"   rótulo/créditos {t0:.1f}-{t1:.1f} s")


def ab(a):
    """Paired A/B of two generation runs (same relative paths = same prompt and seed)."""
    from studio import quality as Q

    va, vb = Q.find_videos(a.a), Q.find_videos(a.b)
    keys = sorted(set(va) & set(vb))
    if not keys:
        raise SystemExit("no hay vídeos con la misma ruta relativa en A y B")
    cmp = Q.compare([Q.score_video(va[k]) for k in keys], [Q.score_video(vb[k]) for k in keys])
    rep = Q.report_es(cmp, os.path.basename(a.a.rstrip("/")), os.path.basename(a.b.rstrip("/")))
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
        open(a.out, "w", encoding="utf-8").write(rep)
    print(rep)


def pick(a):
    """Best candidate per prompt among several runs (same relative path = same prompt, different seed/settings)."""
    from studio import quality as Q

    runs = [Q.find_videos(d) for d in a.dirs]
    keys = sorted(set.intersection(*[set(r) for r in runs]))
    if not keys:
        raise SystemExit("no hay vídeos con la misma ruta relativa en todos los directorios")
    picked = {}
    for k in keys:
        sc = [Q.score_video(r[k]) for r in runs]
        i = Q.pick_best(sc)
        picked[k] = {"winner": a.dirs[i], "video": runs[i][k], "scores": sc}
        if a.link:
            dst = os.path.join(a.link, k)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if os.path.lexists(dst):
                os.remove(dst)
            os.symlink(os.path.abspath(runs[i][k]), dst)
    json.dump(picked, open(a.out, "w"), indent=1)
    wins = {d: sum(v["winner"] == d for v in picked.values()) for d in a.dirs}
    print(f"{len(keys)} prompts · victorias: " + ", ".join(f"{os.path.basename(d.rstrip('/'))} {n}" for d, n in wins.items()) + f" -> {a.out}")


def formats(a):
    from studio import finish as FN

    for k, (w, h) in FN.FORMATS.items():
        print(f"  {k:<9} {w}x{h}")
    print("modelos Real-ESRGAN:", ", ".join(f"{k} ({v['about']})" for k, v in FN.MODELS.items()))


def post(a):
    """Run the external polishing steps declared in postprocess.json on a generated video."""
    from studio import postprocess as PP

    steps = PP.load_steps(a.workdir)
    if not steps:
        raise SystemExit(f"no hay pasos: crea {_p(a, 'postprocess.json')} (ver studio/postprocess.py)")
    for r in PP.run_steps(steps, a.video, a.audio, _p(a, "post"), os.path.splitext(os.path.basename(a.video))[0], a.dry):
        print(r)


def story(a):
    plan = json.load(open(_p(a, "plan.json"))) if os.path.exists(_p(a, "plan.json")) else {"max_seconds": 63}
    reg = Registry.load(_p(a, "registry.json"))
    chars = {c["name"] for c in reg.characters() if c["id"] in reg.names}
    res, issues = EP.read_story(open(a.script, encoding="utf-8").read(), chars, plan["max_seconds"], a.story)
    from studio.story.plan import report_es

    os.makedirs(a.workdir, exist_ok=True)
    open(_p(a, "story_report.md"), "w", encoding="utf-8").write(report_es(res, issues))
    open(_p(a, "script.studio.txt"), "w", encoding="utf-8").write(res["script"])
    print(f"{len(res['reading']['scenes'])} escenas · lectura {res['source']} · {len(issues)} observaciones -> {_p(a, 'story_report.md')}")


def create(a):
    ctx = EP.make_ctx(a.workdir, a.workdir, open(a.script, encoding="utf-8").read(), emotion=a.emotion, story=a.story,
                      compute=a.compute, steps=a.steps, sec_per_step_segment=a.sec_per_step_segment, enhance_weight=a.enhance_weight,
                      style_layers=a.style_layers)
    outs = PL.run([p for p in EP.EPISODE_PHASES if p.key in ("story", "emotion", "plan", "package")], ctx, _LineReporter())
    if any(o.status == "error" for o in outs):
        raise SystemExit("; ".join(o.note for o in outs if o.status == "error"))
    print(ctx["comp"]["summary_es"])
    for ch, v in (ctx.get("voice_binding") or {}).items():
        print(f"  voz de {ch}: " + (f"clon «{v['profile']}» ({v['seconds']} s, {v['verdict']})" if v["source"] == "clone" else "voz de los episodios" if v["source"] == "corpus" else "voz guía (sin clon: `studio voices add`)"))
    for st in ctx["comp"]["runs"]:
        cfg = ctx["plan"]["stages"][-1]["layer"].replace("_", "-").replace("ttt", "hyper")
        print(f"run: torchrun sample.py --job.config_file configs/eval/{cfg}/{ctx['stage']}s.toml --eval.input_file {_p(a, f'prompts_s{st}.jsonl')} "
              f"--eval.num_denoising_steps={st} --guider.num_steps={st}")


def lips(a):
    from studio.lips.learn import learn_corpus_style

    st = learn_corpus_style(a.workdir)
    print(f"mouth style: {st.fps} fps, hold {st.hold_frames} frames, levels {[round(x, 2) for x in st.levels]}, "
          f"lead {st.lead_s * 1000:.0f} ms, from {st.n_samples} frames")


def characters(a):
    reg = Registry.load(_p(a, "registry.json"))
    rows = reg.characters()
    if not rows:
        print("no characters yet (run: learn FOLDER --characters)")
    for c in rows:
        v = f"voice {c['voice_id']} (lift {c['voice_lift']})" if c["voice_id"] else "voice unknown"
        print(f"[{c['id']}] {c['name']:<16} {c['kind']:<10} {c['seconds_on_screen']:>7}s  {c['episodes']} ep  {v}")


def name(a):
    reg = Registry.load(_p(a, "registry.json"))
    if a.id not in reg.visual.sums:
        raise SystemExit(f"unknown character id {a.id}")
    reg.names[a.id] = a.name.upper()
    reg.save(_p(a, "registry.json"))
    print(f"[{a.id}] -> {a.name.upper()}")


def cache_record(a):
    from studio import budget as B

    plan = json.load(open(_p(a, "plan.json")))
    cache = B.ShotCache(_p(a, "shot_cache.json"), cfg=f"{plan['stages'][-1]['layer']}")
    n = 0
    for i, line in enumerate(open(a.prompts, encoding="utf-8")):
        vid = os.path.join(a.videos, f"prompt-{i}", "000000.mp4")
        if os.path.exists(vid):
            cache.record([s["text"] for s in json.loads(line)], a.steps, vid)
            n += 1
    print(f"{n} vídeos registrados en la caché")


def src_args(p):
    p.add_argument("--name", default="", help="series name for online material (default: inferred)")
    p.add_argument("--proxy-height", type=int, default=480, help="height of the local copy kept from online material")
    p.add_argument("--keep", choices=["proxy", "full"], default="proxy", help="proxy: small re-encode (original never stored); full: original quality")
    p.add_argument("--max-seconds", type=float, default=0.0, help="only the first N seconds of every online video (0 = all; live streams default to 300)")
    p.add_argument("--max-gb", type=float, default=0.0, help="stop fetching when the sources folder reaches N GB")
    p.add_argument("--cookies", default="", help="cookies.txt for yt-dlp (material you are allowed to see)")
    p.add_argument("--fetch-workers", type=int, default=4, help="online videos fetched in parallel")
    p.add_argument("--overlay-mode", choices=["mask", "delogo", "crop", "off"], default="mask",
                   help="burned-in text / logos: mask = loss mask + drop title cards (default); delogo / crop also clean the clips; off = ignore")
    p.add_argument("--text-detector", choices=["", "easyocr", "paddle"], default="", help="OCR backend for real footage (default: built-in heuristic)")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="studio")
    ap.add_argument("--workdir", default="studio_ws")
    sp = ap.add_subparsers(dest="cmd")
    l = sp.add_parser("learn")
    l.add_argument("inputs", nargs="+", metavar="INPUT", help="folder, video, URL, YouTube video/playlist/channel, list file (.txt .csv .json .m3u), "
                   "open-directory page, RSS feed, Dropbox/Drive/S3/IPFS link, rtsp/rtmp stream, .torrent or magnet — any number, mixed")
    src_args(l)
    l.add_argument("--gpu_mem_gb", type=float, default=80)
    l.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    l.add_argument("--detector", choices=["auto", "blobs", "yolo", "dino"], default="auto", help="scene elements: Grounding DINO(+SAM 2) with --prompts, YOLO, or CPU blobs")
    l.add_argument("--prompts", default="", help="comma-separated elements to find with Grounding DINO, e.g. 'person,dog,car,tree'")
    l.add_argument("--element-captioner", choices=["measured", "florence2", "blip"], default="measured", help="how each element silhouette is described")
    l.add_argument("--characters", action="store_true", help="detect objects/characters and voices (needs backends)")
    l.add_argument("--device", default="cuda")
    l.add_argument("--voice", choices=["auto", "logmel", "ecapa"], default="auto")
    sc = sp.add_parser("sources", help="show what an input (URL, playlist, list, torrent ...) resolves to, without fetching")
    sc.add_argument("inputs", nargs="+", metavar="INPUT")
    src_args(sc)
    sp.add_parser("characters")
    so = sp.add_parser("sound")
    so.add_argument("--speaker", choices=["auto", "scratch", "chatterbox", "coqui", "f5"], default="scratch")
    so.add_argument("--video", default="", help="optional generated mp4 to mux the first video's sound into")
    so.add_argument("--device", default="cuda")
    so.add_argument("--sync", action="store_true", help="re-time dialogue to the mouths of --video")
    sp.add_parser("lips", help="learn the show's mouth-animation convention from the corpus")
    n = sp.add_parser("name")
    n.add_argument("id", type=int)
    n.add_argument("name")
    c = sp.add_parser("create")
    c.add_argument("script")
    c.add_argument("--steps", type=int, default=50)
    c.add_argument("--emotion", choices=["auto", "emotions", "lexicon", "off"], default="auto")
    c.add_argument("--story", choices=["auto", "native", "script"], default="auto", help="script reader")
    c.add_argument("--style-layers", default=None, metavar="NAME", help="use the style of layers/NAME (_studio, a show, or one made with `layers --compose`)")
    c.add_argument("--enhance-weight", type=float, default=None, help="stage A: add --eval.enhance_weight to the generation commands (Enhance-A-Video-style)")
    c.add_argument("--compute", choices=["adaptive", "draft", "full"], default="adaptive")
    c.add_argument("--sec-per-step-segment", type=float, default=None, help="measured GPU seconds per step per 3 s segment")
    st = sp.add_parser("story", help="read a script, validate it and write the Spanish report (no generation)")
    st.add_argument("script")
    st.add_argument("--story", choices=["auto", "native", "script"], default="auto")
    fu = sp.add_parser("fuse", help="blend learned projects into an intermediate style")
    fu.add_argument("projects", nargs="+", help="project folders (each with profile.json)")
    fu.add_argument("--weights", type=float, nargs="+", help="one weight per project (default: equal)")
    fu.add_argument("--out", required=True)
    fu.add_argument("--mode", choices=["embedding", "text"], default="embedding")
    fw = sp.add_parser("fuse-weights", help="interpolate fine-tuned checkpoints (same base)")
    fw.add_argument("--ckpt", nargs="+", required=True, help="PATH:WEIGHT (.safetensors or .pt state dict)")
    fw.add_argument("--base", help="base checkpoint: task arithmetic base + sum w_i (theta_i - base)")
    fw.add_argument("--out", required=True)
    ds = sp.add_parser("dataset", help="captions + clips + train jsonl from the learned material")
    ds.add_argument("--stage", type=int, nargs="+", help="stage seconds (default: all in plan.json)")
    ds.add_argument("--captioner", choices=["heuristic", "qwen"], default="heuristic")
    ds.add_argument("--style-token", default=None)
    ds.add_argument("--max-clips", type=int, default=None)
    ds.add_argument("--device", default="cuda")
    ds.add_argument("--overlay-mode", choices=["mask", "delogo", "crop", "off"], default="mask")
    sp.add_parser("check", help="is the material enough? verdict per capability + minutes missing")
    bn = sp.add_parser("bench", help="timing catalog: seconds per minute of material, per phase")
    bn.add_argument("--sizes", type=float, nargs="+", default=[16, 32, 64], help="synthetic content sizes in seconds")
    bn.add_argument("--lines", type=int, nargs="+", default=[2, 6, 12])
    bn.add_argument("--resolution", type=int, nargs=2, default=[320, 180], metavar=("W", "H"), help="synthetic frame size; use your footage size")
    bn.add_argument("--out", default="bench_out")
    bn.add_argument("--sec-per-step-segment", type=float, default=None)
    fi = sp.add_parser("finish", help="sharpen and scale videos to a delivery format (Real-ESRGAN / ffmpeg)")
    fi.add_argument("videos", nargs="+")
    fi.add_argument("--format", default="fhd", help="hd | fhd | qhd | 4k | square | vertical | cinema | WxH")
    fi.add_argument("--fit", choices=["fit", "fill", "stretch"], default="fit")
    fi.add_argument("--model", choices=["anime-video", "anime6b", "general", "x4plus"], default="anime-video")
    fi.add_argument("--tile", type=int, default=0, help="tile size for low VRAM (0 = no tiling)")
    fi.add_argument("--sharpen", choices=["off", "light", "medium", "strong"], default="light")
    fi.add_argument("--denoise", action="store_true")
    fi.add_argument("--crf", type=int, default=16)
    fi.add_argument("--cpu", action="store_true", help="skip the AI step (ffmpeg only)")
    fi.add_argument("--no-half", action="store_true")
    fi.add_argument("--allow-download", action="store_true", help="let Real-ESRGAN fetch missing weights from GitHub releases")
    fi.add_argument("--weights", default=None)
    fi.add_argument("--device", default="cuda")
    fi.add_argument("--out", default=None)
    fi.add_argument("--dry", action="store_true")
    sp.add_parser("formats", help="list delivery formats and AI models")
    an = sp.add_parser("analyze", help="shots, scenes, camera movement, framing, elements + space, colour and labelled dialogue of videos")
    an.add_argument("videos", nargs="+")
    an.add_argument("--out", default="analysis_out")
    an.add_argument("--detector", choices=["auto", "blobs", "yolo", "dino"], default="auto")
    an.add_argument("--prompts", default=None, help="comma-separated elements to find with Grounding DINO (e.g. 'person,door,table')")
    an.add_argument("--dialogue", choices=["auto", "whisperx", "faster", "off"], default="auto")
    an.add_argument("--hf-token", default=None, help="Hugging Face token for WhisperX speaker diarization (or env HF_TOKEN)")
    an.add_argument("--device", default="cuda")
    hr = sp.add_parser("hires", help="two-stage high resolution: upsample + refine in native-size tiles + blend (stage B of docs/hires.md)")
    hr.add_argument("videos", nargs="+")
    hr.add_argument("--scale", type=float, default=2.0)
    hr.add_argument("--mode", choices=["no_overlap", "seam_aware", "full_overlap"], default="seam_aware")
    hr.add_argument("--overlap-pixels", type=int, default=None, help="feather width (seam_aware) / minimum overlap (full_overlap); invalid for no_overlap")
    hr.add_argument("--refiner", choices=["identity", "esrgan", "generative", "enhance_a_video"], default="identity")
    hr.add_argument("--window", choices=["cosine", "gaussian"], default="cosine")
    hr.add_argument("--no-exposure-matching", action="store_true", help="only with --allow-visible-seams")
    hr.add_argument("--allow-visible-seams", action="store_true")
    hr.add_argument("--seam-threshold", type=float, default=1.5)
    hr.add_argument("--steps", type=int, default=25, help="denoising steps used for the cost estimate / generative command")
    hr.add_argument("--base-vram-gb", type=float, default=None, help="your measured peak VRAM of one base pass")
    hr.add_argument("--strength", type=float, default=0.35, help="generative: re-noising strength (1 = regenerate, small = keep stage A)")
    hr.add_argument("--lam", type=float, default=0.8, help="generative: low-frequency consistency to the stage-A video")
    hr.add_argument("--enhance-weight", type=float, default=2.0)
    hr.add_argument("--model", choices=["anime-video", "anime6b", "general", "x4plus"], default="anime-video")
    hr.add_argument("--tile", type=int, default=0)
    hr.add_argument("--no-half", action="store_true")
    hr.add_argument("--allow-download", action="store_true")
    hr.add_argument("--weights", default=None)
    hr.add_argument("--device", default="cuda")
    hr.add_argument("--out", default=None)
    hr.add_argument("--dry", action="store_true")
    sc = sp.add_parser("score", help="cheap quality proxies of videos (flicker, jerk, correlation, colour drift, sharpness)")
    sc.add_argument("videos", nargs="+")
    sc.add_argument("--text", action="store_true", help="also measure text / logos / subtitles drawn into the video")
    vc = sp.add_parser("voices", help="voice cloning library: clone characters from audio alone (any source) and link them by name")
    vc.add_argument("action", choices=["add", "list", "show", "alias", "from-corpus", "say", "verify", "remove"])
    vc.add_argument("args", nargs="*")
    vc.add_argument("--language", default="auto", help="es, en, … (XTTS needs it)")
    vc.add_argument("--embedder", choices=["auto", "voiceprint", "ecapa"], default="auto", help="auto = ECAPA when speechbrain is installed, else the built-in voiceprint")
    vc.add_argument("--separate", action="store_true", help="separate vocals from music with Demucs first")
    vc.add_argument("--alias", nargs="+", help="other names this character answers to")
    vc.add_argument("--max-seconds", type=float, default=0.0, help="only the first N seconds of every online source")
    vc.add_argument("--cookies", default="")
    vc.add_argument("--fetch-workers", type=int, default=4)
    vc.add_argument("--speaker", choices=["auto", "scratch", "chatterbox", "coqui", "f5"], default="auto")
    vc.add_argument("--device", default="cuda")
    vc.add_argument("--out", default="voz_prueba.wav")
    en = sp.add_parser("engines", help="local video-generation engines (Wan 2.2, HunyuanVideo 1.5, LTX-Video, CogVideoX, Mochi): what this machine can run")
    rd = sp.add_parser("render", help="generate the episode video with a local engine (GPU) from the prompts written by `create`")
    rd.add_argument("--engine", default="auto", help="auto | hypercartoon | wan22-ti2v-5b | ltx-video | hunyuan-video-1.5 | cogvideox-5b | cogvideox-2b | mochi-1")
    rd.add_argument("--episode", default=None, help="episode folder (default: the latest of the project)")
    rd.add_argument("--dry", action="store_true", help="show the clips and the work without loading any model")
    rd.add_argument("--lora", default=None, help="a style LoRA trained on your show (see export-lora)")
    rd.add_argument("--repo", default=None, help="another Hugging Face repo / local folder for the weights")
    rd.add_argument("--device-gen", default="auto", choices=["auto", "cuda", "mps", "cpu"])
    rd.add_argument("--low-memory", action="store_true", help="encode the prompt with the big text encoder first, free it, then load the video model (16 GB machines)")
    rd.add_argument("--no-offload", action="store_true", help="keep the whole model on the GPU (needs more VRAM, faster)")
    rd.add_argument("--seed", type=int, default=0)
    rd.add_argument("--steps", type=int, default=None)
    rd.add_argument("--guidance", type=float, default=None)
    rd.add_argument("--size", default="720x480", help="delivery size WxH of the joined episode")
    rd.add_argument("--fps-out", type=int, default=16)
    rd.add_argument("--only-video", type=int, default=None)
    rd.add_argument("--out", default=None)
    tl = sp.add_parser("train-lora", help="train a style LoRA for LTX-Video from an export-lora folder (built-in trainer)")
    tl.add_argument("--engine", default="ltx-video")
    tl.add_argument("--data", required=True, help="folder written by export-lora (after running make_videos.sh)")
    tl.add_argument("--out", required=True)
    tl.add_argument("--steps", type=int, default=500)
    tl.add_argument("--rank", type=int, default=16)
    tl.add_argument("--lr", type=float, default=1e-4)
    tl.add_argument("--size", default="704x480")
    tl.add_argument("--frames", type=int, default=49)
    tl.add_argument("--repo", default=None)
    tl.add_argument("--device-gen", default="auto", choices=["auto", "cuda", "mps", "cpu"])
    el = sp.add_parser("export-lora", help="export what was learned as a LoRA training set for a third-party engine (prompt.txt + videos.txt)")
    el.add_argument("--engine", required=True)
    el.add_argument("--out", required=True)
    el.add_argument("--window", type=float, default=None, help="seconds per training sample (default: the engine's maximum, in 3 s steps)")
    el.add_argument("--stage", type=int, default=None)
    ly = sp.add_parser("layers", help="knowledge in layers (characters, backgrounds, palettes, scene types, rhythm) per show and per studio; compose a style")
    ly.add_argument("--import-from", nargs="+", help="other project folders (other shows of the same studio) whose layers to bring in")
    ly.add_argument("--prefix", default="", help="prefix for imported series names")
    ly.add_argument("--no-build", action="store_true", help="do not rebuild from the analysis, only import / compose")
    ly.add_argument("--compose", metavar="NAME", help="build a new style called NAME from --set choices")
    ly.add_argument("--set", nargs="+", metavar="LAYER=SRC[:W],SRC[:W]", help="e.g. palettes=_studio rhythm=ShowA:0.7,ShowB:0.3 characters=ShowA,ShowB")
    ov = sp.add_parser("overlays", help="find burned-in subtitles, title cards, logos and bars (what the learning keeps out)")
    ov.add_argument("videos", nargs="+")
    ov.add_argument("--text-detector", choices=["", "easyocr", "paddle"], default="")
    ov.add_argument("--save", action="store_true", help="store the reports in --workdir/overlays")
    ab_ = sp.add_parser("ab", help="paired A/B of two generation runs with bootstrap confidence intervals")
    ab_.add_argument("a")
    ab_.add_argument("b")
    ab_.add_argument("--out", default=None)
    pk = sp.add_parser("pick", help="best candidate per prompt across several runs (test-time search by selection)")
    pk.add_argument("dirs", nargs="+")
    pk.add_argument("--out", default="picked.json")
    pk.add_argument("--link", default=None, help="folder where symlinks to the winners are created")
    po = sp.add_parser("post", help="run external polishing tools (postprocess.json) on a generated video")
    po.add_argument("video")
    po.add_argument("--audio", default=None)
    po.add_argument("--dry", action="store_true")
    cr = sp.add_parser("cache", help="record generated videos so unchanged ones are never regenerated")
    cr.add_argument("prompts")
    cr.add_argument("videos")
    cr.add_argument("--steps", type=int, default=50)
    a = ap.parse_args(argv)
    if a.cmd is None:
        from studio.tui import main as tui_main

        return tui_main([])
    {"learn": learn, "characters": characters, "name": name, "create": create, "sound": sound, "lips": lips, "story": story, "cache": cache_record, "fuse": fuse, "fuse-weights": fuse_weights, "dataset": dataset, "post": post, "check": check, "bench": bench, "finish": finish, "formats": formats, "score": score, "ab": ab, "pick": pick, "analyze": analyze, "hires": hires, "sources": sources_cmd, "overlays": overlays_cmd, "layers": layers_cmd, "engines": engines_cmd, "voices": voices_cmd, "render": render_cmd, "train-lora": train_lora_cmd, "export-lora": export_lora_cmd}[a.cmd](a)


if __name__ == "__main__":
    main()
