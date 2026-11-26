import pytest

torch = pytest.importorskip("torch")
from hypercartoon.models.cogvideo import ttt_short as TS  # noqa: E402


def _setup(target_shift=1.0):
    torch.manual_seed(0)
    w = torch.nn.Parameter(torch.zeros(4))
    x = torch.randn(32, 4)
    y_true = x @ torch.full((4,), target_shift)
    return w, x, y_true


def test_improving_run_is_accepted_and_keeps_the_best_parameters():
    w, x, y = _setup()
    loss = lambda: ((x @ w - y) ** 2).mean()
    metric = lambda: float(((x @ w - y) ** 2).mean())            # the A/B metric agrees with the loss
    r = TS.short_ttt([w], loss, metric, steps=40, lr=0.05, eval_every=4, patience=3, min_gain=0.05)
    assert r.accepted and r.final < r.baseline * 0.8 and r.best <= r.final + 1e-9 and w.abs().sum() > 0


def test_harmful_run_is_reverted_to_the_original_parameters():
    w, x, y = _setup()
    original = w.detach().clone()
    loss = lambda: ((x @ w - y) ** 2).mean()
    worse = lambda: float(((w - original) ** 2).sum()) + 1.0                                # the held-out quality gets worse as the weights move
    r = TS.short_ttt([w], loss, worse, steps=30, lr=0.05, eval_every=2, patience=2, min_gain=0.02, max_regression=0.05)
    assert not r.accepted and r.stopped_early and torch.equal(w.detach(), original)       # nothing of the experiment survives
    assert r.final == pytest.approx(r.baseline) and ("empeora" in r.reason or "sin mejora" in r.reason)


def test_flat_metric_is_not_accepted_and_patience_stops_early():
    w, x, y = _setup()
    original = w.detach().clone()
    r = TS.short_ttt([w], lambda: ((x @ w - y) ** 2).mean(), lambda: 1.0, steps=50, lr=0.05, eval_every=2, patience=2)
    assert not r.accepted and r.stopped_early and r.steps_run == 4 and torch.equal(w.detach(), original)


def test_param_selection_by_name():
    class M(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.layers = torch.nn.ModuleList([torch.nn.Module()])
            self.layers[0].seq_modeling_block = torch.nn.Module()
            for n in "qkvo":
                setattr(self.layers[0].seq_modeling_block, n, torch.nn.Linear(2, 2))
            self.layers[0].seq_modeling_block.ssm = torch.nn.Module()
            self.layers[0].seq_modeling_block.ssm.hyper = torch.nn.Linear(2, 2)
            self.other = torch.nn.Linear(2, 2)

    m = M()
    assert len(TS.select_params(m, "hyper")) == 2 and len(TS.select_params(m, "spatial_attention")) == 8
    with pytest.raises(ValueError):
        TS.select_params(m, "nope")
