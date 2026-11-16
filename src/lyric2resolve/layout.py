"""Text layout for 16:9 and 9:16: safe areas, line wrapping, position, length warnings.

Text width is ESTIMATED from character counts (no font rendering): average glyph width
is ~0.55 em for mixed case and ~0.68 em for uppercase in typical sans fonts. That is
good enough to warn "this probably won't fit"; it never changes anything by itself.
"""

from __future__ import annotations

from dataclasses import dataclass

LAYOUTS = {"16:9": (1920, 1080), "9:16": (1080, 1920)}
TITLE_SAFE = 0.90      # usable fraction of width/height (title-safe area)


@dataclass(frozen=True)
class Frame:
    name: str
    width: int
    height: int

    @property
    def safe_width(self) -> float:
        return self.width * TITLE_SAFE

    @property
    def safe_height(self) -> float:
        return self.height * TITLE_SAFE


def frame(layout: str, width: int | None = None, height: int | None = None) -> Frame:
    """'16:9' or '9:16'. Custom sizes keep the orientation (e.g. 3840x2160)."""
    if layout not in LAYOUTS:
        raise ValueError(f"unknown layout {layout!r}; use {list(LAYOUTS)}")
    w, h = LAYOUTS[layout]
    if width and height:
        w, h = (max(width, height), min(width, height)) if layout == "16:9" else (min(width, height), max(width, height))
    return Frame(layout, w, h)


def default_font_px(fr: Frame) -> int:
    """Readable default: ~7.5% of the frame height in 16:9, ~4.4% in 9:16 (same pixel size on 1080 wide)."""
    return round(fr.height * 0.075) if fr.width >= fr.height else round(fr.height * 0.044)


def char_width(text: str, font_px: float) -> float:
    letters = [c for c in text if not c.isspace()]
    upper = sum(1 for c in letters if c.isupper())
    ratio = upper / len(letters) if letters else 0
    em = 0.55 + (0.68 - 0.55) * ratio
    return em * font_px


def text_width(text: str, font_px: float) -> float:
    return len(text) * char_width(text, font_px)


def wrap(text: str, font_px: float, max_width: float) -> list[str]:
    """Greedy word wrap by estimated width. A single too-long word stays on its own line."""
    words = text.split()
    if not words:
        return []
    cw = char_width(text, font_px)
    max_chars = max(1, int(max_width // cw))
    lines, cur = [], ""
    for w in words:
        cand = f"{cur} {w}" if cur else w
        if len(cand) <= max_chars or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def balanced_wrap(text: str, font_px: float, max_width: float) -> list[str]:
    """Wrap into the minimum number of lines, then balance line lengths (nicer for lyrics)."""
    greedy = wrap(text, font_px, max_width)
    n = len(greedy)
    if n <= 1:
        return greedy
    words = text.split()
    best, best_score = greedy, None
    max_chars = max(1, int(max_width // char_width(text, font_px)))

    def splits(ws: list[str], k: int):
        if k == 1:
            yield [" ".join(ws)]
            return
        for i in range(1, len(ws) - k + 2):
            head = " ".join(ws[:i])
            for rest in splits(ws[i:], k - 1):
                yield [head, *rest]

    if len(words) <= 24:  # small search; lyric blocks are short
        for cand in splits(words, n):
            if any(len(line) > max_chars for line in cand) and any(len(w) <= max_chars for w in words):
                continue
            score = max(len(line) for line in cand) - min(len(line) for line in cand)
            if best_score is None or score < best_score:
                best, best_score = cand, score
    return best


@dataclass
class LayoutCheck:
    layout: str
    lines: list[str]
    font_px: int
    max_lines: int
    too_wide_word: bool

    @property
    def ok(self) -> bool:
        return len(self.lines) <= self.max_lines and not self.too_wide_word

    def message(self) -> str:
        if self.too_wide_word:
            return f"{self.layout}: a word is wider than the safe area at {self.font_px}px"
        return (f"{self.layout}: needs {len(self.lines)} lines at {self.font_px}px "
                f"(max {self.max_lines}) - probably too long")


def check_text(text: str, layout: str, font_px: int | None = None, max_lines: int = 2,
               width: int | None = None, height: int | None = None) -> LayoutCheck:
    fr = frame(layout, width, height)
    px = font_px or default_font_px(fr)
    lines = balanced_wrap(text, px, fr.safe_width)
    too_wide = any(text_width(w, px) > fr.safe_width for w in text.split())
    total_h = len(lines) * px * 1.2
    if total_h > fr.safe_height * 0.5:  # more than half the screen of text is never OK
        max_lines = min(max_lines, len(lines) - 1)
    return LayoutCheck(layout, lines, px, max_lines, too_wide)
