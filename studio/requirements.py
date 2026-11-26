"""How much material is enough? Measures what a learned project actually contains and compares it with the amount each
capability needs, with a verdict per capability and the minutes still missing.

Thresholds are engineering heuristics, NOT measured optima. Anchors:
 * the original TTT-Video trained on about 7 hours of Tom and Jerry annotated in 3-second segments (paper, arXiv 2504.05298),
   which is the reference scale for the video stages ("óptimo" for the stage checks);
 * the planner refuses a stage with fewer than 32 clips (studio/profile.py MIN_CLIPS_PER_STAGE);
 * zero-shot voice cloning models quote 3-5 s of clean reference (Chatterbox ~5 s, Qwen3 voice model ~3 s, per web sources);
 * statistics (pacing profile) use a bootstrap confidence interval, so they scale with how variable the show really is.
Verdicts: insuficiente < mínimo < bueno < óptimo."""
import json
import os
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

import numpy as np

from studio.ingest import load_manifest

REFERENCE_SECONDS = 7 * 3600           # ≈ original training set
MIN_CLIPS_PER_STAGE = 32
LEVELS = ["insuficiente", "mínimo", "bueno", "óptimo"]


@dataclass
class Check:
    key: str
    title: str
    have: float
    unit: str
    minimum: float
    good: float
    optimal: float
    why: str
    higher_is_better: bool = True
    essential: bool = False
    verdict: str = ""
    missing: str = ""

    def judge(self, to_minutes=None) -> "Check":
        h, t = self.have, (self.minimum, self.good, self.optimal)
        ok = (lambda x: h >= x) if self.higher_is_better else (lambda x: h <= x)
        self.verdict = LEVELS[sum(ok(x) for x in t)]
        k = sum(ok(x) for x in t)
        nxt = t[k] if k < 3 else None
        target = f"para «{LEVELS[k + 1]}» " if nxt is not None else ""
        if nxt is not None and self.higher_is_better:
            gap = nxt - h
            self.missing = f"{target}faltan {gap:.0f} {self.unit}" + (f" (≈ {to_minutes(gap):.0f} min de material)" if to_minutes else "")
        elif nxt is not None:
            self.missing = f"{target}hay que bajar de {h:.1f} a {nxt:.1f} {self.unit} (con más material)"
        return self


def bootstrap_halfwidth(x: np.ndarray, stat=np.median, n: int = 400, seed: int = 0) -> float:
    """Relative half-width of the 95 % bootstrap interval of a statistic (0.1 = ±10 %)."""
    if len(x) < 5:
        return 1.0
    rng = np.random.default_rng(seed)
    s = np.array([stat(rng.choice(x, len(x))) for _ in range(n)])
    lo, hi = np.percentile(s, [2.5, 97.5])
    return float((hi - lo) / 2 / (abs(stat(x)) + 1e-9))


def _load(ws, name):
    p = os.path.join(ws, name)
    return json.load(open(p)) if os.path.exists(p) else None


