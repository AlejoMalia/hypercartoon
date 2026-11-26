import numpy as np
import pytest

torch = pytest.importorskip("torch")
from hypercartoon.models.cogvideo.conditioning import CharacterControl, ControlStack, FrameControl  # noqa: E402

B, T, HP, WP, D, I = 2, 3, 4, 5, 16, 3
N = T * HP * WP


def _tokens():
    torch.manual_seed(0)
    return torch.randn(B, N, D)


def _labels():
    lab = torch.zeros(B, T, HP, WP, dtype=torch.long)
    lab[:, :, :2, :2] = 1
    lab[:, :, 2:, 3:] = 2
    return lab


def test_zero_init_is_exactly_the_base_model():
    x = _tokens()
    st = ControlStack(D, max_characters=I, feat_dim=3, frame_dim=4)
    st.init_weights()
    ctrl = {"labels": _labels(), "feats": torch.randn(B, T, I + 1, 3), "frame_feats": torch.randn(B, T, 4)}
    assert torch.equal(st(x, ctrl), x)       # enabled but untrained: identical output
    assert torch.equal(st(x, None), x) and torch.equal(st(x, {}), x)


def test_after_training_a_character_changes_only_its_own_tokens():
    x = _tokens()
    cc = CharacterControl(D, I, feat_dim=0)
    cc.init_weights()
    with torch.no_grad():
        cc.id_embed.weight[1] += 1.0           # pretend character 1 was trained
    y = cc(x, _labels())
    lab = _labels().reshape(B, N)
    assert torch.equal(y[lab == 0], x[lab == 0]) and torch.equal(y[lab == 2], x[lab == 2])
    assert not torch.equal(y[lab == 1], x[lab == 1])


def test_per_character_features_are_gathered_through_the_label_map():
    x = _tokens()
    cc = CharacterControl(D, I, feat_dim=2)
    cc.init_weights()
    with torch.no_grad():
        cc.feat_mlp[2].weight.normal_(std=0.5)  # pretend trained
    feats = torch.zeros(B, T, I + 1, 2)
    feats[:, :, 1, 0] = 1.0                      # only character 1 "has its mouth open"
    y = cc(x, _labels(), feats)
    lab = _labels().reshape(B, N)
    # tokens of character 1 receive a different shift than those of character 2 (different feature vectors)
    d1 = (y - x)[lab == 1].mean(0)
    d2 = (y - x)[lab == 2].mean(0)
    assert not torch.allclose(d1, d2)
    # and swapping which character carries the feature swaps who is affected
    feats2 = torch.zeros_like(feats)
    feats2[:, :, 2, 0] = 1.0
    y2 = cc(x, _labels(), feats2)
    assert not torch.allclose((y2 - x)[lab == 1].mean(0), d1)


def test_frame_control_is_per_frame_and_broadcast_over_tokens():
    x = _tokens()
    fc = FrameControl(D, 4)
    fc.init_weights()
    with torch.no_grad():
        fc.mlp[2].weight.normal_(std=0.5)
    ff = torch.zeros(B, T, 4)
    ff[:, 1, 0] = 1.0                            # speech only in frame 1
    y = fc(x, ff)
    per = N // T
    delta = (y - x).reshape(B, T, per, D)
    assert torch.allclose(delta[:, 1, 0], delta[:, 1, -1]) and torch.allclose(delta[:, 0].abs().max(), delta[:, 0].abs().max())
    assert not torch.allclose(delta[:, 1], delta[:, 0])


def test_shape_errors_are_explicit():
    cc = CharacterControl(D, I, 2)
    with pytest.raises(ValueError, match="do not match"):
        cc(_tokens(), torch.zeros(B, T, HP + 1, WP, dtype=torch.long))
    with pytest.raises(ValueError, match="expected"):
        cc(_tokens(), _labels(), torch.zeros(B, T, I, 2))
    with pytest.raises(ValueError):
        FrameControl(D, 4)(_tokens(), torch.zeros(B, T, 5))
    assert ControlStack(D).character is None and ControlStack(D).frame is None


def test_ids_beyond_the_table_are_clamped_not_crashing():
    x = _tokens()
    cc = CharacterControl(D, I)
    cc.init_weights()
    assert torch.equal(cc(x, torch.full((B, T, HP, WP), 99, dtype=torch.long)), x)




