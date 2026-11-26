"""Training-free denoising-step cache (TeaCache-style, ali-vilab/TeaCache): when the first block's modulated input barely
changed since the previous step, skip all transformer blocks and reuse the last residual (output - input) instead.

Opt-in: `eval.step_cache_threshold > 0` (default 0 = off, bit-identical behaviour). One residual is kept per CFG stream
(unconditional / conditional alternate every step). The first `warmup` and the last call of each stream always compute.
Without model-specific rescaling coefficients (TeaCache fits a polynomial per model) the threshold is in raw relative-L1
units: start low (0.02-0.1) and compare against a normal run on a short clip. Pure Python/duck-typed: works on torch and numpy.
NOT validated on GPU here."""
from typing import List, Optional, Sequence


class StepCache:
    def __init__(self, threshold: float, streams: int = 2, warmup: int = 1, coeffs: Optional[Sequence[float]] = None):
        self.threshold, self.streams, self.warmup, self.coeffs = float(threshold), streams, warmup, coeffs
        self.reset()

    @property
    def enabled(self) -> bool:
        return self.threshold > 0.0

    def reset(self, total_calls: Optional[int] = None) -> None:
        self.total = None if total_calls is None else max(1, total_calls // self.streams)  # calls per stream
        self.count = 0
        self.calls: List[int] = [0] * self.streams
        self.prev: List = [None] * self.streams
        self.acc: List[float] = [0.0] * self.streams
        self.res: List = [None] * self.streams
        self.skipped = 0
        self.computed = 0

    def begin_call(self) -> int:
        s = self.count % self.streams
        self.count += 1
        return s

    def _rescale(self, x: float) -> float:
        if not self.coeffs:
            return x
        y = 0.0
        for c in self.coeffs:  # numpy.poly1d order: highest degree first
            y = y * x + c
        return max(y, 0.0)

    def decide(self, stream: int, probe) -> bool:
        """True = skip the blocks and reuse the residual of this stream."""
        step = self.calls[stream]
        self.calls[stream] += 1
        prev, self.prev[stream] = self.prev[stream], probe
        last = self.total is not None and step >= self.total - 1
        if step < self.warmup or last or prev is None or self.res[stream] is None:
            self.acc[stream] = 0.0
            self.computed += 1
            return False
        rel = float(abs(probe - prev).mean() / (abs(prev).mean() + 1e-8))
        self.acc[stream] += self._rescale(rel)
        if self.acc[stream] < self.threshold:
            self.skipped += 1
            return True
        self.acc[stream] = 0.0
        self.computed += 1
        return False

    def store(self, stream: int, residual) -> None:
        self.res[stream] = residual

    def residual(self, stream: int):
        return self.res[stream]

    def stats(self) -> dict:
        n = self.skipped + self.computed
        return {"skipped": self.skipped, "computed": self.computed, "skip_rate": self.skipped / n if n else 0.0}
