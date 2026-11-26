"""Terminal version: pick a video or a folder, watch the learning (and creation) phases with time and %, get the project
folder with everything needed to generate an episode.   python -m studio     |     hypercartoon     |     python -m hypercartoon
No dependencies: plain ANSI. Falls back to simple progress lines when stdout is not a terminal."""
import glob
import json
import os
import shutil
import sys
import threading
import time
from typing import List, Optional

from studio import episode as EP
from studio import learning as L
from studio import pipeline as PL
from studio.pipeline import Outcome, Phase

ICON = {"pending": "○", "running": "▶", "ok": "✔", "partial": "◐", "skipped": "⚠", "error": "✖"}
COLOR = {"pending": "2", "running": "36", "ok": "32", "partial": "33", "skipped": "33", "error": "31"}


def fmt_t(s: Optional[float]) -> str:
    if s is None or s != s:
        return "--:--"
    s = int(max(0, s))
    return f"{s // 3600:d}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


def bar(frac: float, width: int = 20) -> str:
    n = int(round(max(0.0, min(1.0, frac)) * width))
    return "█" * n + "░" * (width - n)


class Panel(PL.Reporter):
    """Live panel: one row per phase (state, bar, %, elapsed, ETA, detail) + an overall row with % and ETA."""

    def __init__(self, title: str, out=None, color: Optional[bool] = None, live: Optional[bool] = None):
        self.title, self.out = title, out or sys.stdout
        tty = bool(getattr(self.out, "isatty", lambda: False)())
        self.live = tty if live is None else live
        self.color = tty if color is None else color
        self.lock, self.height, self._stop = threading.Lock(), 0, threading.Event()
        self.phases: List[Phase] = []
        self.state: List[str] = []
        self.frac: List[float] = []
        self.t0: List[Optional[float]] = []
        self.dur: List[float] = []
        self.note: List[str] = []
        self.detail = ""
        self.t_all = 0.0
        self._last_plain = {}

    # -- reporter API
    def begin(self, phases):
        self.phases = phases
        n = len(phases)
        self.state, self.frac, self.t0, self.dur, self.note = ["pending"] * n, [0.0] * n, [None] * n, [0.0] * n, [""] * n
        self.t_all = time.time()
        if self.live:
            self.out.write("\x1b[?25l")
            self._render()
            threading.Thread(target=self._ticker, daemon=True).start()
        else:
            self.out.write(f"{self.title}\n")
            self.out.flush()

    def phase_start(self, i):
        with self.lock:
            self.state[i], self.t0[i], self.detail = "running", time.time(), ""
        self._draw(i, force=True)

    def progress(self, i, frac, detail=""):
        with self.lock:
            self.frac[i] = frac
            if detail:
                self.detail = detail
        self._draw(i)

    def phase_end(self, i, out: Outcome):
        with self.lock:
            self.state[i], self.frac[i], self.dur[i], self.note[i], self.detail = out.status, 1.0, out.seconds, out.note, ""
        self._draw(i, force=True)

    def finish(self, outcomes, seconds):
        self._stop.set()
        if self.live:
            self._render()
            self.out.write("\x1b[?25h")
        self.out.flush()

    # -- rendering
    def overall(self):
        w = sum(p.weight for p in self.phases) or 1.0
        return sum(p.weight * f for p, f in zip(self.phases, self.frac)) / w

    def _paint(self, text, state):
        return f"\x1b[{COLOR[state]}m{text}\x1b[0m" if self.color else text

    def lines(self) -> List[str]:
        width = max(60, min(shutil.get_terminal_size((100, 24)).columns, 120))
        now = time.time()
        L_ = [f"  {self.title}", ""]
        for i, p in enumerate(self.phases):
            st, fr = self.state[i], self.frac[i]
            el = (now - self.t0[i]) if (st == "running" and self.t0[i]) else self.dur[i]
            eta = (el / fr - el) if (st == "running" and fr > 0.05) else None
            tail = {"running": f"ETA {fmt_t(eta)}  {self.detail}", "pending": ""}.get(st, self.note[i])
            row = f"  {self._paint(ICON[st], st)} {i + 1}. {p.title:<40.40} [{bar(fr, 16)}] {fr * 100:3.0f}%  {fmt_t(el if st != 'pending' else None):>5}  {tail}"
            L_.append(row[: width + (len(row) - len(self._strip(row))) if self.color else width])
        ov = self.overall()
        el = now - self.t_all
        eta = (el / ov - el) if ov > 0.03 else None
        L_ += ["", f"  Total [{bar(ov, 30)}] {ov * 100:3.0f}%   transcurrido {fmt_t(el)}   restante {fmt_t(eta)}"]
        return L_

    @staticmethod
    def _strip(s):
        import re

        return re.sub(r"\x1b\[[0-9;]*m", "", s)

    def _render(self):
        with self.lock:
            lines = self.lines()
            if self.height:
                self.out.write(f"\x1b[{self.height}A")
            for ln in lines:
                self.out.write("\x1b[2K" + ln + "\n")
            self.height = len(lines)
            self.out.flush()

    def _ticker(self):
        while not self._stop.wait(0.25):
            self._render()

    def _draw(self, i, force=False):
        if self.live:
            return  # the ticker repaints
        pct = int(self.frac[i] * 100)
        key = (i, pct // 25, self.state[i])
        if force or self._last_plain.get(i) != key:
            self._last_plain[i] = key
            tag = ICON[self.state[i]]
            self.out.write(f"[{self.overall() * 100:3.0f}%] {tag} {i + 1}/{len(self.phases)} {self.phases[i].title}: {pct}%"
                           f"{(' · ' + self.note[i]) if self.state[i] not in ('running', 'pending') and self.note[i] else ''}\n")
            self.out.flush()


# ---- interaction ---------------------------------------------------------------------------------------------
def _enable_path_completion():
    try:
        import readline

        def comp(text, n):
            m = glob.glob(os.path.expanduser(text) + "*")
            m = [x + "/" if os.path.isdir(x) else x for x in sorted(m)]
            return m[n] if n < len(m) else None

        readline.set_completer_delims(" \t\n;")
        readline.set_completer(comp)
        readline.parse_and_bind("bind ^I rl_complete" if "libedit" in (readline.__doc__ or "") else "tab: complete")
    except Exception:
        pass


def ask_path(prompt: str, want: str, inp, out) -> str:
    """want: 'file' | 'dir' | 'any'. Re-asks until the path exists."""
    while True:
        p = os.path.expanduser(inp(prompt).strip().strip("'\"").replace("\\ ", " "))
        if p and ((want == "file" and os.path.isfile(p)) or (want == "dir" and os.path.isdir(p)) or (want == "any" and os.path.exists(p))):
            return os.path.abspath(p)
        out.write("  No encuentro esa ruta. Prueba de nuevo (Tab completa).\n")


def S_split(text: str) -> List[str]:
    import shlex

    try:
        return shlex.split(text)
    except ValueError:
        return text.split()


def box(lines: List[str], out, color: bool):
    cols = max(50, shutil.get_terminal_size((100, 24)).columns - 6)
    lines = [l if len(l) <= cols else l[: cols - 1] + "…" for l in lines]
    w = max(len(l) for l in lines) + 4
    g = "\x1b[32m" if color else ""
    r = "\x1b[0m" if color else ""
    out.write(f"{g}╔{'═' * w}╗{r}\n")
    for l in lines:
        out.write(f"{g}║{r}  {l:<{w - 2}}{g}║{r}\n")
    out.write(f"{g}╚{'═' * w}╝{r}\n")


def run_learning(path, ws: str, out, **opts) -> List[Outcome]:
    os.makedirs(ws, exist_ok=True)
    inputs = [path] if isinstance(path, str) else list(path)
    ctx = {"input": inputs[0], "inputs": inputs, "source_options": opts.get("source_options"), "overlay_mode": opts.get("overlay_mode", "mask"), "text_detector": opts.get("text_detector") or None, "ws": ws, "device": opts.get("device", "cuda"), "gpu_mem_gb": opts.get("gpu_mem_gb", 80.0),
           "workers": opts.get("workers", max(1, (os.cpu_count() or 2) // 2)), "voice": opts.get("voice", "auto"), "vision": True}
    panel = Panel("APRENDIZAJE DEL MATERIAL", out)
    t0 = time.time()
    outs = PL.run(L.LEARNING_PHASES, ctx, panel)
    kit = L.finalize_kit(ctx, outs, time.time() - t0)
    return outs, kit, ctx


def run_episode(ws: str, text: str, ep_dir: str, out, **opts):
    ctx = EP.make_ctx(ws, ep_dir, text, **opts)
    panel = Panel("CREACIÓN DEL EPISODIO", out)
    t0 = time.time()
    outs = PL.run(EP.EPISODE_PHASES, ctx, panel)
    return outs, ctx, time.time() - t0


def main(argv=None, inp=input, out=None) -> int:
    import argparse

    out = out or sys.stdout
    ap = argparse.ArgumentParser(prog="hypercartoon", description="Aprende de un vídeo o carpeta y prepara la creación de episodios")
    ap.add_argument("input", nargs="*", help="vídeo, carpeta, URL (YouTube, lista de reproducción...), lista .txt, magnet/.torrent... (si no, se pregunta)")
    ap.add_argument("--name", default="", help="nombre de la serie para material online")
    ap.add_argument("--proxy-height", type=int, default=480)
    ap.add_argument("--keep", choices=["proxy", "full"], default="proxy")
    ap.add_argument("--max-seconds", type=float, default=0.0)
    ap.add_argument("--max-gb", type=float, default=0.0)
    ap.add_argument("--cookies", default="")
    ap.add_argument("--fetch-workers", type=int, default=4)
    ap.add_argument("--overlay-mode", choices=["mask", "delogo", "crop", "off"], default="mask", help="texto/logos incrustados: mask (por defecto), delogo, crop, off")
    ap.add_argument("--text-detector", choices=["", "easyocr", "paddle"], default="")
    ap.add_argument("--out", help="carpeta del proyecto (por defecto ./hypercartoon_projects/<nombre>)")
    ap.add_argument("--script", help="guion/prompt para crear un episodio al terminar el aprendizaje")
    ap.add_argument("--no-create", action="store_true", help="no preguntar por crear un episodio")
    ap.add_argument("--device", default="cuda")
    a = ap.parse_args(argv if argv is not None else sys.argv[1:])
    tty = bool(getattr(out, "isatty", lambda: False)()) and sys.stdin.isatty()
    color = bool(getattr(out, "isatty", lambda: False)())
    if tty:
        _enable_path_completion()

    out.write("\n  ╭──────────────────────────────────────────╮\n  │  H Y P E R C A R T O O N   ·   estudio   │\n  ╰──────────────────────────────────────────╯\n\n")
    from studio import sources as S

    inputs = list(a.input or [])
    if not inputs:
        out.write("  ¿Qué quieres que aprenda el sistema?\n    1) Un vídeo\n    2) Una carpeta (varios vídeos, temporadas)\n"
                  "    3) En línea: URL, YouTube / lista de reproducción, lista .txt, torrent o magnet\n\n")
        while True:
            c = inp("  Elige 1, 2 o 3: ").strip()
            if c in ("1", "2", "3"):
                break
        if c == "3":
            while not inputs:
                inputs = S_split(inp("  Pega una o varias fuentes (separadas por espacios): "))
        else:
            inputs = [ask_path("  Ruta del vídeo: " if c == "1" else "  Ruta de la carpeta: ", "file" if c == "1" else "dir", inp, out)]
    bad = [i for i in inputs if S.classify(i) == "local" and not os.path.exists(os.path.expanduser(i)) and not any(ch in i for ch in "*?[")]
    if bad:
        out.write(f"  No existe: {bad[0]}\n")
        return 2
    inputs = [os.path.abspath(os.path.expanduser(i)) if S.classify(i) == "local" and os.path.exists(os.path.expanduser(i)) else i for i in inputs]
    path = inputs[0]
    name = S.project_name(inputs)
    ws = os.path.abspath(a.out or os.path.join("hypercartoon_projects", name))
    out.write(f"\n  Material: {', '.join(inputs) if len(inputs) <= 3 else f'{inputs[0]} (+{len(inputs) - 1})'}\n  Proyecto: {ws}\n\n")
    sopts = S.Options(name=a.name, proxy_height=a.proxy_height, keep=a.keep, max_seconds=a.max_seconds, max_gb=a.max_gb, cookies=a.cookies, fetch_workers=a.fetch_workers)

    outs, kit, ctx = run_learning(inputs, ws, out, device=a.device, source_options=sopts, overlay_mode=a.overlay_mode, text_detector=a.text_detector)
    failed = [o for o in outs if o.status == "error"]
    total = sum(o.seconds for o in outs)
    out.write("\n")
    lines = ["PROCESO COMPLETADO" if not failed else "PROCESO TERMINADO CON ERRORES",
             f"Tiempo total: {fmt_t(total)}   ·   fases: {sum(o.status == 'ok' for o in outs)} ok, "
             f"{sum(o.status in ('partial', 'skipped') for o in outs)} parciales/omitidas, {len(failed)} con error",
             f"Paquete del episodio: {kit}", f"Resumen para leer:   {os.path.join(ws, 'LEEME.md')}"]
    req = os.path.join(ws, "requirements.json")
    if os.path.exists(req):
        sm = json.load(open(req))["summary"]
        lines.insert(2, f"Suficiencia del material: {sm['overall'].upper()} (limita: {sm['limiting']})  ·  detalle: REQUISITOS.md")
    box(lines, out, color)
    for o in outs:
        if o.status in ("partial", "skipped", "error") and o.note:
            out.write(f"  {ICON[o.status]} {o.title}: {o.note}\n")
    if failed and failed[0].key in ("scan", "corpus", "profile"):
        return 1

    if a.no_create:
        return 0
    script = a.script
    if script is None:
        script = inp("\n  Para crear un episodio, escribe la ruta de un guion/prompt (Enter para terminar): ").strip().strip("'\"")
    if script:
        script = os.path.expanduser(script)
        if os.path.isfile(script):
            text = open(script, encoding="utf-8").read()
        elif inp("  No es un archivo; ¿uso ese texto como guion? [s/N] ").strip().lower() in ("s", "si", "sí", "y"):
            text = script
        else:
            return 0
        ep_dir = os.path.join(ws, "episodes", f"episodio_{len(glob.glob(os.path.join(ws, 'episodes', 'episodio_*'))) + 1:02d}")
        eouts, ectx, secs = run_episode(ws, text, ep_dir, out)
        out.write("\n")
        ok = not any(o.status == "error" for o in eouts)
        box(["EPISODIO PREPARADO" if ok else "EPISODIO CON ERRORES", f"Tiempo total: {fmt_t(secs)}", f"Carpeta: {ep_dir}",
             "Generación de vídeo: requiere GPU, comandos en episode.json"], out, color)
        for o in eouts:
            if o.status in ("partial", "skipped", "error") and o.note:
                out.write(f"  {ICON[o.status]} {o.title}: {o.note}\n")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
