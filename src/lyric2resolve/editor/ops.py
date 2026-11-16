"""Editing operations on a Project. Pure functions: they mutate the project or raise OpError.

Invariants kept by every op: blocks contain consecutive words in order, no word is in
two blocks, blocks are sorted. Words may be in no block (they are then hidden).
"""

from __future__ import annotations

from lyric2resolve.project import Block, Gap, Project, Word


class OpError(ValueError):
    pass


# ------------------------------------------------------------------ helpers
def _block(p: Project, block_id: str) -> Block:
    for b in p.blocks:
        if b.id == block_id:
            return b
    raise OpError(f"unknown block {block_id}")


def _word_pos(p: Project, word_id: str) -> int:
    idx = p.word_index()
    if word_id not in idx:
        raise OpError(f"unknown word {word_id}")
    return idx[word_id]


def _sort_blocks(p: Project) -> None:
    idx = p.word_index()
    p.blocks = [b for b in p.blocks if b.word_ids]
    p.blocks.sort(key=lambda b: idx[b.word_ids[0]])


def block_of(p: Project, word_id: str) -> Block | None:
    for b in p.blocks:
        if word_id in b.word_ids:
            return b
    return None


def consecutive_range(p: Project, word_ids: list[str]) -> list[str]:
    """Selected words -> the full consecutive run from first to last (in word order)."""
    if not word_ids:
        raise OpError("no words selected")
    pos = sorted(_word_pos(p, w) for w in word_ids)
    if pos[-1] - pos[0] + 1 != len(set(pos)):
        raise OpError("selected words must be consecutive")
    return [p.words[i].id for i in range(pos[0], pos[-1] + 1)]


def _detach(p: Project, word_ids: set[str]) -> None:
    """Remove words from their blocks; a block with a hole is split in two around it."""
    new: list[Block] = []
    pending: list[Block] = []  # split-off parts, get fresh ids after the loop
    for b in p.blocks:
        if not word_ids.intersection(b.word_ids):
            new.append(b)
            continue
        runs: list[list[str]] = [[]]
        for w in b.word_ids:
            if w in word_ids:
                if runs[-1]:
                    runs.append([])
            else:
                runs[-1].append(w)
        runs = [r for r in runs if r]
        if runs:
            b.word_ids, b.text_override = runs[0], None
            new.append(b)
            pending.extend(Block("", r, None, b.style) for r in runs[1:])
    p.blocks = new
    for nb in pending:
        nb.id = p.next_id("b")
        p.blocks.append(nb)


# ------------------------------------------------------------------ block ops
def merge_words(p: Project, word_ids: list[str]) -> Block:
    """Put the selected consecutive words in ONE block (start = first word, end = last word)."""
    run = consecutive_range(p, word_ids)
    styles = [b.style for b in p.blocks if set(run) & set(b.word_ids) and b.style]
    _detach(p, set(run))
    block = Block(p.next_id("b"), run, None, styles[0] if styles else None)
    p.blocks.append(block)
    _sort_blocks(p)
    return block


def merge_blocks(p: Project, block_ids: list[str]) -> Block:
    words: list[str] = []
    for bid in block_ids:
        words.extend(_block(p, bid).word_ids)
    return merge_words(p, words)


def split_block(p: Project, block_id: str, before_word_id: str) -> tuple[Block, Block]:
    """Split a block so that before_word_id starts the second block. Word timings are untouched."""
    b = _block(p, block_id)
    if before_word_id not in b.word_ids:
        raise OpError(f"word {before_word_id} is not in block {block_id}")
    k = b.word_ids.index(before_word_id)
    if k == 0:
        raise OpError("cannot split before the first word of a block")
    second = Block(p.next_id("b"), b.word_ids[k:], None, b.style)
    b.word_ids = b.word_ids[:k]
    b.text_override = None
    p.blocks.append(second)
    _sort_blocks(p)
    return b, second


def split_block_words(p: Project, block_id: str) -> list[Block]:
    """Split a block into one block per word."""
    b = _block(p, block_id)
    out = [b]
    while len(out[-1].word_ids) > 1:
        out.extend(split_block(p, out[-1].id, out[-1].word_ids[1])[1:])
    return out


