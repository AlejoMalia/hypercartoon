"""Story -> production plan. Merges the native reading with script-hypercartoon's (when present), validates the script against what
the generator can actually do, auto-fixes what it can, and writes a Spanish report for the author."""
from typing import Dict, List, Optional

from studio.story import native
from studio.story.convert import Doc, doc_to_script, parse_doc
from studio.story.pacing import SEG, dialogue_seconds, scene_seconds


def analyze(text: str, bridge=None, language: str = "auto") -> Dict:
    """-> {doc, script, reading, threads, source, notes}. script-hypercartoon enriches (tension per scene, threads); never required."""
    doc = parse_doc(text)
    if not doc.scenes:
        raise SystemExit("El guion no contiene escenas ni diálogos reconocibles.")
    reading = native.read(doc)
    thr, source, notes = native.threads(reading), "native", []
    if bridge is not None:
        try:
            ab = bridge.analyze(doc_to_script(doc), language, completion=True)
            r = ab["reading"]
            ts = [a.get("tension") for a in r.get("scenes", [])]
            informative = len(ts) == len(doc.scenes) and all(t is not None for t in ts) and max(ts) > 0 and len(set(ts)) > 1
            if informative:  # script-hypercartoon's curve needs page-scale text; on a short script it is flat/empty -> keep the native one
                for sc, t in zip(reading["scenes"], ts):
                    sc["tension"] = float(t)
                reading["tension"] = [s["tension"] for s in reading["scenes"]]
            else:
                notes.append("La curva de tensión de script-hypercartoon no es informativa para este guion (necesita varias páginas o segmentó otras escenas); se usó la tensión nativa.")
            if r.get("acts"):
                reading["acts"] = r["acts"]
            comp = ab.get("completion") or {}
            ab_threads = comp.get("openThreads") or []
            seen = {(t["kind"], t["subject"]) for t in thr}
            thr += [t for t in ab_threads if (t["kind"], t["subject"]) not in seen]
            reading["script"] = {"confidence": r.get("confidence"), "summary": comp.get("summary"), "returnsToStart": comp.get("returnsToStart")}
            source = "script-hypercartoon+native"
        except Exception as e:  # the bridge is an enhancement, never a blocker
            notes.append(f"Motor de script-hypercartoon no disponible ({e}); lectura nativa.")
    for s, sc in zip(doc.scenes, reading["scenes"]):
        s.tension = sc.get("tension")
    return {"doc": doc, "script": doc_to_script(doc), "reading": reading, "threads": thr, "source": source, "notes": notes}


def validate(res: Dict, known_looks: set, max_seconds: int) -> List[dict]:
    """Problems that would make generation hard, each with severity and whether it was already fixed automatically."""
    doc: Doc = res["doc"]
    issues = []
    for i, s in enumerate(doc.scenes, 1):
        need = dialogue_seconds(s.lines)
        sec = scene_seconds(s.action_words, s.lines, s.requested)
        if s.requested and need > s.requested + 1e-6:
            issues.append({"sev": "corregido", "scene": i, "msg": f"Escena {i}: el diálogo necesita {need:.1f}s y se había pedido {s.requested:.0f}s; ampliada a {sec:.0f}s."})
        if sec > max_seconds:
            issues.append({"sev": "aviso", "scene": i, "msg": f"Escena {i} dura {sec:.0f}s y el modelo entrenado llega a {max_seconds}s por pasada; se dividirá en varios vídeos (la continuidad depende de los segmentos)."})
        if not s.action_text and not s.lines:
            issues.append({"sev": "aviso", "scene": i, "msg": f"Escena {i} sin acción ni diálogo."})
        if not s.place and doc.fmt == "screenplay":
            issues.append({"sev": "aviso", "scene": i, "msg": f"Escena {i} sin localización en el encabezado."})
    for c in res["reading"]["characters"]:
        if c["name"] not in known_looks:
            issues.append({"sev": "info", "scene": c["firstScene"], "msg": f"{c['name']} no tiene aspecto aprendido del corpus; se describirá solo con texto (usa `studio name`)."})
    for t in res["threads"]:
        issues.append({"sev": "trama", "scene": None, "msg": f"Hilo abierto — {t['kind']}: {t['subject']} ({'; '.join(t.get('evidence', [])[:1])})."})
    return issues


def report_es(res: Dict, issues: List[dict], compute: Optional[Dict] = None) -> str:
    r, d = res["reading"], res["doc"]
    L = [f"# Informe del guion", "", f"Lectura: **{res['source']}**. Formato detectado: **{d.fmt}**.", "",
         f"- Escenas: {r['stats']['scenes']} · personajes que hablan: {r['stats']['speakers']} · duración estimada: {r['stats'].get('seconds', 0):.0f} s", ""]
    L += ["## Personajes", "", "| Personaje | Líneas | Palabras | Escenas | Primera–última |", "|---|---|---|---|---|"]
    L += [f"| {c['name']} | {c['cues']} | {c['words']} | {c['scenes']} | {c['firstScene']}–{c['lastScene']} |" for c in r["characters"]]
    L += ["", "## Arco", "", "| Parte | Escenas | Escena de mayor tensión |", "|---|---|---|"]
    L += [f"| {a['part']} | {a['scenes'][0]}–{a['scenes'][1]} | {a.get('peakScene') or '—'} |" for a in r["acts"]]
    L += ["", "## Escenas", "", "| # | Lugar | Hora | Reparto | Tensión | Segundos |", "|---|---|---|---|---|---|"]
    L += [f"| {s['index']} | {s['place'] or '—'} | {s['time'] or '—'} | {', '.join(s['cast']) or '—'} | {s['tension'] if s['tension'] is not None else '—'} | {s.get('seconds', '—')} |" for s in r["scenes"]]
    L += ["", "## Problemas y correcciones", ""]
    L += [f"- **{i['sev']}** · {i['msg']}" for i in issues] or ["- Ninguno."]
    if res["notes"]:
        L += ["", "## Notas", ""] + [f"- {n}" for n in res["notes"]]
    if compute:
        L += ["", "## Cómputo", "", compute["summary_es"]]
    return "\n".join(L) + "\n"
