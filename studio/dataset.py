"""Learning -> training data. Turns the analysed material into what `train.py` consumes (docs/dataset.md): clips per stage,
one caption per 3-second chunk, scene-boundary flags, the input for data/precomp_text.py and the final train_<N>s.jsonl.

Captions: `HeuristicCaptioner` (CPU, generic: style token + pacing / motion / colour / sound) so the pipeline always yields a
valid dataset; `QwenVLCaptioner` (GPU, Qwen2.5-VL video captions, the kind of re-captioning ViMix / VC4VG report helps T2V
training) for real descriptions. Every caption starts with the project's style token, which is what lets the model learn
distinct styles and what style fusion later blends."""
import json
import os
import re
from typing import Dict, List, Optional

from hypercartoon.models.cogvideo import control_data as CD
from studio import corpus as C
from studio import overlays as OV
from studio.ingest import load_manifest

SEG = 3.0
TEXT_MAXLEN = 493       # default of data/precomp_text.py
NAMES = [("black", (0, 0, 0)), ("white", (255, 255, 255)), ("gray", (128, 128, 128)), ("red", (220, 40, 40)), ("orange", (240, 140, 30)),
         ("yellow", (240, 220, 50)), ("green", (50, 180, 70)), ("teal", (40, 170, 170)), ("blue", (50, 80, 220)),
         ("purple", (140, 60, 190)), ("pink", (240, 130, 190)), ("brown", (130, 80, 40))]


def color_name(rgb) -> str:
    return min(NAMES, key=lambda n: sum((a - b) ** 2 for a, b in zip(rgb, n[1])))[0]


def safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_") or "x"


class HeuristicCaptioner:
    """Generic but honest captions from what the analysis measured. No model, no GPU."""

    def caption(self, ctx: dict) -> str:
        mot = "fast action" if ctx["motion"] > 0.08 else "gentle movement" if ctx["motion"] < 0.02 else "moderate movement"
        light = "bright" if ctx["brightness"] > 0.6 else "dark" if ctx["brightness"] < 0.35 else "evenly lit"
        cols = list(dict.fromkeys(color_name(c) for c in ctx["palette"][:3]))
        snd = ", with dialogue" if ctx.get("speech", 0) > 0.3 else ""
        sh = ctx.get("shot")
        if sh:  # measured by studio.analysis: framing, camera, subject position and colour
            parts = [f"{sh['shot_type_en']}", sh["camera_en"], f"main subject in the {sh['cell_en']}" if sh.get("cell_en") else None, sh.get("color_en")]
            return ", ".join(p for p in parts if p) + f", {mot}{snd}"
        return f"a {light} animated scene with {mot}, dominated by {' and '.join(cols) or 'mixed'} colours{snd}"


class QwenVLCaptioner:
    """Qwen2.5-VL video captioner (needs transformers, qwen-vl-utils, a GPU). Follows the model card's usage; validate on GPU."""

    PROMPT = ("Describe this animated clip for a text-to-video training set: the characters and what they do, the setting, "
              "camera and motion, in one or two sentences. Do not mention the art style. Never mention or transcribe any text, subtitles, "
              "captions, logos, watermarks, credits or symbols that appear on screen.")

    def __init__(self, model_id: str = "Qwen/Qwen2.5-VL-7B-Instruct", device: str = "cuda"):
        from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

        self.proc = AutoProcessor.from_pretrained(model_id)
        self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(model_id, torch_dtype="auto").to(device).eval()
        self.device = device

    def caption(self, ctx: dict) -> str:
        from qwen_vl_utils import process_vision_info

        msgs = [{"role": "user", "content": [{"type": "video", "video": ctx["clip"], "fps": 2.0}, {"type": "text", "text": self.PROMPT}]}]
        text = self.proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        img, vid = process_vision_info(msgs)
        inp = self.proc(text=[text], images=img, videos=vid, padding=True, return_tensors="pt").to(self.device)
        out = self.model.generate(**inp, max_new_tokens=120)
        return self.proc.batch_decode(out[:, inp.input_ids.shape[1]:], skip_special_tokens=True)[0].strip()


def get_captioner(kind: str = "heuristic", device: str = "cuda"):
    if kind == "heuristic":
        return HeuristicCaptioner()
    if kind == "qwen":
        return QwenVLCaptioner(device=device)
    raise ValueError("captioner: heuristic | qwen")


