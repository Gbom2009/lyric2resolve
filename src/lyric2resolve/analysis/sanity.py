"""Rough-cut sanity check: flag (never fix) words that are probably wrong."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from lyric2resolve.project import Project

MIN_WORD_S = 0.06
MAX_WORD_S = 3.0
LOW_CONFIDENCE = 0.45
HALLUCINATIONS = ("thank you for watching", "thanks for watching", "subtitles by", "please subscribe",
                  "ondertiteling", "amara.org", "like and subscribe")


@dataclass
class Flag:
    word_id: str
    kind: str        # zero_length | very_short | very_long | overlap | low_confidence | repeat | outside_vocals | hallucination
    message: str
    severity: str = "warn"   # warn | info

    def to_dict(self) -> dict:
        return asdict(self)


def _norm(text: str) -> str:
    return re.sub(r"[^\w']+", "", text.lower())


def check(project: Project, activity: list[tuple[float, float]] | None = None) -> list[Flag]:
    flags: list[Flag] = []
    words = project.words
    for i, w in enumerate(words):
        d = w.end - w.start
        if d <= 0.001:
            flags.append(Flag(w.id, "zero_length", f"'{w.text}' has no duration ({w.start:.2f}s)"))
        elif d < MIN_WORD_S and len(_norm(w.text)) > 2:
            flags.append(Flag(w.id, "very_short", f"'{w.text}' lasts only {d * 1000:.0f} ms"))
        elif d > MAX_WORD_S:
            flags.append(Flag(w.id, "very_long", f"'{w.text}' lasts {d:.1f} s (held note or timing error?)", "info"))
        if i and w.start < words[i - 1].end - 0.02:
            flags.append(Flag(w.id, "overlap", f"'{w.text}' starts before '{words[i - 1].text}' ends"))
        if w.confidence < LOW_CONFIDENCE:
            flags.append(Flag(w.id, "low_confidence", f"Whisper was unsure about '{w.text}' ({w.confidence:.0%})"))
        if activity is not None and d > 0:
            sung = sum(max(0.0, min(w.end, e) - max(w.start, s)) for s, e in activity)
            mid = (w.start + w.end) / 2
            dist = min((min(abs(mid - s), abs(mid - e)) for s, e in activity), default=1e9)
            if sung / d < 0.2 and dist > 1.0:
                flags.append(Flag(w.id, "outside_vocals", f"'{w.text}' is {dist:.1f} s away from any singing"))
    # repeats: same token 3+ times in a row (classic Whisper loop), or a 2-4 word phrase looping 3+ times
    norms = [_norm(w.text) for w in words]
    i = 0
    while i < len(words):
        for n in (1, 2, 3, 4):
            phrase = norms[i:i + n]
            if len(phrase) < n or not all(phrase):
                continue
            reps = 1
            while norms[i + reps * n:i + (reps + 1) * n] == phrase:
                reps += 1
            if reps >= (4 if n == 1 else 3):
                for j in range(i + n, i + reps * n):
                    flags.append(Flag(words[j].id, "repeat",
                                      f"'{' '.join(words[k].text for k in range(i, i + n))}' repeats {reps}x - "
                                      "possible Whisper loop (check if the song really repeats it)", "info"))
                i += reps * n - 1
                break
        i += 1
    joined = " ".join(norms)
    for h in HALLUCINATIONS:
        hn = " ".join(_norm(t) for t in h.split())
        pos = joined.find(hn)
        if pos >= 0:
            idx = joined[:pos].count(" ")
            flags.append(Flag(words[idx].id, "hallucination", f"'{h}' looks like a Whisper hallucination"))
    order = {w.id: k for k, w in enumerate(words)}
    flags.sort(key=lambda f: order.get(f.word_id, 0))
    return flags
