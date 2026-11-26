"""Precompute persistent-object label maps next to the VAE latents (same episode/video layout, cached, resumable).

  python data/precomp_tracks.py --episode_dir EPISODES --output_dir TRACKS --backend grounded_sam2 \
      --prompts "person,dog" --sam2_cfg configs/sam2.1/sam2.1_hiera_l.yaml --sam2_ckpt sam2.1_hiera_large.pt
"""
import argparse
import os
import tempfile
from os import path as osp

import imageio
from tqdm import tqdm

from hypercartoon.perception import backends, coherence_report, save_labelmaps


def extract_jpegs(video_path: str, out_dir: str) -> None:
    with imageio.get_reader(video_path, "ffmpeg") as r:
        for i, f in enumerate(r):
            imageio.imwrite(osp.join(out_dir, f"{i:06d}.jpg"), f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episode_dir", required=True)
    ap.add_argument("--output_dir", required=True)
    ap.add_argument("--backend", choices=["grounded_sam2", "yolo_track"], default="grounded_sam2")
    ap.add_argument("--prompts", default="", help="comma-separated object names (grounded_sam2)")
    ap.add_argument("--sam2_cfg", default="configs/sam2.1/sam2.1_hiera_l.yaml")
    ap.add_argument("--sam2_ckpt", default="")
    ap.add_argument("--yolo_weights", default="yolo11n-seg.pt")
    ap.add_argument("--device", default="cuda")
    a = ap.parse_args()

    for ep in sorted(d for d in os.listdir(a.episode_dir) if osp.isdir(osp.join(a.episode_dir, d))):
        for v in tqdm(sorted(f for f in os.listdir(osp.join(a.episode_dir, ep)) if f.endswith(".mp4")), desc=ep):
            src, dst = osp.join(a.episode_dir, ep, v), osp.join(a.output_dir, ep, v.replace(".mp4", ".npz"))
            if osp.exists(dst):  # cache hit: zero compute
                continue
            if a.backend == "yolo_track":
                labels, names = backends.yolo_track(src, a.yolo_weights, device=a.device)
            else:
                with tempfile.TemporaryDirectory() as tmp:
                    extract_jpegs(src, tmp)
                    labels, names = backends.grounded_sam2(
                        tmp, [p for p in a.prompts.split(",") if p], a.sam2_cfg, a.sam2_ckpt, device=a.device
                    )
            save_labelmaps(dst, labels, names)
            print(f"{dst}: {len(names)} objects, coherence={coherence_report(labels).get('coherence'):.3f}")


if __name__ == "__main__":
    main()