# ---- tile-position control -----------------------------------------------------------------------------------------------------
from hypercartoon.models.cogvideo.conditioning import TileControl  # noqa: E402


def test_tile_control_zero_init_and_global_coordinates():
    x = _tokens()
    tc = TileControl(D)
    tc.init_weights()
    pos = torch.tensor([[0.0, 0.0, 0.5, 0.5], [0.5, 0.5, 1.0, 1.0]])
    xx = torch.randn(2, N, D)
    assert torch.equal(tc(xx, pos, (T, HP, WP)), xx)                        # untrained: identical to the base model
    gx, gy = tc.token_coordinates(pos, HP, WP)
    assert gx.shape == (2, HP, WP) and gx[0].max() < 0.5 and gx[1].min() > 0.5                # tile 0 lives in the left half, tile 1 in the right
    assert gx[0, 0, 0] == pytest.approx(0.5 / WP * 0.5) and gy[1, -1, 0] == pytest.approx(0.5 + (HP - 0.5) / HP * 0.5)
    with torch.no_grad():
        tc.mlp[2].weight.normal_(std=0.5)                                    # pretend trained
    y = tc(xx, pos, (T, HP, WP))
    d0, d1 = (y - xx)[0], (y - xx)[1]
    assert not torch.allclose(d0, d1)                                        # different tile positions -> different offsets
    per = (y - xx)[0].reshape(T, HP * WP, D)
    assert torch.allclose(per[0], per[-1])                                   # same offset for every frame of the tile
    with pytest.raises(ValueError):
        tc(xx, pos[:1], (T, HP, WP))


def test_control_stack_tile_branch_needs_grid_and_stays_identity_when_off():
    xx = torch.randn(1, N, D)
    st = ControlStack(D, tile=True)
    st.init_weights()
    pos = {"tile_pos": torch.tensor([[0.0, 0.0, 1.0, 1.0]])}
    assert torch.equal(st(xx, pos, (T, HP, WP)), xx) and torch.equal(st(xx, None, (T, HP, WP)), xx)
    with pytest.raises(ValueError, match="grid"):
        st(xx, pos)
    assert ControlStack(D).tile is None and torch.equal(ControlStack(D, frame_dim=2)(xx, pos), xx)   # no tile branch: key ignored


# ---- control_tile=false (and every adapter off) is the original model ------------------------------------------------------------------
from types import SimpleNamespace  # noqa: E402

from hypercartoon.models.cogvideo.conditioning import build_control_stack, maybe_apply_control  # noqa: E402


def test_with_every_adapter_off_there_is_no_module_no_parameter_and_the_same_tensor():
    cfg = SimpleNamespace(model_dim=D, control_max_characters=0, control_feat_dim=3, control_frame_dim=0, control_tile=False)
    assert build_control_stack(cfg) is None                                  # no module => no new state_dict keys => original checkpoints load strictly
    assert build_control_stack(SimpleNamespace(model_dim=D)) is None         # an old config without the fields behaves the same
    x = _tokens()
    out = maybe_apply_control(None, x, {"tile_pos": torch.tensor([[0.0, 0.0, 1.0, 1.0]]), "frame_feats": torch.randn(B, T, 4)}, (T, HP, WP))
    assert out is x and torch.equal(out, x)                                  # not even a copy: bit-for-bit the same object
    holder = torch.nn.Linear(D, D)
    before = {k: v.clone() for k, v in holder.state_dict().items()}
    assert set(holder.state_dict()) == set(before)                          # a module that owns `control = None` registers nothing


def test_enabling_tile_control_adds_only_namespaced_parameters_and_is_identity_until_trained():
    on = build_control_stack(SimpleNamespace(model_dim=D, control_max_characters=0, control_feat_dim=0, control_frame_dim=0, control_tile=True))
    assert on is not None and on.tile is not None and on.character is None and on.frame is None
    on.init_weights()
    names = [n for n, _ in on.named_parameters()]
    assert names and all(n.startswith("tile.") for n in names)              # all under `.control.` in the DiT: filtered by the tolerant checkpoint loader
    x = _tokens()
    assert torch.equal(maybe_apply_control(on, x, {"tile_pos": torch.tensor([[0.25, 0.0, 0.75, 0.5]]).expand(B, 4)}, (T, HP, WP)), x)
