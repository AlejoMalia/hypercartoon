import math

import pytest

torch = pytest.importorskip("torch")
from hypercartoon.models.cogvideo import refine as R  # noqa: E402

N = 12
# ascending sqrt(alpha_cumprod): noisy -> clean, plus the final 1.0 like the sampler builds it
ALPHAS = [0.04 + 0.95 * (i / (N - 1)) ** 1.3 for i in range(N)] + [1.0]


def _ref(T=3, C=4, H=16, W=24, seed=0):
    g = torch.Generator().manual_seed(seed)
    return torch.randn(T, C, H, W, generator=g)


def _one_tile(H=16, W=24):
    return [[((0, 0, W, H), torch.ones(H, W))]]


def test_start_step_semantics_and_validation():
    assert R.start_step(20, 1.0) == 0 and R.start_step(20, 0.0) == 20 and R.start_step(20, 0.35) == 13
    with pytest.raises(ValueError):
        R.start_step(20, 1.2)


def test_perfect_denoiser_returns_the_clean_latent_exactly_and_strength_zero_is_a_noop():
    ref = _ref()
    truth = ref.clone()
    out = R.refine_latent_tiled(ref, _one_tile(), lambda x, i, rect: truth[..., rect[1]:rect[3], rect[0]:rect[2]], ALPHAS, strength=0.6, lam=0.0,
                                generator=torch.Generator().manual_seed(1))
    assert torch.allclose(out, truth, atol=1e-5)            # last step returns the denoised estimate
    calls = []
    same = R.refine_latent_tiled(ref, _one_tile(), lambda *a: calls.append(1), ALPHAS, strength=0.0)
    assert torch.equal(same, ref) and not calls            # strength 0: stage A untouched, the model is never called


def test_start_noise_level_matches_the_schedule_and_is_reproducible():
    ref = _ref()
    seen = {}

    def den(x, i, rect):
        seen.setdefault("x", x.clone())
        seen.setdefault("i", i)
        return ref
    R.refine_latent_tiled(ref, _one_tile(), den, ALPHAS, strength=0.5, lam=0.0, generator=torch.Generator().manual_seed(7))
    i0 = R.start_step(N, 0.5)
    a = ALPHAS[i0]
    assert seen["i"] == i0
    resid = (seen["x"] - a * ref) / math.sqrt(1 - a * a)          # what was added is unit-variance noise
    assert abs(resid.std().item() - 1.0) < 0.15
    mk = lambda: R.refine_latent_tiled(ref, _one_tile(), lambda x, i, r: x * 0.9, ALPHAS, strength=0.5, generator=torch.Generator().manual_seed(3))
    assert torch.equal(mk(), mk())


def test_low_frequency_projection_keeps_structure_and_lets_detail_through():
    ref = _ref(T=1, C=1, H=32, W=32, seed=2)
    ref = R.lowpass(ref, 8)                                          # a smooth "stage A" latent
    detail = torch.randn(ref.shape, generator=torch.Generator().manual_seed(5)) * 0.5     # what a model would add
    bad_lowfreq = -ref + detail                                      # a prediction whose structure disagrees with stage A
    out = R.project_low_frequency(bad_lowfreq, ref, lam=1.0, factor=4)
    err_before = (R.lowpass(bad_lowfreq, 4) - R.lowpass(ref, 4)).abs().mean()
    err_after = (R.lowpass(out, 4) - R.lowpass(ref, 4)).abs().mean()
    assert err_after < 0.25 * err_before                             # structure pulled back to the reference
    hf = lambda x: (x - R.lowpass(x, 4)).std()
    assert hf(out) > 0.8 * hf(bad_lowfreq)                           # the added fine detail survives
    assert torch.equal(R.project_low_frequency(bad_lowfreq, ref, lam=0.0), bad_lowfreq)


