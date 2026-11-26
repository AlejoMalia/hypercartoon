# Video analysis

```bash
python -m studio analyze episode.mp4 --out analysis_out                      # everything below, CPU-only by default
python -m studio analyze ep.mp4 --prompts "person,door,table" --detector dino   # name the elements to find (Grounding DINO [+ SAM 2])
python -m studio analyze ep.mp4 --dialogue whisperx --hf-token $HF_TOKEN     # word times + speakers with WhisperX
```
The terminal learning panel runs it for every episode (phase "Cámara, encuadre, elementos, color y diálogo") and writes
`analysis/<episode>.analysis.json`, a Spanish report `.md`, the labelled `.srt` and the colour pictures; the show's visual grammar goes into
`profile.json["cinematography"]` and into the style prompt (e.g. "mostly medium shots, static camera"), the training captions carry the measured
framing / camera / subject position / colour of each clip, and style fusion blends the distributions.

## What is measured (`studio/analysis/`)
| Need | Module | How | Needs |
|---|---|---|---|
| Shots / cuts | `studio/ingest.py` | histogram detector; PySceneDetect `AdaptiveDetector` when installed | nothing / `scenedetect` |
| Scenes | `scenes.py` | consecutive shots grouped by palette + brightness (a cut back to an earlier angle rejoins its scene) | nothing |
| Camera movement | `camera.py` | per frame pair: block-matching flow (or OpenCV Farneback if `cv2` is installed) -> robust similarity fit (pan, tilt, zoom, rotation) -> median per shot -> *fija, paneo izquierda/derecha, tilt arriba/abajo, zoom/dolly in/out, temblor* | nothing / `opencv` |
| Framing and subject position | `framing.py` | main subject's height vs the frame -> *primer plano / plano medio / plano completo / plano general / ambiente*; 3x3 cell (rule of thirds), distance to the nearest power point | detections |
| Elements and space | `elements.py` | per keyframe: area %, bbox, centre, third, 3x3 occupancy, covered / free space; per shot inventory by label | detector |
| Dialogue | `dialogue.py` | transcript (WhisperX or faster-whisper) -> labelled with time, shot, scene, offset in the shot, whether it crosses a cut, speaker | `faster-whisper` / `whisperx` |
| Colour | `color.py` | k-means in Lab: global / per interval / per shot palettes, shadows-mids-highlights palettes, warm/cool, saturation, contrast, colour rhythm; pictures: colour strip, fingerprint, hue timeline, treemap | nothing |

Detectors (`--detector`): **blobs** (default, CPU, no model: foreground vs the dominant background colour; elements are unlabeled but their
area / position are real and it suits flat-colour cartoons), **yolo** (Ultralytics, closed vocabulary), **dino** (Grounding DINO boxes from your
prompts, SAM 2 masks for the exact area when `sam2` is configured). The colour views follow the ideas of Cinechroma, moviesColorFingerprint,
colorduce, vidcolortree and Video-Color-Summarizer; those projects' CLIs were not verified or used, the views are implemented here.

## Honest limits
* Shot type is a heuristic from the subject's height (thresholds in `framing.SHOT_TYPES`); scene grouping is by colour, not by location or story.
* Camera movement from flow: flat cartoon backgrounds have no texture (blocks are skipped, the answer can be "indeterminada"), a character filling the
  frame can be taken for the background, and zoom cannot be told from a dolly. Tested on synthetic textured footage only.
* Unlabeled blobs say *how much space* and *where*, not *what*; names need YOLO or Grounding DINO. The YOLO / DINO / SAM 2 / WhisperX adapters follow
  those projects' public APIs and were **not run** here (no GPU or packages); transformers' Grounding DINO post-processing signature changed
  between versions (both are tried).
* WhisperX speaker labels need a Hugging Face token; without it speakers come from clustering the segment voices (stable inside one video only).
* TransNetV2 (a neural shot-boundary detector) is not integrated.


## Element silhouettes, kinds and descriptions

Every shot keeps, per keyframe, a **label map** (`silhouettes/<video>.sil.npz`: 0 = background, k = k-th element) and a table
(`<video>.sil.json`, also in `analysis/*.analysis.json` as `shots[].labelled`): label, **kind** (person / animal / vehicle / scenery /
object / unlabeled; people and animals are the *agents*), a short **caption**, dominant colour, area, bounding box and a **track** id that
follows the same element across the keyframes of the shot (IoU linking; SAM 2's video predictor does this far better on moving subjects).

* Silhouettes: SAM 2 masks from Grounding DINO boxes (`--detector dino --prompts "person,dog,car,tree"`), YOLO-seg masks, or the CPU
  blob masks. Captions: measured (size · colour · label · place in the frame; no model), or `--element-captioner florence2|blip` on the crop.
* Adapters written to the public APIs and **not run here**: Grounding DINO + SAM 2 image masks, `Sam2VideoTracker` (video
  propagation), Florence-2 and BLIP captioners. The CPU path (blobs + measured captions + IoU tracks) is tested.
* Repositories this follows: [Grounded-SAM-2](https://github.com/IDEA-Research/Grounded-SAM-2), [SAM 2](https://github.com/facebookresearch/sam2),
  [SAMWISE](https://github.com/ClaudiaCuttano/SAMWISE) (text-guided SAM 2; not integrated),
  [Track-Anything](https://github.com/gaomingqi/Track-Anything), [Segment-and-Track-Anything](https://github.com/z-x-yang/Segment-and-Track-Anything).
