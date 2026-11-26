"""How long things take on screen. Keeps dialogue inside its scene so the sound system never has to report late lines."""
import math
import re

SEG = 3.0
SYL_PER_S = 4.0       # conservative delivery rate incl. breaths (ScratchVoice ~4.5/s; emotional rate adds up to +30 %)
_V = re.compile(r"[aeiouáéíóúüy]+", re.I)


def syllables(text: str) -> int:
    return sum(max(1, len(_V.findall(w))) for w in re.findall(r"[\wáéíóúüñ']+", text.lower()))


def dialogue_seconds(lines) -> float:
    """lines: [(character, text, ...)] -> seconds needed to say them in sequence (with the lead-in and 0.25 s gaps)."""
    if not lines:
        return 0.0
    return 0.2 + sum(syllables(ln[1]) / SYL_PER_S + 0.25 for ln in lines)


def scene_seconds(action_words: int, lines, requested: float = 0.0, min_s: float = SEG) -> float:
    """Needed duration snapped up to whole 3-second segments: dialogue time, action time (~2.5 words/s of description
    is what a viewer can follow), or what the author asked for, whichever is longest."""
    need = max(min_s, requested, dialogue_seconds(lines), action_words / 2.5)
    return math.ceil(need / SEG - 1e-6) * SEG
