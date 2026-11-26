# Notice

Hypercartoon builds on and vendors third-party work, all MIT-licensed:

* **TTT-Video** (c) 2025 test-time-training, https://github.com/test-time-training/ttt-video — the diffusion-transformer
  training/sampling engine in `hypercartoon/` descends from this code (Hussein, Koceja, Dalal et al.). The original
  copyright notice is kept in `LICENSE`. It adapts CogVideoX-5B (THUDM) with Test-Time Training layers; those layers are
  called "Hyper" layers in this repository. The optional MLP kernel is the external `ttt-tk` project.
* **emotions-hypercartoon** (c) Alejo Malia, MIT — vendored under `vendor/emotions-hypercartoon/` for emotion state tracking.
* **script-hypercartoon** (c) Alejo Malia — a small deterministic screenplay reader is vendored under `vendor/script-hypercartoon/`.

Provenance: `emotions-hypercartoon` and `script-hypercartoon` were developed by Alejo Malia under other names before being
brought into this framework; their original licence text is kept in each vendor folder.

Model weights (CogVideoX, Chatterbox, Demucs, ...) are downloaded separately and keep their own licences.
