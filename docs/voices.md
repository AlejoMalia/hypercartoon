# Voice cloning, independent of the animation learning

The voice of a character should not depend on whatever audio happened to sit under the episodes the studio learned from. The **voice
library** clones each character from *audio alone*, from any source, keeps the result as a labelled profile, and binds it to the character
by name when an episode is created. The learning stays lighter (it does not have to cluster every voice), and the voice can be as good as
the best recording you can find — a clean dub, an interview, a playlist of the actor.

```bash
python -m studio voices add HOMER ~/audio/homer_dub/ "https://www.youtube.com/playlist?list=PL…" --language es --alias HOMERO
python -m studio voices add MARGE marge_entrevista.mp3 --max-seconds 300
python -m studio voices list                     # seconds of clean speech, verdict, links
python -m studio voices say HOMER "Buenos días, familia." --speaker chatterbox --out prueba.wav     # hear the clone
python -m studio voices verify HOMER linea_generada.wav          # is this line closer to HOMER than to any other voice?
python -m studio voices from-corpus                # promote the voices found in the episodes (named characters) to library profiles
python -m studio create guion.txt                  # prints the voice of every character: clone / episode voice / guide
python -m studio sound --speaker auto              # renders the dialogue with the clones (best cloner installed)
```

## From any audio to a clean reference

Inputs are anything the studio can read (`docs/sources.md`): audio or video files, folders, URLs, YouTube videos and playlists, torrents —
only the soundtrack is kept (`.wav`, 24 kHz mono) and the fetched copies are deleted afterwards.

1. **Utterances**: speech ranges merged across short pauses into clips of 1.5–12 s; music, hum and noise that pass the energy detector
   are rejected by a speech-likeness test (`speech_like`).
2. **Dominant speaker**: every clip gets a voice descriptor; the centroid is built from the clips closest to the medoid and clips far
   beyond the typical spread are dropped — other voices in the recording cannot pull the reference away.
3. **Quality**: signal-to-noise and clipping per clip; noisy or clipped clips lose.
4. **References**: the best clips (up to ~30 s) become `ref_long.wav`, a ~8 s selection becomes `ref_primary.wav`; both loudness-normalised.
5. **Profile** (`voices/<NAME>/profile.json`): sources, language, aliases, quality, descriptor, links (`corpus_voice_id`, `visual_id`), and a
   sufficiency verdict: *insuficiente* < 5 s ≤ *mínimo* < 15 s ≤ *bueno* < 30 s ≤ *óptimo* (cloners quote 3–5 s as the floor; more clean
   speech holds the timbre better). Adding more audio to an existing name re-selects the best clips across old and new.

## Binding to characters

`voice_id = "clone:NAME"` is written into the episode's `voices.json`; names are matched case- and accent-insensitively and through
aliases. **Order of preference**: a clone profile → the voice found in the episodes → the generic guide voice. `voice_binding.json` in
the episode folder records, per character, which one was used and the profile's verdict; the creation panel flags characters without a
clone and warns when clones exist but the speaker is the guide voice.

## Cloning backends (`--speaker`)

| Speaker | Package | Licence note |
|---|---|---|
| `chatterbox` | `chatterbox-tts` | MIT code and weights; emotion drives its `exaggeration` |
| `coqui` | `coqui-tts` (Coqui XTTS-v2) | CPML: **non-commercial**; multilingual (reads `language` from the profile) |
| `f5` | `f5-tts` | code MIT, released weights **CC-BY-NC** |
| `auto` | — | the first of those that is installed, else the guide voice |
| `scratch` | — | built-in guide voice (timing / animatic): follows each character's reference *pitch* but is not a clone |

Add another model by implementing `say(text, ref_wav, voice_id, emotion)` in `studio/sound/speak.py`.

## Real speech: what was measured

On real audio (eight 90-second clips of a Spanish-dubbed cartoon compilation, one featured character each; the first 60 s build the voice,
the last 30 s are held out): every voice was built (30–42 s of clean speech, verdict *óptimo* for 7 of 8 with the built-in descriptor and 8 of 8
with ECAPA). Held-out utterances assigned to the featured character's own voice rather than the other seven:

| Embedder | Correct | Note |
|---|---|---|
| built-in `voiceprint` | 16 / 29 = 55 % | no dependencies |
| ECAPA (`speechbrain`) | **20 / 29 = 69 %** | `--embedder auto` picks it when installed |

Chance is 12.5 %, and the true ceiling is below 100 %: these compilations contain many *other* characters speaking, so a held-out clip of
another character is legitimately closer to *their* voice. Treat it as a lower bound, not an accuracy figure. Use ECAPA for real work.

## Honest limits

* **Tested**: preparation, dominant-speaker selection, music rejection, quality ranking, profiles, binding, audio from files / folders / an
  HTTP URL, an episode whose lines follow each character's reference pitch, and the real-speech experiment above (voiceprint and ECAPA).
* **Not run**: Chatterbox, Coqui XTTS-v2 and F5-TTS themselves — their weights are 1.3–3 GB and the development disk had 3 GB free; Demucs
  separation; YouTube audio against the live service was only exercised through the video path. The adapters follow the public APIs.
* `speech_like` rejects held chords and noise (synthetic tests); on real speech it accepted every utterance it was given, but rhythmic music
  with vocals can pass: use `--separate` (Demucs).
* Cloning a person's voice needs their consent and the rights to the recordings; this reads audio, it does not grant either.
