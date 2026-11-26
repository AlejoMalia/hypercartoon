# Knowledge in layers — one style per show, one for the whole studio

The studio does not pour everything it learns into one container. It files it by **kind**, per show, and then across every show
you give it, so the system can copy one animation *or* learn what a studio's animations have in common and compose a new look.

| Layer | What it holds | How a studio of several shows is merged |
|---|---|---|
| **characters** | agents seen in the shots (people, animals; label + dominant colour + seconds on screen) and, with `--characters`, the registry (identity, name, voice) | never averaged: each character keeps its series |
| **backgrounds** | background colour of every scene (clustered into *places*), how open or busy the frame is, scenery that shows up | pooled |
| **palettes** | global palette, shadows / mids / highlights palettes, the palette **of each kind of shot**, colour metrics | pooled and weighted by minutes |
| **scene_types** | the grammar of the shots: framing × camera movement × pace (e.g. `close-up · static · quick`) with share, mean length, typical subject cell, characters | weighted share + **consistency** (how many shows really use it): all of them = *studio signature*, some = *specific to those shows* |
| **rhythm** | cuts per minute, shot-length quantiles, camera movement shares, dialogue density | mean **and spread** across shows |

```bash
python -m studio learn STUDIO_FOLDER/             # a folder with several shows (one sub-folder each): layers are built by the learning panel
python -m studio layers                            # (re)build from the analysis; prints the studio style; writes layers/CAPAS.md
python -m studio layers --import-from ../ShowB_project ../ShowC_project --prefix c_      # shows learned in other projects join this studio
python -m studio layers --compose MyLook --set palettes=_studio rhythm=ShowA:0.7,ShowB:0.3 characters=ShowA,ShowB scene_types=ShowB
python -m studio create guion.txt --style-layers MyLook     # the episode is written in that style (or `_studio`, or any one show)
```

Files: `layers/<series>/<layer>.json`, `layers/_studio/…` (merged), `layers/<name>/…` (composed), each with a `style.json`
(`style_prompt`, palette, cuts per minute, signature scene types, sources) and `layers/CAPAS.md` (Spanish report with the
palette distance between shows — if it is small the studio has one look, if it is large the merged style is a compromise).

## What `compose` means

Every layer can come from a different place: *"the studio's palette, show A's rhythm at 70 % and B's at 30 %, B's shot grammar, the
cast of A and B"*. A source is a series name, `_studio` (every show, equally in a mix, minute-weighted alone), or `name:weight`
lists. The result is a new style that no single show has, built from measurements, not from a prompt written by hand.

## Honest limits

* Everything is computed from the **analysis** the learning already produced (shots, framing, camera, colour, labelled elements): it
  is as good as that analysis. On CPU the element detector only finds unnamed colour blobs, so *characters* are "agents" only when a
  YOLO / Grounding DINO detector (`--detector`, `--prompts`) names them; otherwise the character layer is mostly empty and the
  palette / backgrounds / scene-type / rhythm layers carry the style.
* The style that reaches the generator is **words** (`style_prompt`) plus the measured numbers in `style.json`. Whether the model
  renders a blended look faithfully is exactly what `studio ab` is for; true weight-level blending is `studio fuse-weights`.
* Scene types are a descriptive grammar (framing, camera, pace), not semantic scene categories like "chase" or "dialogue in a kitchen".
* Tested on synthetic analyses and in the learning panel on a real playlist; not validated against human judgement of "same style".
