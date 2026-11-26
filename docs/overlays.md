# Keeping the model on the animation: no burned-in text, logos or subtitles

A cartoon uploaded to a platform carries things that are **not part of the animation**: subtitles burned into the picture, the
channel's logo or watermark, a TV station's bug, title cards and credits, letterbox bars. If a video model trains on them it
learns to draw them — garbled letters, a ghost logo in a corner, subtitles in every scene. Hypercartoon blocks that at four
points, all driven by one per-video report:

```bash
python -m studio overlays episode.mp4                  # what is burned into this video?
python -m studio learn SHOW/ --overlay-mode mask       # default: mask + drop title cards (also: delogo | crop | off)
python -m studio score generated.mp4 --text            # did the generator draw text or a logo by itself?
```

| Block | What happens | Where |
|---|---|---|
| **Data** | clips that fall in title cards / credits are never cut; letterbox bars are cropped; with `--overlay-mode delogo` static logos are also removed by ffmpeg's `delogo`, with `crop` a subtitle band touching the top/bottom edge is cut away | `dataset/make_clips_*.sh` |
| **Loss** | every clip row gets `loss_mask`: a `[T, 60, 90]` 0/1 grid on the latent. Overlay cells carry **no gradient** (the loss is the mean over kept cells, with a floor so a mostly-masked clip cannot explode). Rows without the key train exactly as before | `studio/overlays.py`, `hypercartoon/models/cogvideo/loss_mask.py`, `train.py` |
| **Captions** | captions never mention text, subtitles, logos, watermarks or credits: the Qwen2.5-VL prompt forbids it and every caption (any backend) is sanitised | `OV.sanitize_caption` |
| **Generation** | every 3-second segment gets the negative text `text, subtitles, captions, watermark, logo, …` (`neg_text`, merged with your own `NEG:` line); `studio score --text` measures any text / static overlay still drawn | `studio/script.py`, `studio/overlays.py` |

The learning panel has a phase *“Texto, logos y rótulos incrustados (se excluyen)”* right after the scan; it is incremental (one
`overlays/<video>.overlay.json` per video, skipped when the video is unchanged) and the kit lists `overlays/index.json`.

## How it detects (CPU, no model)

* **Text lines** — in a 2 fps stream of small frames, light-on-dark and dark-on-light *letter-like* components (small, contrasting with
  their surroundings) that are lined up, similar in height, packed close together and wide enough form a line. Eyes, sparkles and
  other scattered blobs are rejected because they are not packed.
* **Subtitle bands** — positions where lines keep reappearing; a line there is a subtitle, and the band is masked while subtitles are
  showing (±0.5 s). Many lines or lots of text at once = a **title card / credits**, excluded from clips.
* **Logos / watermarks** — edges that stay in the same place across *different shots* while everything around them changes (needs ≥ 3
  shots and real motion; a held frame cannot be told from an overlay). Frames of credits are ignored when measuring this, because
  channel logos usually vanish there. Letters inside a logo count as the logo, never as subtitles.
* **Letterbox / pillarbox bars** — rows/columns that stay black the whole video; they are cropped.

## What a real run showed

First real test: 17 Spanish-dubbed *Simpsons* compilation clips fetched from a YouTube playlist (first 90 s of each).
The first version of the detector, tuned on synthetic renders only, **failed on real footage**: it read yellow skin, white eyes
and black outlines as text, flagged 17/17 videos and would have dropped 536 of 816 training clips. Fixed (and kept as a lesson):

* only **white / pure bright-yellow** fills with a darker surround count as letters (yellow skin, G ≈ 215, no longer does);
  dark-on-light text is not searched (cartoon outlines look like it);
* a subtitle must sit in a **narrow band** that collects ≥ 25 % of all lines, keep **one font size**, and **stay put** for more than one sample;
* a title card / credits needs several lines **on a mostly flat background**;
* cached reports carry `version`, so a changed detector recomputes them.

After the fix, on the same clips: the channel logo (a persistent corner watermark) was found as a **static overlay in 15/17 videos**,
the burned-in credit lines and in-world captions that the show itself draws ("Supervising Producers …", "Dramatization") were found
as subtitle bands (checked by eye on the frames), 0 clips were dropped and 732 of 816 carry a masked zone (mostly the logo).
Not detected: the semi-transparent TV-station bugs ("FOX", "A3") that appear only in some shots. Text that belongs to the scene is
masked like any other text.

## Honest limits

* The detector is a heuristic **calibrated on synthetic renders** (outlined and plain subtitles, a corner logo, credits). Real footage
  will differ: stylised fonts, text that is part of the story (a sign in a scene), semi-transparent watermarks, animated logos. Check
  `python -m studio overlays` on your episodes, and for real footage use an OCR detector: `--text-detector easyocr` or `paddle`
  (`pip install easyocr` / `paddleocr`; **adapters written, not run here**). Everything after detection only needs boxes.
* Text that belongs to the animation (an in-world sign) is masked like any other text — by design, the model should not learn to
  draw letters.
* Masking stops the model from *learning* the overlay; it does not repaint the pixels. For a cleaner picture (not just no gradient)
  use `delogo` / `crop`, or inpaint offline with the tools below and learn from the result.
* The masked loss is **unit-tested with torch on CPU only**; the full `train.py` path has not been run on a GPU.

## Repositories this follows (and how far they are used)

| Repository | Role here |
|---|---|
| [YaoFANGUK/video-subtitle-remover](https://github.com/YaoFANGUK/video-subtitle-remover) | AI removal of hard-coded subtitles and text-like watermarks. **Not bundled**; the right offline tool when you want the pixels repainted rather than masked |
| [sczhou/ProPainter](https://github.com/sczhou/ProPainter) | video inpainting (object / watermark removal); S-Lab licence requires attribution. **Not bundled**; same use |
| EAST ([paper](https://arxiv.org/abs/1704.03155), [OpenCV sample](https://docs.opencv.org/3.4/db/da4/samples_2dnn_2text_detection_8cpp-example.html)), DBNet / [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR), EasyOCR | scene-text detectors; `--text-detector easyocr|paddle` plugs them in as the box source (adapters, not run) |
| [DAVAR-Lab-OCR (video text spotting, YORO)](https://github.com/laofeiwei/DAVAR-Lab-OCR/blob/main/demo/videotext/yoro) | reference for text detection on video |

What *is* used and tested: ffmpeg (`crop`, `delogo`), NumPy/SciPy for the built-in detector. Nothing from the repositories above is
vendored or executed by the tests.
