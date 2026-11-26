import numpy as np
import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("PIL")
import torch.nn.functional as F  # noqa: E402

from studio import hires as HR  # noqa: E402

N = 10
ALPHAS = [0.05 + 0.93 * (i / (N - 1)) ** 1.2 for i in range(N)] + [1.0]


class ToyBackend:
    """A stand-in for the DiT + VAE with the interface DitRefineBackend exposes: latents = 8x average-pooled RGB, 'denoising' = low-pass smoothing."""
    vae_stride = 8
    latent_channels = 3

    def __init__(self, add_detail=0.0, constant=None):
        self.calls, self.encoded_T, self.add_detail, self.constant = [], [], add_detail, constant

    def schedule(self):
        return list(ALPHAS)

    def encode(self, frames):
        self.encoded_T.append(frames.shape[0])
        x = frames.float().permute(0, 3, 1, 2) / 127.5 - 1.0
        return F.avg_pool2d(x, 8)

    def decode(self, z):
        up = F.interpolate(z, scale_factor=8, mode="nearest")
        return ((up.clamp(-1, 1) + 1) * 127.5).round().byte().permute(0, 2, 3, 1)

    def denoise(self, x, i, tile_pos):
        self.calls.append((i, tile_pos, tuple(x.shape)))
        if self.constant is not None:
            return torch.full_like(x, self.constant)
        return F.avg_pool2d(x, 3, stride=1, padding=1) + self.add_detail


def _frames(T=9, h=64, w=96, seed=0):
    rng = np.random.default_rng(seed)
    base = rng.random((h, w)) * 100 + 80
    out = []
    for t in range(T):
        f = np.stack([base, base * 0.8, base * 0.6], -1)
        f[10:30, (t * 4) % (w - 20) : (t * 4) % (w - 20) + 20] = (230, 200, 40)
        out.append(f.astype(np.uint8))
    return np.stack(out)


def test_generative_refiner_shapes_padding_and_tile_positions():
    be = ToyBackend()
    ref = HR.GenerativeRefiner(be, strength=0.5, lam=0.5, mode="seam_aware", seed=1)
    out = ref.refine_video(_frames(T=6), 2.0)                                       # 6 frames: not 4k+1 -> padded to 9 for the VAE, cropped back
    assert out.shape == (6, 128, 192, 3) and out.dtype == np.uint8 and set(be.encoded_T) == {9}
    i0 = int(round((1 - 0.5) * N))
    steps = {}
    for i, pos, shape in be.calls:
        steps.setdefault(i, []).append(pos)
        assert all(0.0 <= v <= 1.0 for v in pos) and pos[0] < pos[2] and pos[1] < pos[3]      # normalised rectangles of the FULL latent frame
        assert shape[2:] == (8, 12)                                                  # every tile is the native window (64x96 px = 8x12 latent)
    assert sorted(steps) == list(range(i0, N)) and all(len(v) == (4 if (i - i0) % 2 == 0 else 5) for i, v in steps.items())   # grids A / B alternate
    assert (0.25, 0.25, 0.75, 0.75) in steps[i0 + 1]                                 # the tile centred on the seam crossing
    assert ref.info["tiles"] == [4, 5] and ref.info["latent_frames"] == 9


def test_strength_zero_never_calls_the_model_and_modes_change_the_number_of_passes():
    be0 = ToyBackend()
    HR.GenerativeRefiner(be0, strength=0.0).refine_video(_frames(), 2.0)
    assert be0.calls == []                                                           # stage A untouched: only encode / decode
    counts = {}
    for mode in ("no_overlap", "seam_aware", "full_overlap"):
        be = ToyBackend()
        HR.GenerativeRefiner(be, strength=0.4, mode=mode).refine_video(_frames(), 2.0)
        counts[mode] = len(be.calls) / len({i for i, _, _ in be.calls})
    assert counts["no_overlap"] == 4 and counts["seam_aware"] == pytest.approx(4.5, abs=0.5) and counts["full_overlap"] == 9


def test_low_frequency_consistency_keeps_the_result_close_to_stage_a_even_with_a_bad_denoiser():
    frames = _frames()
    base = np.stack([np.asarray(__import__("PIL.Image", fromlist=["Image"]).fromarray(f).resize((192, 128))) for f in frames]).astype(np.float64)
    errs = {}
    for lam in (0.0, 1.0):
        out = HR.GenerativeRefiner(ToyBackend(constant=0.9), strength=0.8, lam=lam, mode="no_overlap", seed=3).refine_video(frames, 2.0).astype(np.float64)
        errs[lam] = float(np.abs(out - base).mean())
    assert errs[1.0] < 0.6 * errs[0.0]                                               # the projection is what keeps stage A's structure


def test_seeded_and_finite():
    mk = lambda seed: HR.GenerativeRefiner(ToyBackend(add_detail=0.02), strength=0.6, mode="full_overlap", seed=seed).refine_video(_frames(), 2.0)
    a, b, c = mk(5), mk(5), mk(6)
    assert np.array_equal(a, b) and not np.array_equal(a, c) and a.min() >= 0 and a.max() <= 255


def test_make_refiner_wires_the_generative_backend():
    r = HR.make_refiner("generative", backend=ToyBackend(), strength=0.2, lam=0.3, mode="full_overlap")
    assert isinstance(r, HR.GenerativeRefiner) and r.video_level and r.strength == 0.2 and r.mode == "full_overlap"
