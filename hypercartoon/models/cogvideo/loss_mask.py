"""Masked training loss: pixels that are not animation (burned-in subtitles, logos, title cards) carry no gradient.

The mask lives on the latent grid, [B, T, H, W] with 1 = learn, 0 = ignore (built by studio/overlays.py). The loss of a sample is the
mean squared error over the *kept* elements; the denominator never drops below `floor` of all elements so a clip that is almost all
overlay cannot get an exploding per-pixel weight. torch only, no 3.12 syntax, testable anywhere."""
import torch
import torch.nn.functional as F


def fit_mask(mask: torch.Tensor, t: int, h: int, w: int) -> torch.Tensor:
    """Resize a [B, T0, H0, W0] mask to the latent shape (nearest) when resolutions differ."""
    if tuple(mask.shape[1:]) == (t, h, w):
        return mask
    m = F.interpolate(mask[:, None].float(), size=(t, h, w), mode="nearest")
    return m[:, 0]


def masked_l2(sq_err: torch.Tensor, mask=None, floor: float = 0.25) -> torch.Tensor:
    """sq_err [B, T, C, H, W] (already weighted) -> per-sample loss [B]."""
    b = sq_err.shape[0]
    if mask is None:
        return sq_err.reshape(b, -1).mean(1)
    t, c, h, w = sq_err.shape[1:]
    m = fit_mask(mask.to(sq_err.device), t, h, w).to(sq_err.dtype)[:, :, None]
    num = (sq_err * m).reshape(b, -1).sum(1)
    den = (m.expand_as(sq_err)).reshape(b, -1).sum(1).clamp_min(floor * sq_err[0].numel())
    return num / den
