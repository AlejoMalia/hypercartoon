import sys
import types

import pytest

from hypercartoon.infra import state_load as SL


# ---- tolerant checkpoint loading (pure python) ---------------------------------------------------------------------
def _fake(keys_in_ckpt, wrapped):
    def get():
        return {"dit.layers.0.w": 1, "dit.control.frame.mlp.0.weight": 0, "dit.control.frame.mlp.2.weight": 0}

    def load(holder, path):
        target = holder["model"] if wrapped and "model" in holder else holder
        for k in list(target):
            if k not in keys_in_ckpt:
                raise RuntimeError(f"Missing key in checkpoint state_dict: {k}")
            target[k] = 42  # loaded value
    return get, load


def test_old_checkpoint_without_control_keys_loads_and_keeps_zero_adapters():
    get, load = _fake({"dit.layers.0.w"}, wrapped=True)
    out = SL.load_model_state(get, load, "p", "model")
    assert out["dit.layers.0.w"] == 42 and out["dit.control.frame.mlp.0.weight"] == 0 and len(out) == 3


def test_new_checkpoint_with_control_keys_loads_everything():
    keys = {"dit.layers.0.w", "dit.control.frame.mlp.0.weight", "dit.control.frame.mlp.2.weight"}
    get, load = _fake(keys, wrapped=False)
    out = SL.load_model_state(get, load, "p", "model")
    assert all(v == 42 for v in out.values())


def test_genuinely_missing_base_key_still_fails():
    get, load = _fake(set(), wrapped=True)
    with pytest.raises(RuntimeError):
        SL.load_model_state(get, load, "p", "model")
    assert SL.is_control_key("dit.control.x") and not SL.is_control_key("dit.controller.x") and not SL.is_control_key("dit.layers.0")


# ---- init keeps the adapters at zero (needs torch) ------------------------------------------------------------------
def test_init_does_not_randomise_the_adapters():
    torch = pytest.importorskip("torch")
    from hypercartoon.infra.init_params import init_parameters
    from hypercartoon.models.cogvideo.conditioning import ControlBase, ControlStack

    class FakeHyper(torch.nn.Module):
        pass

    class Toy(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.base = torch.nn.Linear(8, 8)
            self.control = ControlStack(8, max_characters=2, feat_dim=2, frame_dim=3)

    with torch.device("meta"):
        m = Toy()
    m.to_empty(device="cpu")
    init_parameters(m, FakeHyper, ControlBase)
    assert m.base.weight.abs().sum() > 0 and m.base.bias.abs().sum() == 0   # ordinary layers: as before
    for name, p in m.control.named_parameters():
        if name.endswith(("2.weight", "2.bias", "id_embed.weight")):
            assert p.abs().sum() == 0, name                                  # output layers / identity table stay exactly zero
    x = torch.randn(1, 6, 8)
    assert torch.equal(m.control(x, {"frame_feats": torch.randn(1, 3, 3)}), x)  # => the base model is unchanged