EN_TYPE = {"primer plano": "close-up", "plano medio": "medium shot", "plano completo": "full shot", "plano general": "wide shot",
           "plano de ambiente (sin personaje)": "establishing shot", "sin datos": ""}
EN_CAM = {"fija": "static camera", "paneo derecha": "camera pans right", "paneo izquierda": "camera pans left", "tilt arriba": "camera tilts up",
          "tilt abajo": "camera tilts down", "zoom/dolly in": "camera zooms in", "zoom/dolly out": "camera zooms out",
          "temblor / cámara en mano": "handheld camera", "indeterminada": ""}
EN_V = {"arriba": "upper", "medio": "middle", "abajo": "lower"}
EN_H = {"izquierda": "left", "centro": "center", "derecha": "right"}


def shot_context(analysis: Optional[dict], t: float) -> Optional[dict]:
    """Measured description (English, for captions) of the shot covering time t, from a studio.analysis result."""
    if not analysis:
        return None
    sh = next((s for s in analysis["shots"] if s["start"] <= t < s["end"]), None)
    if sh is None:
        return None
    sub = sh["framing"].get("subject")
    cam = EN_CAM.get(sh["camera"]["label"]) if sh["camera"]["label"] in EN_CAM else "+".join(EN_CAM.get(x, "") for x in sh["camera"]["labels"]).strip("+")
    pc = (analysis.get("color") or {}).get("per_shot", [{}] * (sh["index"] + 1))[sh["index"]] if analysis.get("color") else None
    from studio.analysis.color import descriptor_es

    color_en = descriptor_es({"metrics": pc["metrics"], "palette": pc["palette"]}) if pc and pc.get("metrics") and pc.get("palette") else None
    return {"shot_type_en": EN_TYPE.get(sh["framing"]["shot_type"], ""), "camera_en": cam,
            "cell_en": f"{EN_V.get(sub['vertical'], '')} {EN_H.get(sub['horizontal'], '')}".strip() if sub else None, "color_en": color_en}


# ---- clips ----------------------------------------------------------------------------------------------------------
def episode_folder(e: dict) -> str:
    return safe(f"{e['series']}_S{int(e['season']):02d}E{int(e['episode']):02d}")  # corpus.json keys are strings


