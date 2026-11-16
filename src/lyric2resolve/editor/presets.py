"""Block presets (WORD / LINE / PHRASE / AUTO) per section, plus text options.

Presets build blocks as a starting point; the user then edits by hand. A block never
spans an instrumental gap, a section boundary, or more than max_chars characters.
"""

from __future__ import annotations

import re
import string
from pathlib import Path

from lyric2resolve.project import Block, Project, ProjectSettings, Section, Word

PRESETS = ("word", "line", "phrase", "auto")


def _in_gap(p: Project, t: float) -> bool:
    return any(g.start <= t < g.end for g in p.gaps)


def _gap_between(p: Project, a: Word, b: Word) -> bool:
    """True if a gap overlaps the silence between word a and the later word b."""
    return any(g.start < b.start and g.end > a.end for g in p.gaps)


def section_for(p: Project, w: Word) -> Section | None:
    mid = (w.start + w.end) / 2
    for s in p.sections:
        if s.start <= mid < s.end:
            return s
    return None


def _group(p: Project, words: list[Word], preset: str, cfg: ProjectSettings) -> list[list[Word]]:
    groups: list[list[Word]] = []
    for w in words:
        if not groups:
            groups.append([w])
            continue
        prev = groups[-1][-1]
        cur = groups[-1]
        if preset == "word":
            new = True
        elif preset == "line":
            new = w.line != prev.line
        elif preset == "phrase":
            new = len(cur) >= max(1, cfg.phrase_words) or w.line != prev.line  # phrases restart per line
        elif preset == "auto":
            new = (w.start - prev.end) > cfg.auto_pause_s
        else:
            raise ValueError(f"unknown preset {preset!r}; use one of {PRESETS}")
        if new:
            groups.append([w])
        else:
            cur.append(w)
    return groups


def _split_long(groups: list[list[Word]], max_chars: int) -> list[list[Word]]:
    """Split groups whose text is longer than max_chars, at the biggest pause near the middle."""
    out: list[list[Word]] = []
    stack = list(reversed(groups))
    while stack:
        g = stack.pop()
        text_len = len(" ".join(w.text for w in g))
        if max_chars <= 0 or text_len <= max_chars or len(g) < 2:
            out.append(g)
            continue
        n = len(g)
        best, best_score = 1, -1e9
        for k in range(1, n):
            left = len(" ".join(w.text for w in g[:k]))
            balance = -abs(left - text_len / 2) / max(1, text_len)
            pause = g[k].start - g[k - 1].end
            score = balance + pause
            if score > best_score:
                best, best_score = k, score
        stack.append(g[best:])
        stack.append(g[:best])
    return out


def apply_presets(p: Project, default: str | None = None, only_section: str | None = None,
                  keep_styles: bool = True) -> None:
    """Rebuild blocks. Section preset > default (> project setting). Words in gaps are skipped.

    only_section: rebuild only the words of that section; other blocks stay as they are.
    """
    cfg = p.settings
    default = default or cfg.granularity
    old_styles = {wid: b.style for b in p.blocks for wid in b.word_ids} if keep_styles else {}
    if only_section:
        sec = next((s for s in p.sections if s.id == only_section), None)
        if sec is None:
            raise ValueError(f"unknown section {only_section}")
        target = {w.id for w in p.words if section_for(p, w) is sec}
        keep = []
        for b in p.blocks:
            if not target.intersection(b.word_ids):
                keep.append(b)
                continue
            # a block crossing the section boundary: its words outside the section keep their own block(s)
            run: list[str] = []
            for wid in b.word_ids + [None]:
                if wid is not None and wid not in target:
                    run.append(wid)
                elif run:
                    keep.append(Block("", run, None, b.style))
                    run = []
        for b in keep:
            if not b.id:
                b.id = p.next_id("b")
                p.blocks.append(b)  # so next_id sees it (the list is replaced below)
    else:
        target = {w.id for w in p.words}
        keep = []
    words = [w for w in p.words if w.id in target and not _in_gap(p, (w.start + w.end) / 2)]
    # runs separated by section changes and gaps
    runs: list[list[Word]] = []
    for w in words:
        if runs:
            prev = runs[-1][-1]
            if section_for(p, prev) is not section_for(p, w) or _gap_between(p, prev, w) \
                    or p.word_index()[w.id] != p.word_index()[prev.id] + 1:
                runs.append([w])
                continue
            runs[-1].append(w)
        else:
            runs.append([w])
    new_blocks: list[Block] = []
    for run in runs:
        sec = section_for(p, run[0])
        preset = (sec.preset if sec and sec.preset else default).lower()
        for g in _split_long(_group(p, run, preset, cfg), cfg.max_chars):
            new_blocks.append(Block("", [w.id for w in g], None, old_styles.get(g[0].id)))
    p.blocks = keep
    for b in new_blocks:
        b.id = p.next_id("b")
        p.blocks.append(b)
    idx = p.word_index()
    p.blocks.sort(key=lambda b: idx[b.word_ids[0]])


