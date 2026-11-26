# Perception: object identity & motion coherence

Integrates SAM 2 / Grounded-SAM-2, Ultralytics YOLO (ByteTrack/BoT-SORT) behind one cached representation:
a `uint8[T,60,90]` label map (0 = background, k = persistent object id) aligned with the VAE latent grid.

**Compute policy:** perception never runs inside training or sampling. It runs once per video in
`data/precomp_tracks.py` (skipped if the `.npz` exists) and in `scripts/eval_coherence.py`.
Grounded-SAM-2 detects on one keyframe only; SAM 2's memory propagates identities to the other frames.

```bash
pip install -e ".[perception]"
python data/precomp_tracks.py --episode_dir EP --output_dir TRACKS --backend grounded_sam2 --prompts "person,dog" --sam2_ckpt sam2.1_hiera_large.pt
python scripts/eval_coherence.py --labels TRACKS      # or --videos GENERATED_DIR
```

Metrics (`hypercartoon/perception/coherence.py`): temporal IoU, persistence, id churn, motion smoothness -> `coherence` in [0,1].
Roboflow Trackers / BoxMOT / MMTracking are not wired yet: add them as one function in `backends.py` returning the same label map.
Next step (needs H100 retraining): feed the label maps as per-object conditioning in the DiT.