def plan_clips(corpus: Dict, vids: Dict, seconds: int) -> List[dict]:
    """Consecutive `seconds`-long clips per episode (chronological). Clip names follow the data/precomp_text.py quirk: they
    must contain 'video_sample_'. Each clip lists its 3-second chunks with scene-start / scene-end flags from shot cuts."""
    clips, idx = [], 0
    for e in C.flat_order(corpus):
        v = vids.get(e["path"])
        if v is None:
            continue
        cuts = [s.start for s in v.shots[1:]]  # shot starts after the first
        for i in range(int(v.duration // seconds)):
            idx += 1
            t0 = i * seconds
            chunks = []
            for k in range(int(seconds // SEG)):
                a, b = t0 + k * SEG, t0 + (k + 1) * SEG
                near = lambda t: any(abs(c - t) <= 0.5 for c in cuts)
                chunks.append({"start": a, "end": b, "scene_start": bool(near(a) or (i == 0 and k == 0)), "scene_end": bool(near(b))})
            clips.append({"episode": episode_folder(e), "name": f"video_sample_{idx:05d}", "video": e["path"], "start": t0, "dur": seconds,
                          "chunks": chunks, "shots": len(v.shots), "motion": sum(s.motion for s in v.shots) / len(v.shots),
                          "brightness": sum(s.brightness for s in v.shots) / len(v.shots),
                          "palette": next((s.palette for s in v.shots if s.palette), [])})
    return clips


def clips_script(clips: List[dict], out_dir: str, seconds: int, fps: int = 16) -> str:
    lines = ["#!/bin/bash", "set -e", f"mkdir -p {out_dir}"]
    for c in clips:
        d = os.path.join(out_dir, c["episode"])
        lines.append(f'mkdir -p "{d}" && ffmpeg -loglevel error -y -ss {c["start"]} -t {seconds + 0.1} -i "{c["video"]}" -frames:v {fps * seconds + 1} '
                     f'-r {fps} -vf "{c["vf"] + "," if c.get("vf") else ""}scale=720:480:force_original_aspect_ratio=increase,crop=720:480" -an "{d}/{c["name"]}.mp4"')
    return "\n".join(lines) + "\n"


# ---- build ----------------------------------------------------------------------------------------------------------
def build_training_set(ws: str, seconds_list: List[int], captioner=None, style_token: Optional[str] = None,
                       progress=None, max_clips: Optional[int] = None, with_control: bool = True, overlay_mode: str = "mask") -> Dict:
    captioner = captioner or HeuristicCaptioner()
    token = style_token or f"{os.path.basename(os.path.normpath(ws))} animation style"
    vids = load_manifest(os.path.join(ws, "manifest.json"))
    corpus = json.load(open(os.path.join(ws, "corpus.json")))
    cand = json.load(open(os.path.join(ws, "audio_candidates.json"))) if os.path.exists(os.path.join(ws, "audio_candidates.json")) else {}
    d = os.path.join(ws, "dataset")
    os.makedirs(d, exist_ok=True)
    cap_path = os.path.join(d, "captions.json")
    cache = json.load(open(cap_path)) if os.path.exists(cap_path) else {}
    reports = OV.load_reports(ws) if overlay_mode != "off" else {}  # burned-in text / logos found by the overlays phase
    text_input, files, total, dropped, masked = {}, {}, 0, 0, 0
    waves: Dict[str, tuple] = {}  # episode -> (wave, speech ranges), decoded once
    idx_path = os.path.join(ws, "analysis", "index.json")
    a_index = json.load(open(idx_path)) if os.path.exists(idx_path) else {}
    a_cache: Dict[str, Optional[dict]] = {}
    for secs in seconds_list:
        clips = plan_clips(corpus, vids, secs)
        keep = [c for c in clips if not (c["video"] in reports and OV.overlaps_excluded(reports[c["video"]], c["start"], c["dur"]))]
        dropped += len(clips) - len(keep)  # title cards / credits never become training clips
        clips = keep[:max_clips]
        for c in clips:
            rep = reports.get(c["video"])
            v = vids[c["video"]]
            c["vf"] = OV.ffmpeg_filter(rep, overlay_mode, (v.width, v.height)) if rep else ""
        rows, n = [], len(clips)
        for ci, c in enumerate(clips):
            progress and progress((total + ci) / max(1, sum(len(plan_clips(corpus, vids, s)) for s in seconds_list)), c["name"])
            texts = []
            for k, ch in enumerate(c["chunks"]):
                key = f"{c['video']}@{ch['start']:.2f}"
                if key not in cache:
                    speech = (cand.get("sound", {}).get(c["video"]) or {}).get("speech", 0.0)
                    if c["video"] not in a_cache:
                        ap = a_index.get(c["video"])
                        a_cache[c["video"]] = json.load(open(os.path.join(ws, ap))) if ap and os.path.exists(os.path.join(ws, ap)) else None
                    shot = shot_context(a_cache[c["video"]], ch["start"] + SEG / 2)
                    cache[key] = captioner.caption({**c, "speech": speech, "clip": c["video"], "start": ch["start"], "dur": SEG, "shot": shot})
                texts.append(f"{token}. {OV.sanitize_caption(cache[key])}")
                text_input[f"{c['name']}_c{k}"] = {"text": texts[-1], "scene_start": ch["scene_start"], "scene_end": ch["scene_end"],
                                                  "mp4": os.path.join("clips", c["episode"], f"{c['name']}_c{k}.mp4")}
            ctrl = None
            if with_control:
                ctrl = f"control/{c['episode']}/{c['name']}.npz"
                if c["video"] not in waves:
                    from studio.audio import SR, energy_vad, load_audio

                    w = load_audio(c["video"], SR)
                    waves[c["video"]] = (w, energy_vad(w, SR) if len(w) else [])
                w, rng_ = waves[c["video"]]
                from studio.control import clip_control

                CD.save_control(os.path.join(d, ctrl), frame_feats=clip_control(w, 16000, c["start"], c["dur"], rng_))
            lm = None
            if c["video"] in reports:  # 0 where the picture is a subtitle / logo / title card: the loss ignores it
                v = vids[c["video"]]
                m = OV.clip_loss_mask(reports[c["video"]], (v.width, v.height), c["start"], c["dur"], mode=overlay_mode)
                lm = f"lossmask/{c['episode']}/{c['name']}.npz"
                CD.save_loss_mask(os.path.join(d, lm), m)
                masked += int((m < 0.5).any())
            tmode = lambda ch: "-both" if ch["scene_start"] and ch["scene_end"] else "-start" if ch["scene_start"] else "-end" if ch["scene_end"] else ""
            rows.append({**({"control": ctrl} if ctrl else {}), **({"loss_mask": lm} if lm else {}), "vid_emb": f"vid/{c['episode']}/{c['name']}.pt",
                         "text_chunk_emb": [f"txt/text-3s-{TEXT_MAXLEN}{tmode(ch)}/{c['episode']}/{c['name']}_c{k}_txt_emb.pt" for k, ch in enumerate(c["chunks"])]})
        total += n
        with open(os.path.join(d, f"train_{secs}s.jsonl"), "w") as f:
            f.write("".join(json.dumps(r) + "\n" for r in rows))
        json.dump(clips, open(os.path.join(d, f"clips_{secs}s.json"), "w"), indent=1)
        open(os.path.join(d, f"make_clips_{secs}s.sh"), "w").write(clips_script(clips, os.path.join(d, "clips", f"{secs}s"), secs))
        files[secs] = {"clips": len(clips), "train_jsonl": f"dataset/train_{secs}s.jsonl", "script": f"dataset/make_clips_{secs}s.sh"}
    json.dump(cache, open(cap_path, "w"), ensure_ascii=False, indent=1)
    json.dump(text_input, open(os.path.join(d, "text_input.json"), "w"), ensure_ascii=False, indent=1)
    open(os.path.join(d, "COMANDOS.md"), "w", encoding="utf-8").write(commands_es(ws, seconds_list))
    return {"style_token": token, "stages": files, "captions": len(cache), "captioner": type(captioner).__name__,
            "overlays": {"mode": overlay_mode, "videos_with_reports": len(reports), "clips_dropped": dropped, "clips_with_masked_area": masked}}


def commands_es(ws: str, seconds_list) -> str:
    L = ["# Del material al entrenamiento", "", "Todo esto necesita GPU salvo el paso 1. Rutas relativas a `dataset/`.", "",
         "1. Cortar los clips (ffmpeg, CPU): `bash dataset/make_clips_<N>s.sh`",
         "2. Latentes de vídeo (VAE): `torchrun data/precomp_video.py --precomp.episode_dir dataset/clips/<N>s --precomp.video_length <N> "
         "--precomp.output_dir dataset/vid --precomp.vae_weight_path RUTA_VAE`",
         "3. Embeddings de texto (T5, 4 variantes de token de escena): `torchrun data/precomp_text.py --video_length 3 "
         f"--max_length {TEXT_MAXLEN} --checkpoint_dir RUTA_T5 --input_jsonl_file dataset/text_input.json --output_path dataset/txt`",
         "4. Entrenar por etapas, en orden: configura `dataset_path` (= `dataset/`) y `jsonl_paths` (= `dataset/train_<N>s.jsonl`) en "
         "`configs/train/hyper-mlp/<N>s.toml` y lanza `scripts/train_singlenode.sh`.", "",
         "5. (Opcional, capacidades nuevas) Control de audio: las filas llevan `control` (habla y volumen por fotograma latente). Para "
         "entrenarlo añade `model.control_frame_dim = 4` a la configuración y mantén ese valor al generar. Ver docs/capabilities.md.", "",
         "6. Texto y logos incrustados: los clips con rótulos/créditos no se cortan, cada clip lleva `loss_mask` (la pérdida ignora subtítulos y "
         "logos) y los subtítulos de entrenamiento nunca los mencionan. `train.py` aplica la máscara solo si las filas la traen. Ver docs/overlays.md.", "",
         f"Etapas generadas: {', '.join(f'{s}s' for s in seconds_list)}. Los subtítulos empiezan por el *token de estilo* del proyecto: "
         "úsalo igual al generar y, si vas a fusionar estilos, entrena cada fuente con su propio token."]
    return "\n".join(L) + "\n"