def measure(ws: str) -> List[Check]:
    vids = load_manifest(os.path.join(ws, "manifest.json"))
    prof, plan = _load(ws, "profile.json") or {}, _load(ws, "plan.json") or {}
    corpus, cand = _load(ws, "corpus.json") or {}, _load(ws, "audio_candidates.json") or {}
    bank = _load(ws, "bank/manifest.json") or {"voices": {}, "ambience": []}
    reg = _load(ws, "registry.json")
    mouth, emo = _load(ws, "mouth_style.json"), _load(ws, "emotion_profile.json") or {}
    total = float(sum(v.duration for v in vids.values()))
    n_ep = sum(len(e) for s in corpus.values() for e in s.values())
    checks: List[Check] = []
    add = lambda c: checks.append(c)

    add(Check("total", "Duración total del material", total / 60, "min", 20, 120, REFERENCE_SECONDS / 60,
              "el original entrenó con ≈7 h; por debajo de ~20 min no hay clips para ninguna etapa larga", essential=True))
    add(Check("episodes", "Episodios", n_ep, "episodios", 2, 10, 26,
              "hacen falta ≥2 episodios para reconocer a un personaje entre episodios; más para separar identidad de escena"))
    shots = np.array([s.end - s.start for v in vids.values() for s in v.shots]) if vids else np.array([])
    add(Check("shots", "Planos analizados", len(shots), "planos", 30, 150, 500, "base estadística del ritmo y del estilo"))
    if len(shots):
        add(Check("pace_ci", "Precisión del ritmo (±IC95 de la duración mediana de plano)", bootstrap_halfwidth(shots) * 100, "%",
                  25, 12, 6, "intervalo bootstrap: depende de lo variable que sea la serie", higher_is_better=False, essential=True))

    for st in plan.get("stages", []):
        s = st["seconds"]
        ref = REFERENCE_SECONDS / s
        add(Check(f"stage_{s}", f"Clips para la etapa de {s} s", st["clips"], "clips", MIN_CLIPS_PER_STAGE, 0.25 * ref, ref,
                  f"≥{MIN_CLIPS_PER_STAGE} es el mínimo del planificador; el óptimo es la escala del original (≈7 h en clips de {s} s)",
                  essential=(s == plan["stages"][0]["seconds"])).judge(lambda c, s=s: c * s / 60))
    if plan:
        for s in (3, 9, 18, 30, 63):
            if s not in [x["seconds"] for x in plan.get("stages", [])]:
                clips = int(sum(v.duration // s for v in vids.values()))
                add(Check(f"stage_{s}", f"Clips para la etapa de {s} s (no habilitada)", clips, "clips", MIN_CLIPS_PER_STAGE, 0.25 * REFERENCE_SECONDS / s,
                          REFERENCE_SECONDS / s, "sin ≥32 clips esta etapa no se entrena", ).judge(lambda c, s=s: c * s / 60))

    speech_s = sum((cand.get("sound", {}).get(p) or {}).get("speech", 0.0) * v.duration for p, v in vids.items())
    add(Check("speech", "Diálogo hablado total", speech_s / 60, "min", 5, 30, 120, "alimenta voces, emoción de voz, boca e historia"))
    if reg is not None:
        r = Registry_chars(ws)
        add(Check("characters", "Personajes reconocidos con ≥30 s en pantalla", sum(c["seconds_on_screen"] >= 30 for c in r), "personajes", 1, 3, 6,
                  "necesita la parte visual instalada ([perception]) y varios episodios"))
        if r:
            add(Check("char_min", "Personaje menos visto (segundos en pantalla)", min(c["seconds_on_screen"] for c in r), "s", 30, 120, 600,
                      "identidad estable en el reparto"))
    secs = {vid: sum(c["end"] - c["start"] for c in lst) for vid, lst in bank["voices"].items()}
    add(Check("voices", "Voces con referencia limpia", len(secs), "voces", 1, 3, 6, "una por personaje que hable"))
    if secs:
        add(Check("voice_ref", "Referencia limpia de la voz con menos audio", min(secs.values()), "s", 5, 15, 30,
                  "clonar una voz funciona con 3-5 s, pero 15-30 s de varias escenas generaliza mejor"))
    if emo:
        add(Check("emo_base", "Segmentos por voz para la línea base de emoción", min(b["n"] for b in emo.values()), "segmentos", 5, 30, 100,
                  "la emoción de la voz se mide contra el estilo habitual del personaje"))
    add(Check("mouth", "Fotogramas con habla para la convención de boca", (mouth or {}).get("n_samples", 0), "fotogramas", 300, 3000, 15000,
              "fija cada cuántos fotogramas cambia la boca, sus aperturas y el adelanto"))
    add(Check("ambience", "Ambientes de sonido", len(bank["ambience"]), "ambientes", 1, 3, 6, "cama sonora para mezclar bajo el diálogo"))
    return [c if c.verdict else c.judge() for c in checks]


def Registry_chars(ws: str):
    from studio.characters import Registry

    return Registry.load(os.path.join(ws, "registry.json")).characters(min_presence=0.0)


def summarize(checks: List[Check]) -> Dict:
    ess = [c for c in checks if c.essential] or checks
    worst = min(ess, key=lambda c: LEVELS.index(c.verdict))
    counts = {l: sum(c.verdict == l for c in checks) for l in LEVELS}
    return {"overall": worst.verdict, "limiting": worst.title, "counts": counts}


def report_es(checks: List[Check]) -> str:
    sm = summarize(checks)
    L = ["# Suficiencia del material", "",
         f"**Veredicto global: {sm['overall'].upper()}** (lo limita: {sm['limiting']}).", "",
         "Los umbrales son heurísticas de ingeniería ancladas en el entrenamiento original (≈7 h de dibujos en segmentos de 3 s) y en lo "
         "que citan los modelos de clonación de voz; no son óptimos medidos.", "",
         "| Capacidad | Tienes | Mínimo | Bueno | Óptimo | Veredicto | Qué falta |", "|---|---|---|---|---|---|---|"]
    f = lambda x: f"{x:.0f}" if abs(x - round(x)) < 1e-9 or abs(x) >= 10 else f"{x:.1f}"
    L += [f"| {c.title} | {f(c.have)} {c.unit} | {f(c.minimum)} | {f(c.good)} | {f(c.optimal)} | {c.verdict} | {c.missing or '—'} |" for c in checks]
    return "\n".join(L) + "\n"


def run(ws: str, write: bool = True) -> Dict:
    checks = measure(ws)
    out = {"summary": summarize(checks), "checks": [asdict(c) for c in checks]}
    if write:
        json.dump(out, open(os.path.join(ws, "requirements.json"), "w"), indent=1, ensure_ascii=False)
        open(os.path.join(ws, "REQUISITOS.md"), "w", encoding="utf-8").write(report_es(checks))
    return out