def test_refinement_with_projection_stays_close_to_stage_a_without_it_drifts():
    ref = R.lowpass(_ref(T=2, C=3, H=32, W=48, seed=4), 8)
    wrong = lambda x, i, rect: torch.full_like(x, 2.0)                # a denoiser that disagrees with stage A everywhere
    kw = dict(grids=[[((0, 0, 48, 32), torch.ones(32, 48))]], denoise_tile=wrong, alphas_sqrt=ALPHAS, strength=0.7)
    drift = (R.refine_latent_tiled(ref, generator=torch.Generator().manual_seed(1), lam=0.0, **kw) - ref).abs().mean()
    held = (R.refine_latent_tiled(ref, generator=torch.Generator().manual_seed(1), lam=1.0, **kw) - ref).abs().mean()
    assert held < 0.6 * drift and torch.isfinite(held)


def _grid(H, W, th, tw, alternate):
    def tiles(ps):
        out = []
        for x, y in ps:
            w = torch.ones(th, tw)
            out.append(((x, y, x + tw, y + th), w))
        return out
    A = tiles([(0, 0), (tw, 0), (0, th), (tw, th)])
    ws = {}
    for r, w in A:                                                    # normalised: exact 2x2 -> weights 1 everywhere
        ws[r] = w
    if not alternate:
        return [A]
    B = tiles([(tw // 2, 0), (tw // 2, th), (0, th // 2), (tw, th // 2), (tw // 2, th // 2)])
    tot = torch.zeros(H, W)
    for (x0, y0, x1, y1), w in B:
        tot[y0:y1, x0:x1] += w
    B = [(r, w / tot[r[1]:r[3], r[0]:r[2]]) for r, w in B]
    return [A, B]


def test_tiles_are_synchronised_every_step_and_alternate_grids_cover_the_seams():
    H, W, th, tw = 16, 24, 8, 12
    ref = _ref(T=2, C=2, H=H, W=W)
    seen = []

    def den(x, i, rect):
        seen.append((i, rect))
        return x * 0.5 + 0.5 * ref[..., rect[1]:rect[3], rect[0]:rect[2]]
    out = R.refine_latent_tiled(ref, _grid(H, W, th, tw, True), den, ALPHAS, strength=0.5, lam=0.5, generator=torch.Generator().manual_seed(0))
    assert out.shape == ref.shape and torch.isfinite(out).all()
    i0 = R.start_step(N, 0.5)
    per_step = {}
    for i, r in seen:
        per_step.setdefault(i, set()).add(r)
    assert all(len(v) == (4 if (i - i0) % 2 == 0 else 5) for i, v in per_step.items())       # A (4 tiles) / B (5 tiles) alternate
    # a seam-centred tile exists on the odd steps: the seam x = 12 is interior to it
    assert any(r[0] < 12 < r[2] for r in per_step[i0 + 1])
    assert not any(r[0] < 12 < r[2] for r in per_step[i0])


def test_assemble_blends_tiles_back_into_the_frame():
    full = _ref(T=2, C=2, H=16, W=24)
    rects = [(0, 0, 16, 16), (8, 0, 24, 16)]
    w = [torch.ones(16, 16), torch.ones(16, 16)]
    parts = [full[..., r[1]:r[3], r[0]:r[2]] for r in rects]
    assert torch.allclose(R.assemble(parts, rects, w, (16, 24)), full, atol=1e-6)


def test_dit_backend_calls_the_sampler_like_sampler_step_does():
    class FakeSampler:
        def __init__(self):
            self.calls = []

        def prepare_sampling_loop(self, x, cond, uc):
            return x, None, torch.tensor(ALPHAS), len(ALPHAS), cond, uc, torch.arange(N + 1)

        def denoise(self, x, a, cond, uc, timestep, idx):
            self.calls.append((x.shape, float(a), int(timestep), idx, "control" in cond))
            return x * 0.0 + 3.0

    s = FakeSampler()
    be = R.DitRefineBackend(s, None, torch.zeros(1), torch.zeros(1), device="cpu", use_tile_control=True)
    alphas = be.schedule()
    assert len(alphas) == N + 1 and alphas[-1] == 1.0
    out = be.denoise(torch.zeros(3, 4, 8, 8), 5, (0.0, 0.0, 0.5, 0.5))
    shape, a, ts, idx, has_ctrl = s.calls[0]
    assert shape == (1, 3, 4, 8, 8) and a == pytest.approx(ALPHAS[5]) and ts == int(torch.arange(N + 1)[-6]) and idx == N - 5 and has_ctrl
    assert out.shape == (3, 4, 8, 8) and out.mean() == 3.0
