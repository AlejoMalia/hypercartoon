"""Enhance-A-Video-style temporal attention enhancement (training-free, inference-time).

Idea (Enhance-A-Video, NUS-HPC-AI-Lab, arXiv 2502.07508): measure how strongly frames attend to *other* frames (the "cross-frame
intensity", CFI = mean of the non-diagonal elements of the temporal attention) and scale the attention output by an "enhance
temperature" built from it, which they report improves temporal coherence and detail on CogVideoX without retraining.

This is an independent re-implementation of that description, ADAPTED to this model (chunked attention over 3-second segments, with
the Hyper layers handling the long range): CFI is computed per chunk from the already normalised / rotated q and k of the video tokens.
It is NOT their package and was not validated against it or on a GPU. Extreme weights distort the video (their finding): start near 1-2
and compare against the base with the same seed (studio `ab`). Off by default (`eval.enhance_weight = 0`)."""
import torch


def cross_frame_intensity(q_vid: torch.Tensor, k_vid: torch.Tensor, num_frames: int) -> torch.Tensor:
    """q_vid / k_vid [B, H, N, D], N = num_frames * S tokens ordered (frame, space) -> scalar mean off-diagonal temporal attention."""
    b, h, n, d = q_vid.shape
    if num_frames < 2 or n % num_frames:
        raise ValueError(f"{n} video tokens cannot be split into {num_frames} frames")
    s = n // num_frames

    def per_pixel(x):  # [B, H, F*S, D] -> [B*S, H, F, D]: one tiny temporal attention per spatial position
        return x.reshape(b, h, num_frames, s, d).permute(0, 3, 1, 2, 4).reshape(b * s, h, num_frames, d)

    q, k = per_pixel(q_vid), per_pixel(k_vid)
    attn = ((q * d ** -0.5) @ k.transpose(-2, -1)).float().softmax(dim=-1)  # [B*S, H, F, F]
    eye = torch.eye(num_frames, dtype=torch.bool, device=attn.device)
    off = attn.masked_fill(eye, 0.0)
    return (off.sum(dim=(-1, -2)) / (num_frames * num_frames - num_frames)).mean()


def enhance_scale(q_vid: torch.Tensor, k_vid: torch.Tensor, num_frames: int, weight: float) -> torch.Tensor:
    """Multiplier (>= 1) for the attention output: CFI * (num_frames + weight), clamped below at 1 (never attenuates)."""
    if weight <= 0 or num_frames < 2:
        return torch.ones((), device=q_vid.device)
    return (cross_frame_intensity(q_vid, k_vid, num_frames) * (num_frames + weight)).clamp(min=1.0)
