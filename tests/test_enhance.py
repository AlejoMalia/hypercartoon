import pytest

torch = pytest.importorskip("torch")
from hypercartoon.models.cogvideo.enhance import cross_frame_intensity, enhance_scale  # noqa: E402

B, H, F, S, D = 1, 2, 5, 7, 8


def _qk(same_across_frames: bool, scale: float = 1.0):
    torch.manual_seed(0)
    base = torch.randn(B, H, S, D)
    if same_across_frames:  # every frame has the same content -> temporal attention is uniform
        q = base.unsqueeze(2).expand(B, H, F, S, D).reshape(B, H, F * S, D) * 0 + 1.0
        k = q.clone()
        return q, k
    q = torch.randn(B, H, F * S, D)
    return q * scale, q * scale


def test_uniform_temporal_attention_gives_one_plus_weight_over_frames():
    q, k = _qk(True)
    w = 2.0
    assert cross_frame_intensity(q, k, F).item() == pytest.approx(1.0 / F, rel=1e-5)
    assert enhance_scale(q, k, F, w).item() == pytest.approx(1 + w / F, rel=1e-5)


def test_diagonal_dominant_attention_is_never_attenuated():
    # huge, frame-distinct vectors: each frame attends only to itself -> CFI ~ 0 -> clamped to 1
    q = torch.zeros(B, H, F * S, D)
    for f in range(F):
        q[:, :, f * S : (f + 1) * S, f % D] = 60.0
    s = enhance_scale(q, q.clone(), F, 3.0)
    assert s.item() == pytest.approx(1.0) and s.item() >= 1.0


def test_off_switch_short_clips_and_monotonic_weight():
    q, k = _qk(True)
    assert enhance_scale(q, k, F, 0.0).item() == 1.0 and enhance_scale(q, k, 1, 2.0).item() == 1.0
    vals = [enhance_scale(q, k, F, w).item() for w in (0.5, 1.0, 2.0, 3.5)]
    assert vals == sorted(vals) and vals[0] > 1.0


def test_bad_token_count_is_explicit_and_scaling_applies_to_the_attention_output():
    q, k = _qk(False)
    with pytest.raises(ValueError):
        cross_frame_intensity(q[:, :, :-1], k[:, :, :-1], F)
    v = torch.randn(B, H, F * S, D)
    base = torch.nn.functional.scaled_dot_product_attention(q, k, v)
    out = base * enhance_scale(q, k, F, 2.0)
    assert out.shape == base.shape and torch.all(out.abs() >= base.abs() - 1e-6)
