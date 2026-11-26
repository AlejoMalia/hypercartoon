# Finishing: sharpening and format scaling

The video model outputs 480x720. `studio/finish.py` brings episodes to a delivery format and sharpens them, with **Real-ESRGAN**
([xinntao/Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN)) when installed and an ffmpeg-only path when not.

```bash
python -m studio formats                                              # hd fhd qhd 4k square vertical cinema, or WxH
python -m studio finish out/prompt-0/000000.mp4 --format fhd --model anime-video
python -m studio finish *.mp4 --format 4k --fit fill --sharpen medium --denoise --tile 400   # low VRAM: tile
python -m studio finish clip.mp4 --format hd --cpu                    # ffmpeg only (Lanczos + unsharp), no GPU
python -m studio finish clip.mp4 --format fhd --dry                   # show the plan, run nothing
```
Also as a post-process step: `{"builtin": "finish", "format": "fhd", "model": "anime-video"}` in `postprocess.json`.

## How the format is reached
The network upsamples (the models below are natively x4) and the exact target is then reached with a final Lanczos resize + **pad**
(`--fit fit`, letterbox/pillarbox), **crop** (`fill`) or **stretch**. So any size works: 720x480 -> 1920x1080 needs x2.25, which the
network produces by x4 and a resize down; 720x480 -> 4K needs x4.5 (x4 plus a small final upsample). Even sizes are enforced (h264).

## Models (weights are not bundled and not downloaded unless you pass `--allow-download`)
| Key | Real-ESRGAN model | Use |
|---|---|---|
| `anime-video` (default) | `realesr-animevideov3` (compact) | cartoon/anime **video**: lighter and more temporally stable |
| `anime6b` | `RealESRGAN_x4plus_anime_6B` | anime / illustrations, per image |
| `general` | `realesr-general-x4v3` | lighter general model |
| `x4plus` | `RealESRGAN_x4plus` | general photos, heaviest |

Put the `.pth` in `~/.cache/hypercartoon/realesrgan` (or `--weights DIR`); the exact download URLs are in the error message.
GFPGAN face enhancement is not wired: it targets photographic faces, not cartoon faces.

## Install and known issue
`pip install -e ".[finish]"`. `basicsr` 1.4.2 imports `torchvision.transforms.functional_tensor`, removed in torchvision 0.17; the
adapter aliases it at import time (`_torchvision_shim`), the other fixes are editing that import or pinning an older torchvision.

## Limits (read this)
* Super-resolution invents plausible detail; it does not recover what the generator never drew. Compare against plain Lanczos on your own footage.
* Per-frame processing can flicker. Use `anime-video`, add `--denoise` (light temporal denoise) and check motion before delivering.
* GPU cost ~ the **input** pixels of every frame (49 frames per 3 s at 720x480 = 0.35 MP each); `studio.finish.estimate` gives megapixel-frames
  and turns them into seconds only if you pass a measured seconds-per-megapixel. Nothing here was run on a GPU; the CPU path and the format
  planner are tested, the AI path is tested with a stand-in upscaler.