def merge_short_blocks(p: Project, min_frames: int | None = None) -> int:
    """Merge blocks shorter than N frames into a neighbour (never across a gap). Returns merges done."""
    fps = p.settings.fps
    min_frames = p.settings.min_clip_frames if min_frames is None else min_frames
    min_s = min_frames / fps
    merged = 0
    i = 0
    idx = p.word_index()
    wm = p.word_map()
    while i < len(p.blocks):
        b = p.blocks[i]
        s, e = p.block_span(b)
        if e - s >= min_s or len(p.blocks) == 1:
            i += 1
            continue
        cands = []
        for j in (i - 1, i + 1):
            if 0 <= j < len(p.blocks):
                o = p.blocks[j]
                a, c = (o, b) if j < i else (b, o)
                adjacent = idx[c.word_ids[0]] == idx[a.word_ids[-1]] + 1
                if adjacent and not _gap_between(p, wm[a.word_ids[-1]], wm[c.word_ids[0]]):
                    os_, oe = p.block_span(o)
                    cands.append((min(abs(s - oe), abs(os_ - e)), j))
        if not cands:
            i += 1
            continue
        _, j = min(cands)
        a, c = (p.blocks[j], b) if j < i else (b, p.blocks[j])
        a.word_ids = a.word_ids + c.word_ids
        a.text_override = None
        p.blocks.remove(c)
        merged += 1
        i = max(0, min(i, j))
    return merged


# ------------------------------------------------------------------ text options (export-time)
_PUNCT = re.compile(r"[%s¡¿…“”‘’«»]" % re.escape(string.punctuation.replace("'", "")))


def format_text(text: str, case: str = "keep", strip_punctuation: bool = False) -> str:
    if strip_punctuation:
        text = _PUNCT.sub("", text)
        text = re.sub(r"\s+", " ", text).strip()
    if case == "upper":
        return text.upper()
    if case == "lower":
        return text.lower()
    if case == "title":
        return " ".join(w[:1].upper() + w[1:].lower() for w in text.split(" "))
    return text


def display_text(p: Project, block: Block) -> str:
    return format_text(p.block_text(block), p.settings.case, p.settings.strip_punctuation)


# ------------------------------------------------------------------ YAML section config
def load_sections_yaml(path: Path) -> dict:
    """sections.yaml:
        default: line
        phrase_words: 4
        auto_pause_s: 0.6
        sections:
          chorus: word        # by label
          s0003: phrase       # or by section id
    """
    import yaml

    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("sections.yaml must be a mapping")
    for name, preset in (data.get("sections") or {}).items():
        if str(preset).lower() not in PRESETS:
            raise ValueError(f"section {name}: unknown preset {preset!r}")
    if data.get("default") and str(data["default"]).lower() not in PRESETS:
        raise ValueError(f"default: unknown preset {data['default']!r}")
    return data


def apply_sections_config(p: Project, data: dict) -> None:
    if data.get("default"):
        p.settings.granularity = str(data["default"]).lower()
    for key in ("phrase_words", "auto_pause_s", "max_chars"):
        if key in data:
            setattr(p.settings, key, type(getattr(p.settings, key))(data[key]))
    mapping = {str(k).lower(): str(v).lower() for k, v in (data.get("sections") or {}).items()}
    for s in p.sections:
        if s.id.lower() in mapping:
            s.preset = mapping[s.id.lower()]
        elif s.label.lower() in mapping:
            s.preset = mapping[s.label.lower()]