def move_word(p: Project, word_id: str, direction: str) -> None:
    """Move a boundary word to the neighbouring block: 'prev' (first word -> previous block)
    or 'next' (last word -> next block). The neighbour must be directly adjacent."""
    b = block_of(p, word_id)
    if b is None:
        raise OpError("word is not in a block")
    idx = p.word_index()
    i = p.blocks.index(b)
    if direction == "prev":
        if b.word_ids[0] != word_id:
            raise OpError("only the first word of a block can move to the previous block")
        if i == 0 or idx[p.blocks[i - 1].word_ids[-1]] != idx[word_id] - 1:
            raise OpError("there is no adjacent previous block")
        p.blocks[i - 1].word_ids.append(word_id)
        p.blocks[i - 1].text_override = None
        b.word_ids.pop(0)
    elif direction == "next":
        if b.word_ids[-1] != word_id:
            raise OpError("only the last word of a block can move to the next block")
        if i == len(p.blocks) - 1 or idx[p.blocks[i + 1].word_ids[0]] != idx[word_id] + 1:
            raise OpError("there is no adjacent next block")
        p.blocks[i + 1].word_ids.insert(0, word_id)
        p.blocks[i + 1].text_override = None
        b.word_ids.pop()
    else:
        raise OpError("direction must be 'prev' or 'next'")
    b.text_override = None
    _sort_blocks(p)


def remove_block(p: Project, block_id: str) -> None:
    """Remove a block; its words stay in the project but are not shown/exported."""
    p.blocks.remove(_block(p, block_id))


def set_block_text(p: Project, block_id: str, text: str | None) -> None:
    b = _block(p, block_id)
    b.text_override = None if text is None or text.strip() == p.block_text(Block("x", b.word_ids)) else text


def set_block_style(p: Project, block_id: str, style: str | None) -> None:
    _block(p, block_id).style = style or None


# ------------------------------------------------------------------ word ops
def set_word_text(p: Project, word_id: str, text: str) -> None:
    text = (text or "").strip()
    if not text:
        raise OpError("word text cannot be empty (remove the block instead)")
    p.words[_word_pos(p, word_id)].text = text


def set_word_timing(p: Project, word_id: str, start: float | None = None, end: float | None = None) -> None:
    w = p.words[_word_pos(p, word_id)]
    s = w.start if start is None else max(0.0, round(float(start), 3))
    e = w.end if end is None else max(0.0, round(float(end), 3))
    if e < s:
        raise OpError("end must be after start")
    w.start, w.end = s, e


def nudge_words(p: Project, word_ids: list[str], delta: float, edge: str = "both") -> None:
    """Shift start/end/both of words by delta seconds (never below 0, never end < start)."""
    for wid in word_ids:
        w = p.words[_word_pos(p, wid)]
        s = w.start + delta if edge in ("both", "start") else w.start
        e = w.end + delta if edge in ("both", "end") else w.end
        if s < 0:
            e, s = e - s if edge == "both" else e, 0.0
        if e < s:
            raise OpError("nudge would make a word end before it starts")
        w.start, w.end = round(s, 3), round(e, 3)


def nudge_block(p: Project, block_id: str, delta: float) -> None:
    nudge_words(p, list(_block(p, block_id).word_ids), delta)


# ------------------------------------------------------------------ your own text (where Whisper missed it)
def _clear_gaps(p: Project, start: float, end: float, keep_min: float = 0.5) -> int:
    """Make room in instrumental gaps for new text: trim/split/remove gaps overlapping [start, end]."""
    out, changed = [], 0
    for g in p.gaps:
        if g.end <= start or g.start >= end:
            out.append(g)
            continue
        changed += 1
        if g.start < start and start - g.start >= keep_min:
            out.append(Gap(g.id, g.start, round(start, 3), "manual"))
        if g.end > end and g.end - end >= keep_min:
            out.append(Gap(p.next_id("g") if g.start < start else g.id, round(end, 3), g.end, "manual"))
    p.gaps = sorted(out, key=lambda x: x.start)
    return changed


