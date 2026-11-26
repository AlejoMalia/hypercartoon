"""EXPERIMENTAL, off by default: a few test-time optimisation steps on the refined video itself, accepted only if an A/B says it helped.

The Hyper layers already run an inner test-time-training loop during inference; this is an OUTER fine-tune of a few parameters (Hyper layers or
spatial-attention projections) on the model's own output. Self-training can amplify the model's artefacts, so the procedure is guarded:
  * a baseline metric (lower is better: e.g. temporal flow residual + seam visibility on a held-out clip) is measured BEFORE;
  * the metric is re-measured every `eval_every` steps; the run stops early when it has not improved for `patience` evaluations or is worse than
    the baseline by more than `max_regression`;
  * the best parameters seen are restored; if the best does not beat the baseline by `min_gain`, the ORIGINAL parameters are restored and
    `accepted` is False. So a bad run costs time, never quality.
Pure torch; the model enters through `loss_fn` / `eval_fn`. Verified on CPU with toy models only."""
import re
from dataclasses import dataclass, field
from typing import Callable, Iterable, List, Sequence

import torch

HYPER_PATTERNS = (r"hyper", r"ssm")                                   # the Hyper (test-time-training) layers
SPATIAL_ATTN_PATTERNS = (r"seq_modeling_block\.(q|k|v|o)\.",)           # q/k/v/o projections of the chunked attention


def select_params(model: torch.nn.Module, kind: str = "hyper") -> List[torch.nn.Parameter]:
    pats = {"hyper": HYPER_PATTERNS, "spatial_attention": SPATIAL_ATTN_PATTERNS}.get(kind)
    if pats is None:
        raise ValueError("kind: hyper | spatial_attention")
    out = [p for n, p in model.named_parameters() if any(re.search(x, n) for x in pats)]
    if not out:
        raise ValueError(f"ningún parámetro coincide con '{kind}'")
    return out


@dataclass
class ShortTTTResult:
    accepted: bool
    baseline: float
    final: float
    best: float
    steps_run: int
    stopped_early: bool
    reason: str
    history: List[float] = field(default_factory=list)


def short_ttt(params: Sequence[torch.nn.Parameter], loss_fn: Callable[[], torch.Tensor], eval_fn: Callable[[], float], steps: int = 8, lr: float = 1e-5,
              eval_every: int = 2, patience: int = 2, min_gain: float = 0.02, max_regression: float = 0.05) -> ShortTTTResult:
    """loss_fn(): self-supervised loss to minimise (builds its own graph). eval_fn(): quality metric, LOWER is better."""
    params = list(params)
    original = [p.detach().clone() for p in params]
    baseline = float(eval_fn())
    best, best_snap, bad, history = baseline, original, 0, []
    opt = torch.optim.Adam(params, lr=lr)
    steps_run, stopped, reason = 0, False, "completado"
    for step in range(steps):
        opt.zero_grad()
        loss_fn().backward()
        opt.step()
        steps_run = step + 1
        if steps_run % eval_every == 0 or steps_run == steps:
            m = float(eval_fn())
            history.append(m)
            if m < best - 1e-12:
                best, best_snap, bad = m, [p.detach().clone() for p in params], 0
            else:
                bad += 1
            if m > baseline * (1 + max_regression):
                stopped, reason = True, f"empeora respecto a la línea base ({m:.4f} > {baseline * (1 + max_regression):.4f})"
                break
            if bad >= patience:
                stopped, reason = True, f"sin mejora durante {patience} evaluaciones"
                break
    accepted = best < baseline * (1 - min_gain)
    with torch.no_grad():
        for p, s in zip(params, best_snap if accepted else original):
            p.copy_(s)                                                      # best seen if it helped, the original otherwise
    final = float(eval_fn())
    return ShortTTTResult(accepted, baseline, final, best, steps_run, stopped, reason if not accepted or stopped else "mejora aceptada", history)
