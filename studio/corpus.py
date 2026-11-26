"""Multi-season corpus: infer series / season / episode from the folder layout, keep chronological order.

Accepted layouts (any depth, case-insensitive):  Show/S01/E03.mp4, Show/Temporada 2/cap_5.mp4, Show/1x03.mp4,
Show/S02E07.mkv. Unrecognised files fall back to season 1 in alphabetical order, so a flat folder still works."""
import os
import re
from collections import defaultdict
from typing import Dict, List, Tuple

_SEASON = re.compile(r"(?:^|[^a-z])(?:s|season|temporada|temp|t)[ _\-.]?(\d{1,2})(?![a-z]*\d*p\b)", re.I)
_SXE = re.compile(r"[sS](\d{1,2})[ _\-.]?[eE](\d{1,3})|(\d{1,2})x(\d{1,3})")
_EP = re.compile(r"(?:^|[^a-z])(?:e|ep|episode|episodio|cap|capitulo|capítulo|chapter)[ _\-.]?(\d{1,3})", re.I)
_NUM = re.compile(r"(\d{1,3})")


def parse_episode(path: str, root: str) -> Tuple[str, int, int]:
    """-> (series, season, episode). episode == 0 means 'unknown, use alphabetical order'."""
    rel = os.path.relpath(path, root)
    parts = rel.split(os.sep)
    stem = os.path.splitext(parts[-1])[0]
    season, ep = None, 0
    m = _SXE.search(stem)
    if m:
        season, ep = int(m.group(1) or m.group(3)), int(m.group(2) or m.group(4))
    for d in reversed(parts[:-1]):
        if season is None and (ms := _SEASON.search(d)) and len(d) <= 24:
            season = int(ms.group(1))
    if not ep and (me := _EP.search(stem)):
        ep = int(me.group(1))
    if not ep and (mn := _NUM.search(stem)):
        ep = int(mn.group(1))
    top = parts[0] if len(parts) > 1 and not _SEASON.fullmatch(parts[0]) else os.path.basename(root.rstrip(os.sep))
    return top, season or 1, ep


def build_corpus(videos: Dict, root: str) -> Dict:
    """videos: {path: VideoInfo} -> {series: {season: [ {path, episode, duration, order} ... ]}} (chronological)."""
    tree: Dict[str, Dict[int, List[dict]]] = defaultdict(lambda: defaultdict(list))
    for p, v in videos.items():
        s, se, ep = parse_episode(p, root)
        tree[s][se].append({"path": p, "episode": ep, "duration": v.duration})
    out = {}
    for s, seasons in tree.items():
        out[s] = {}
        for se in sorted(seasons):
            eps = sorted(seasons[se], key=lambda e: (e["episode"] == 0, e["episode"], e["path"]))
            for i, e in enumerate(eps, 1):
                e["order"] = i
            out[s][se] = eps
    return out


def flat_order(corpus: Dict) -> List[dict]:
    """Chronological list over the whole corpus: series -> season -> episode."""
    return [dict(e, series=s, season=se) for s, ss in corpus.items() for se, eps in ss.items() for e in eps]


def corpus_summary(corpus: Dict) -> str:
    rows = []
    for s, ss in corpus.items():
        for se, eps in ss.items():
            rows.append(f"{s} S{se:02d}: {len(eps)} ep, {sum(e['duration'] for e in eps) / 60:.0f} min")
    return "\n".join(rows)