def add_text(p: Project, text: str, start: float, end: float, mode: str = "lines") -> list[Block]:
    """Insert your own words at [start, end] seconds.

    mode 'lines': every line of text becomes one block (default); 'block': everything in one block;
    'words': one block per word. Word times are spread over the range by word length. The range must not
    overlap existing words (lyrics stay in time order); instrumental gaps there are trimmed to make room.
    """
    start, end = round(max(0.0, float(start)), 3), round(float(end), 3)
    if end <= start:
        raise OpError("the end time must be after the start time")
    lines = [ln.split() for ln in (text or "").splitlines() if ln.strip()]
    tokens = [t for ln in lines for t in ln]
    if not tokens:
        raise OpError("type some text first")
    if mode not in ("lines", "block", "words"):
        raise OpError("mode must be lines, block or words")
    clash = [w for w in p.words if w.start < end and w.end > start]
    if clash:
        raise OpError(f"{len(clash)} existing word(s) are in that time range ('{clash[0].text}' at "
                      f"{clash[0].start:.2f} s). Pick a free range, or remove/shorten those words first.")
    weights = [max(1, len(t)) + 1 for t in tokens]  # longer words get more time; +1 = a small gap per word
    total, t = float(sum(weights)), start
    span = end - start
    new_words: list[Word] = []
    line_no = max([w.line for w in p.words if w.line is not None] or [-1]) + 1
    li_of = [li for li, ln in enumerate(lines) for _ in ln]
    for tok, wt, li in zip(tokens, weights, li_of):
        dur = span * wt / total
        new_words.append(Word(p.next_id("w"), tok, round(t, 3), round(t + dur * 0.9, 3), 1.0, line_no + li))
        p.words.append(new_words[-1])  # so next_id sees it
        t += dur
    for w in new_words:
        p.words.remove(w)
    pos = next((i for i, w in enumerate(p.words) if w.start >= end), len(p.words))
    p.words[pos:pos] = new_words
    if mode == "block":
        groups = [new_words]
    elif mode == "words":
        groups = [[w] for w in new_words]
    else:
        groups, k = [], 0
        for ln in lines:
            groups.append(new_words[k:k + len(ln)])
            k += len(ln)
    blocks = []
    for g in groups:
        b = Block(p.next_id("b"), [w.id for w in g])
        p.blocks.append(b)
        blocks.append(b)
    _sort_blocks(p)
    _clear_gaps(p, start, end)
    return blocks


def retime_block(p: Project, block_id: str, start: float | None = None, end: float | None = None) -> None:
    """Set a block's start/end; its words are stretched/moved proportionally (their order stays)."""
    b = _block(p, block_id)
    ws = p.block_words(b)
    s0, e0 = ws[0].start, ws[-1].end
    s = s0 if start is None else round(max(0.0, float(start)), 3)
    e = e0 if end is None else round(float(end), 3)
    if e <= s:
        raise OpError("the end time must be after the start time")
    idx = p.word_index()
    lo, hi = idx[ws[0].id], idx[ws[-1].id]
    prev_end = p.words[lo - 1].end if lo > 0 else 0.0
    next_start = p.words[hi + 1].start if hi + 1 < len(p.words) else float("inf")
    if s < prev_end - 1e-6 or e > next_start + 1e-6:
        raise OpError(f"that would overlap the neighbouring words (free range: {prev_end:.2f} - "
                      f"{next_start:.2f} s)" if next_start != float("inf") else
                      f"that would overlap the previous word (ends at {prev_end:.2f} s)")
    k = (e - s) / (e0 - s0) if e0 > s0 else 0.0
    for w in ws:
        w.start, w.end = round(s + (w.start - s0) * k, 3), round(s + (w.end - s0) * k, 3)
    if e0 <= s0:  # zero-length block: spread evenly
        n = len(ws)
        for i, w in enumerate(ws):
            w.start, w.end = round(s + (e - s) * i / n, 3), round(s + (e - s) * (i + 1) / n, 3)


# ------------------------------------------------------------------ gaps
def add_gap(p: Project, start: float, end: float) -> Gap:
    start, end = round(max(0.0, float(start)), 3), round(float(end), 3)
    if end <= start:
        raise OpError("a gap needs end > start")
    g = Gap(p.next_id("g"), start, end, "manual")
    p.gaps.append(g)
    p.gaps.sort(key=lambda x: x.start)
    return g


def update_gap(p: Project, gap_id: str, start: float | None = None, end: float | None = None) -> None:
    g = next((x for x in p.gaps if x.id == gap_id), None)
    if g is None:
        raise OpError(f"unknown gap {gap_id}")
    s = g.start if start is None else round(max(0.0, float(start)), 3)
    e = g.end if end is None else round(float(end), 3)
    if e <= s:
        raise OpError("a gap needs end > start")
    g.start, g.end, g.source = s, e, "manual"
    p.gaps.sort(key=lambda x: x.start)


def remove_gap(p: Project, gap_id: str) -> None:
    before = len(p.gaps)
    p.gaps = [g for g in p.gaps if g.id != gap_id]
    if len(p.gaps) == before:
        raise OpError(f"unknown gap {gap_id}")


# ------------------------------------------------------------------ sections
def update_section(p: Project, section_id: str, **fields) -> None:
    s = next((x for x in p.sections if x.id == section_id), None)
    if s is None:
        raise OpError(f"unknown section {section_id}")
    for k, v in fields.items():
        if k not in ("label", "start", "end", "preset", "style"):
            raise OpError(f"cannot set section field {k}")
        setattr(s, k, v)
    if s.end <= s.start:
        raise OpError("section end must be after start")
