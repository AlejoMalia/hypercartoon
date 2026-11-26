"""Absorb episodes into the registry. Idempotent (unchanged episodes skipped) and order-independent, so adding a
second season later only costs the new episodes. Backends are injected callables:

  tracker(path)               -> (labels uint8[T,H,W], {track_id: label})
  embedder(path, labels)      -> ({track_id: vec}, {track_id: [(start_s, end_s)]})
  speech(path)                -> [(start_s, end_s, voice_vec)]
"""
import os
from typing import Callable, Dict, Optional

from studio.characters import Registry


def _has(*mods) -> bool:
    import importlib.util

    return all(importlib.util.find_spec(m) is not None for m in mods)


def default_backends(device: str = "cuda", voice: str = "auto", vision: bool = True):
    """-> (tracker, embedder, speech, absorber, notes). Missing optional packages degrade gracefully and say so in notes:
    no ultralytics/transformers -> no object/character vision (voices and sound still work); no speechbrain -> simple voice print."""
    from studio import audio
    from studio.sound.bank import AudioAbsorber

    notes, tracker, embedder = [], None, None
    if vision and _has("ultralytics", "transformers", "torch"):
        from hypercartoon.perception import backends

        tracker = lambda p: backends.yolo_track(p, device=device)
        embedder = lambda p, labels: backends.track_embeddings(p, labels, device=device)
    else:
        notes.append("objetos/personajes visuales omitidos: instala `pip install -e \".[perception]\"` (ultralytics, transformers, torch)")
    use_ecapa = voice == "ecapa" or (voice == "auto" and _has("speechbrain", "torch"))
    emb = audio.ecapa_embedder("cpu") if use_ecapa else audio.logmel_embedding
    if not use_ecapa:
        notes.append("huella de voz simple (instala speechbrain para ECAPA, mucho más fiable)")
    ab = AudioAbsorber(emb)  # also collects voice-reference / ambience candidates and soundtrack ratios
    return tracker, embedder, ab, ab, notes


def absorb_corpus(corpus_eps, registry: Registry, tracker: Optional[Callable], embedder: Optional[Callable],
                  speech: Optional[Callable], on_episode: Optional[Callable] = None,
                  progress: Optional[Callable] = None) -> Dict[str, int]:
    """corpus_eps: iterable of {path, duration, series, season, episode}. progress(done, total, path). Returns counters."""
    stats = {"new": 0, "skipped": 0}
    corpus_eps = list(corpus_eps)
    for n, e in enumerate(corpus_eps):
        if progress:
            progress(n, len(corpus_eps), e["path"])
        p = e["path"]
        st = os.stat(p)
        stamp = [float(st.st_size), float(st.st_mtime)]
        if registry.is_done(p, stamp):
            stats["skipped"] += 1
            continue
        vecs, names, ivs = {}, {}, {}
        if tracker and embedder:
            labels, names = tracker(p)
            vecs, ivs = embedder(p, labels)
        sp = speech(p) if speech else []
        registry.add_episode(p, stamp, e["duration"], vecs, names, ivs, sp)
        stats["new"] += 1
        if on_episode:
            on_episode(e, registry)
    if progress:
        progress(len(corpus_eps), len(corpus_eps), "")
    registry.consolidate()
    return stats
