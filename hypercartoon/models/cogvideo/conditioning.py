"""Control adapters: new capabilities for the video model without touching its pretrained weights.

* `CharacterControl`  - per-token identity + per-character signals. A label map (0 = background, k = persistent character id, the
  same ids `hypercartoon/perception` produces) tags every video token with the character it belongs to; each id gets a learned
  embedding (identity/layout control: "this character is HERE and looks like THIS") and, optionally, per-character per-frame
  features (e.g. mouth openness, emotion) gathered through that map (audio/emotion-driven mouths, per character).
* `FrameControl`      - global per-frame features (speech activity, loudness, valence, arousal...) added to every token of the
  frame: audio/emotion conditioning when no layout is known.

Every output layer is ZERO-initialised, so a model with the adapters enabled is *exactly* the base model until they are trained
(`init_weights` is called by hypercartoon.infra.parallelisms.init_model_parameters because parameters are created on the meta
device). Disabled (the default) they cost nothing. Training them needs data with controls (studio `dataset` builds the audio-side
ones) and a GPU; none of that has been run here - only the module behaviour is tested on CPU."""
from typing import Dict, Optional

import torch
import torch.nn as nn


class ControlBase(nn.Module):
    """Marker for modules that own their initialisation (like HyperBase)."""

    def init_weights(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError


def _mlp(i: int, h: int, o: int) -> nn.Sequential:
    return nn.Sequential(nn.Linear(i, h), nn.SiLU(), nn.Linear(h, o))


def _init_mlp(m: nn.Sequential) -> None:
    nn.init.normal_(m[0].weight, std=0.02)
    nn.init.zeros_(m[0].bias)
    nn.init.zeros_(m[2].weight)  # zero output => no effect until trained
    nn.init.zeros_(m[2].bias)


class CharacterControl(ControlBase):
    def __init__(self, model_dim: int, max_characters: int, feat_dim: int = 0, hidden: int = 256):
        super().__init__()
        self.max_characters, self.feat_dim = max_characters, feat_dim
        self.id_embed = nn.Embedding(max_characters + 1, model_dim)
        self.feat_mlp = _mlp(feat_dim, hidden, model_dim) if feat_dim > 0 else None

    def init_weights(self) -> None:
        nn.init.zeros_(self.id_embed.weight)
        if self.feat_mlp is not None:
            _init_mlp(self.feat_mlp)

    def forward(self, vid_emb: torch.Tensor, labels: torch.Tensor, feats: Optional[torch.Tensor] = None) -> torch.Tensor:
        """vid_emb [B, N, D] with N = T*Hp*Wp (tokens ordered t, h, w); labels [B, T, Hp, Wp] ints;
        feats [B, T, max_characters+1, feat_dim] (slot 0 = background)."""
        b, n, _ = vid_emb.shape
        if labels.shape[0] != b or labels[0].numel() != n:
            raise ValueError(f"labels {tuple(labels.shape)} do not match {n} video tokens")
        lab = labels.reshape(b, n).long().clamp(0, self.max_characters)
        out = self.id_embed(lab)
        if feats is not None and self.feat_mlp is not None:
            t = labels.shape[1]
            if feats.shape[1] != t or feats.shape[2] != self.max_characters + 1 or feats.shape[3] != self.feat_dim:
                raise ValueError(f"feats {tuple(feats.shape)} expected [B, {t}, {self.max_characters + 1}, {self.feat_dim}]")
            idx = lab.view(b, t, n // t).unsqueeze(-1).expand(-1, -1, -1, self.feat_dim)
            g = torch.gather(feats.to(vid_emb.dtype), 2, idx)  # per token: the features of ITS character at ITS frame
            out = out + self.feat_mlp(g.reshape(b, n, self.feat_dim))
        return vid_emb + out.to(vid_emb.dtype)


class FrameControl(ControlBase):
    def __init__(self, model_dim: int, frame_dim: int, hidden: int = 256):
        super().__init__()
        self.frame_dim = frame_dim
        self.mlp = _mlp(frame_dim, hidden, model_dim)

    def init_weights(self) -> None:
        _init_mlp(self.mlp)

    def forward(self, vid_emb: torch.Tensor, frame_feats: torch.Tensor) -> torch.Tensor:
        """frame_feats [B, T, frame_dim]; each frame's vector is added to all its tokens."""
        b, n, d = vid_emb.shape
        t = frame_feats.shape[1]
        if frame_feats.shape[0] != b or frame_feats.shape[2] != self.frame_dim or n % t:
            raise ValueError(f"frame_feats {tuple(frame_feats.shape)} do not fit {n} tokens / frame_dim {self.frame_dim}")
        e = self.mlp(frame_feats.to(vid_emb.dtype))  # [B, T, D]
        return vid_emb + e.unsqueeze(2).expand(b, t, n // t, d).reshape(b, n, d)


def _fourier(x: torch.Tensor, n_freq: int) -> torch.Tensor:
    """x [...] in 0..1 -> [..., 2*n_freq] sin/cos features at octave frequencies."""
    f = (2.0 ** torch.arange(n_freq, device=x.device, dtype=x.dtype)) * torch.pi
    a = x.unsqueeze(-1) * f
    return torch.cat([a.sin(), a.cos()], -1)


class TileControl(ControlBase):
    """Tells the model WHERE its window sits in a larger frame (tiled / cascaded high-resolution generation or refinement).

    COORDINATE SYSTEM (exact):
      * `tile_pos` [B, 4] = (x0, y0, x1, y1): the tile's rectangle in the FULL frame, NORMALISED to [0, 1] (x by the full width, y by the full height;
        origin top-left, y down). In pixels it is (x0 / W, y0 / H, x1 / W, y1 / H); studio.tiling.Tile.norm() produces it.
      * Tokens are the patch grid of the tile, flattened (frame, row, column). The token at (row r, column c) of an Hp x Wp grid sits at the
        centre of its patch: gx = x0 + (c + 0.5) / Wp * (x1 - x0),  gy = y0 + (r + 0.5) / Hp * (y1 - y0)   (global, in [0, 1]).
      * Features per token: Fourier features of gx and gy at octave frequencies 2^k * pi (k < n_freq): sin and cos each -> 4 * n_freq values, plus the
        tile extent (x1 - x0, y1 - y0) -> 4 * n_freq + 2 inputs to a zero-initialised MLP. The offset is identical for every frame of the tile.
    With `control_tile = false` the module does not exist and the model is exactly the original (see build_control_stack)."""

    def __init__(self, model_dim: int, n_freq: int = 6, hidden: int = 256):
        super().__init__()
        self.n_freq = n_freq
        self.mlp = _mlp(4 * n_freq + 2, hidden, model_dim)

    def init_weights(self) -> None:
        _init_mlp(self.mlp)

    def token_coordinates(self, tile_pos: torch.Tensor, hp: int, wp: int):
        """-> gx, gy [B, Hp, Wp]: global coordinates of every patch token of the tile."""
        x0, y0, x1, y1 = (tile_pos[:, i].view(-1, 1, 1) for i in range(4))
        u = (torch.arange(wp, device=tile_pos.device, dtype=tile_pos.dtype) + 0.5).view(1, 1, wp) / wp
        v = (torch.arange(hp, device=tile_pos.device, dtype=tile_pos.dtype) + 0.5).view(1, hp, 1) / hp
        b = tile_pos.shape[0]
        return (x0 + u * (x1 - x0)).expand(b, hp, wp), (y0 + v * (y1 - y0)).expand(b, hp, wp)

    def forward(self, vid_emb: torch.Tensor, tile_pos: torch.Tensor, grid) -> torch.Tensor:
        t, hp, wp = grid
        b, n, d = vid_emb.shape
        if tile_pos.shape != (b, 4) or n != t * hp * wp:
            raise ValueError(f"tile_pos {tuple(tile_pos.shape)} / grid {grid} do not fit {n} tokens")
        gx, gy = self.token_coordinates(tile_pos.to(vid_emb.dtype), hp, wp)
        ext = torch.stack([tile_pos[:, 2] - tile_pos[:, 0], tile_pos[:, 3] - tile_pos[:, 1]], -1).to(vid_emb.dtype)   # [B, 2]
        f = torch.cat([_fourier(gx, self.n_freq), _fourier(gy, self.n_freq), ext.view(b, 1, 1, 2).expand(b, hp, wp, 2)], -1)  # [B,Hp,Wp,F]
        e = self.mlp(f.reshape(b, hp * wp, -1))                                         # [B, Hp*Wp, D]
        return vid_emb + e.unsqueeze(1).expand(b, t, hp * wp, d).reshape(b, n, d)       # same offset for every frame of the tile


def build_control_stack(config) -> Optional["ControlStack"]:
    """The ONLY place the DiT decides whether control exists. Returns None (no module, no parameters, forward untouched => bit-identical to the
    original model and to its checkpoints) unless an adapter is switched on in the config."""
    chars = getattr(config, "control_max_characters", 0)
    frame = getattr(config, "control_frame_dim", 0)
    tile = bool(getattr(config, "control_tile", False))
    if chars <= 0 and frame <= 0 and not tile:
        return None
    return ControlStack(config.model_dim, chars, getattr(config, "control_feat_dim", 0), frame, tile)


def maybe_apply_control(stack: Optional["ControlStack"], vid_emb: torch.Tensor, control, grid) -> torch.Tensor:
    """What the DiT calls after the patch embedding: without a stack the SAME tensor comes back untouched."""
    return vid_emb if stack is None else stack(vid_emb, control, grid)


class ControlStack(ControlBase):
    """What DiffusionTransformer owns: either, both or neither adapter (neither => never built)."""

    def __init__(self, model_dim: int, max_characters: int = 0, feat_dim: int = 0, frame_dim: int = 0, tile: bool = False):
        super().__init__()
        self.tile = TileControl(model_dim) if tile else None
        self.character = CharacterControl(model_dim, max_characters, feat_dim) if max_characters > 0 else None
        self.frame = FrameControl(model_dim, frame_dim) if frame_dim > 0 else None

    def init_weights(self) -> None:
        for m in (self.character, self.frame, self.tile):
            if m is not None:
                m.init_weights()

    def forward(self, vid_emb: torch.Tensor, control: Optional[Dict[str, torch.Tensor]], grid=None) -> torch.Tensor:
        if not control:
            return vid_emb
        if self.tile is not None and control.get("tile_pos") is not None:
            if grid is None:
                raise ValueError("tile control needs the token grid (frames, Hp, Wp)")
            vid_emb = self.tile(vid_emb, control["tile_pos"], grid)
        if self.character is not None and control.get("labels") is not None:
            vid_emb = self.character(vid_emb, control["labels"], control.get("feats"))
        if self.frame is not None and control.get("frame_feats") is not None:
            vid_emb = self.frame(vid_emb, control["frame_feats"])
        return vid_emb
