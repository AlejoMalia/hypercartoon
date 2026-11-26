"""Shared tensor/helper utilities (single source of truth; previously copy-pasted in vae/ and cogvideo/)."""
from inspect import isfunction

import torch


def exists(x):
    return x is not None


def default(val, d):
    if exists(val):
        return val
    return d() if isfunction(d) else d


def expand_dims_like(x: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
    """Append trailing singleton dims to x until it has as many dims as y."""
    while x.dim() != y.dim():
        x = x.unsqueeze(-1)
    return x


def append_zero(x: torch.Tensor) -> torch.Tensor:
    return torch.cat([x, x.new_zeros([1])])


def append_dims(x: torch.Tensor, target_dims: int) -> torch.Tensor:
    """Append singleton dimensions to the end of a tensor until it has target_dims dimensions."""
    dims_to_append = target_dims - x.ndim
    if dims_to_append < 0:
        raise ValueError(f"Cannot reduce dimensions: input has {x.ndim} dims but target_dims is {target_dims}")
    return x[(...,) + (None,) * dims_to_append]
