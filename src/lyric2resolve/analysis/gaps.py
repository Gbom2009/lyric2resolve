"""Vocal activity + instrumental gap detection. Pure numpy."""

from __future__ import annotations

import numpy as np

from lyric2resolve.project import Gap, Project, Word


def vocal_activity(y: np.ndarray, sr: int, frame_s: float = 0.05, threshold_db: float = -40.0,
                   min_on_s: float = 0.1, hangover_s: float = 0.3) -> list[tuple[float, float]]:
    """Active intervals of the acapella (RMS above threshold relative to its loud parts)."""
    x = y.mean(axis=1) if y.ndim == 2 else y
    hop = max(1, int(frame_s * sr))
    n = len(x) // hop
    if n == 0:
        return []
    rms = np.sqrt(np.mean(x[: n * hop].reshape(n, hop).astype(np.float64) ** 2, axis=1) + 1e-12)
    ref = np.percentile(rms, 95)
    if ref <= 1e-6:
        return []
    db = 20 * np.log10(rms / ref)
    active = db > threshold_db
    # hangover: keep active for a while after it drops (word tails, breaths)
    hang = int(hangover_s / frame_s)
    idx = np.flatnonzero(active)
    for i in idx:
        active[i:i + hang] = True
    out, start = [], None
    for i, a in enumerate(np.append(active, False)):
        if a and start is None:
            start = i
        elif not a and start is not None:
            if (i - start) * frame_s >= min_on_s:
                out.append((round(start * frame_s, 3), round(i * frame_s, 3)))
            start = None
    return out


def detect_gaps(words: list[Word], duration: float, min_gap_s: float = 4.0,
                activity: list[tuple[float, float]] | None = None) -> list[tuple[float, float]]:
    """Gaps = stretches >= min_gap_s without words (intro, breaks, outro).

    If vocal activity is given, a word-less stretch that is mostly sung (e.g. a missed
    word / ad-lib) is not treated as an instrumental gap.
    """
    spans = sorted((w.start, w.end) for w in words)
    cands: list[tuple[float, float]] = []
    prev_end = 0.0
    for s, e in spans:
        if s - prev_end >= min_gap_s:
            cands.append((prev_end, s))
        prev_end = max(prev_end, e)
    if duration - prev_end >= min_gap_s:
        cands.append((prev_end, duration))
    if not spans and duration >= min_gap_s:
        cands = [(0.0, duration)]
    if activity is None:
        return [(round(a, 3), round(b, 3)) for a, b in cands]
    out = []
    for a, b in cands:
        sung = sum(max(0.0, min(b, e) - max(a, s)) for s, e in activity)
        if sung / (b - a) < 0.5:
            out.append((round(a, 3), round(b, 3)))
    return out


def apply_auto_gaps(project: Project, gaps: list[tuple[float, float]]) -> None:
    """Replace auto gaps, keep manual ones; skip auto gaps overlapping a manual gap."""
    manual = [g for g in project.gaps if g.source == "manual"]
    project.gaps = list(manual)
    for a, b in gaps:
        if any(a < m.end and b > m.start for m in manual):
            continue
        project.gaps.append(Gap(project.next_id("g"), a, b, "auto"))
    project.gaps.sort(key=lambda g: g.start)
