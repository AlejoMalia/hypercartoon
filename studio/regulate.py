"""Self-regulation: generate, score coherence, retry with a controlled escalation inside a compute budget.
Pure control logic (callbacks), so it is testable without a GPU."""
from dataclasses import dataclass, field
from typing import Any, Callable, List


@dataclass
class Attempt:
    seed: int
    steps: int
    score: float
    result: Any = field(repr=False, default=None)


def regulate(generate: Callable[[int, int], Any], score: Callable[[Any], float], *, target: float = 0.75,
             base_steps: int = 50, max_steps: int = 80, max_attempts: int = 3, seed: int = 0) -> List[Attempt]:
    """Attempt 1 is cheap (base_steps). Retries change the seed; steps only escalate if the score is *close* to the
    target (low-noise problem), otherwise a new seed is the cheaper fix. Stops at target or budget; returns all
    attempts (best = max score) so the caller keeps the best instead of the last."""
    history: List[Attempt] = []
    steps = base_steps
    for i in range(max_attempts):
        s = seed + i
        out = generate(s, steps)
        sc = float(score(out))
        history.append(Attempt(s, steps, sc, out))
        if sc >= target:
            break
        if sc >= 0.9 * target:
            steps = min(max_steps, int(steps * 1.3))
    return history


def best(history: List[Attempt]) -> Attempt:
    return max(history, key=lambda a: -1.0 if a.score != a.score else a.score)
