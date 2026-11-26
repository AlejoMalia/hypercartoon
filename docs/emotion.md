# Emotion

Two independent measurements per line of dialogue:

1. **emotions-hypercartoon** (vendored in `vendor/emotions-hypercartoon/`, runs on Node >= 18; falls back to a small lexicon if Node is missing).
   One persistent engine instance per character. A line spoken by S is *heard* by every other character, which changes
   their state (valence / arousal / dominance, mood, dominant emotion, cortisol, style tags). The expressed emotion of a
   speaker is their current state blended (60/40) with the appraisal of their own words. `python -m studio create` writes
   it to `voices.json` and adds "Fox looks angry"-style phrases to each 3-second prompt, so the video and the voice share it.
2. **Prosody** (`studio/emotion/prosody.py`): pitch level and range, loudness, syllable rate measured from the corpus audio.
   Only *arousal* is reported and always relative to that voice's own baseline (`emotion_profile.json`), because valence
   from prosody alone is unreliable.

Delivery: `delivery_params(valence, arousal)` turns emotion into rate / pitch / energy / exaggeration used by every speaker
backend (`ScratchVoice`, `ChatterboxSpeaker`).

emotions-hypercartoon is a behavioural simulation, not feeling, and it was designed for conversation with a user; using it for
scripted multi-character dialogue is an adaptation. Scores are good for continuity (a character stays upset after an
insult), not calibrated against real annotated cartoon emotion data.

```bash
python -m studio create guion.txt --emotion emotions   # or lexicon | off | auto (default)
```
