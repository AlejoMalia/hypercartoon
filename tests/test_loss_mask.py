import pytest

torch = pytest.importorskip("torch")

from hypercartoon.models.cogvideo.loss_mask import fit_mask, masked_l2  # noqa: E402


def test_unmasked_loss_is_the_plain_mean():
    sq = torch.rand(2, 5, 4, 6, 8)
    assert torch.allclose(masked_l2(sq, None), sq.reshape(2, -1).mean(1))
    assert torch.allclose(masked_l2(sq, torch.ones(2, 5, 6, 8)), sq.reshape(2, -1).mean(1), atol=1e-6)


def test_masked_pixels_get_no_loss_and_no_gradient():
    sq = torch.zeros(1, 3, 2, 4, 4, requires_grad=True)
    with torch.no_grad():
        sq[:] = 1.0
        sq[0, :, :, :2, :] = 100.0  # the overlay (top half) is very wrong
    sq.retain_grad()
    mask = torch.ones(1, 3, 4, 4)
    mask[:, :, :2, :] = 0
    loss = masked_l2(sq, mask)
    loss.sum().backward()
    assert abs(loss.item() - 1.0) < 1e-5            # only the clean half counts
    assert sq.grad[0, :, :, :2, :].abs().max() == 0  # ... and the overlay receives no gradient
    assert sq.grad[0, :, :, 2:, :].min() > 0


def test_floor_keeps_an_almost_fully_masked_clip_from_exploding():
    sq = torch.ones(1, 2, 1, 4, 4)
    mask = torch.zeros(1, 2, 4, 4)
    mask[0, 0, 0, 0] = 1  # one kept cell
    assert masked_l2(sq, mask).item() == pytest.approx(1 / (0.25 * sq.numel()))
    assert masked_l2(sq, torch.zeros(1, 2, 4, 4)).item() == 0.0


def test_mask_is_resized_to_the_latent_shape():
    m = fit_mask(torch.ones(2, 13, 60, 90), 7, 30, 45)
    assert m.shape == (2, 7, 30, 45)
