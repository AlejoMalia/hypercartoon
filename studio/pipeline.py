"""Phase engine shared by the terminal panel, the CLI and the tests. A pipeline is an ordered list of phases; each phase
gets a context dict and a progress callback `progress(fraction, detail)`. A phase may raise Skip(reason) (optional
dependency missing, nothing to do) or return a note; errors in non-essential phases are recorded and the run continues."""
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional


class Skip(Exception):
    pass


@dataclass
class Phase:
    key: str
    title: str                 # shown to the user (Spanish)
    weight: float              # relative share of the total work, for the overall percentage / ETA
    fn: Callable               # fn(ctx, progress) -> optional note (str)
    essential: bool = False    # an error here stops the run


@dataclass
class Outcome:
    key: str
    title: str
    status: str                # ok | partial | skipped | error
    seconds: float
    note: str = ""


class Reporter:
    """No-op base; the panel and the plain-text reporters override these."""

    def begin(self, phases: List[Phase]): ...
    def phase_start(self, i: int): ...
    def progress(self, i: int, frac: float, detail: str = ""): ...
    def phase_end(self, i: int, out: Outcome): ...
    def finish(self, outcomes: List[Outcome], seconds: float): ...


def run(phases: List[Phase], ctx: dict, reporter: Optional[Reporter] = None) -> List[Outcome]:
    rep = reporter or Reporter()
    rep.begin(phases)
    t_all, outs = time.time(), []
    ctx["_outcomes"] = outs  # phases (e.g. the kit writer) can see what ran before them
    for i, ph in enumerate(phases):
        rep.phase_start(i)
        t0, status, note = time.time(), "ok", ""
        try:
            r = ph.fn(ctx, lambda frac, detail="", _i=i: rep.progress(_i, max(0.0, min(1.0, frac)), detail))
            note = r or ""
            if note.startswith("parcial:"):
                status = "partial"
        except Skip as e:
            status, note = "skipped", str(e)
        except (Exception, SystemExit) as e:  # keep going: one broken optional phase must not lose the rest of the learning
            status, note = "error", f"{type(e).__name__}: {e}"
        out = Outcome(ph.key, ph.title, status, time.time() - t0, note)
        outs.append(out)
        rep.progress(i, 1.0, "")
        rep.phase_end(i, out)
        if status == "error" and ph.essential:
            break
    rep.finish(outs, time.time() - t_all)
    return outs
