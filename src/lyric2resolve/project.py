"""Editable project model (JSON). Stdlib only.

WORDS are atomic (text, start, end, confidence). BLOCKS are ordered groups of
consecutive words; exports read only from blocks. Sections, instrumental gaps,
analysis results and per-project settings live alongside.
"""

from __future__ import annotations

import datetime as _dt
import json
import time
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Callable, Iterable

SCHEMA_VERSION = 1
PROJECT_FILE = "project.json"


def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def _from(cls, data: dict):
    known = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in (data or {}).items() if k in known})


@dataclass
class Word:
    id: str
    text: str
    start: float
    end: float
    confidence: float = 1.0
    line: int | None = None       # lyric line index (forced alignment) or Whisper segment index

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class Block:
    id: str
    word_ids: list[str]
    text_override: str | None = None   # None = words joined with spaces
    style: str | None = None           # style preset name (Phase 9); None = section/default style


@dataclass
class Section:
    id: str
    label: str                 # verse / chorus / drop / bridge / intro / outro / ...
    start: float
    end: float
    preset: str | None = None  # word | line | phrase | auto (None = project default)
    style: str | None = None


@dataclass
class Gap:
    id: str
    start: float
    end: float
    source: str = "auto"       # auto | manual


@dataclass
class ProjectSettings:
    fps: float = 25.0
    start_timecode: str = "01:00:00:00"
    width: int = 1920
    height: int = 1080
    layouts: list[str] = field(default_factory=lambda: ["16:9", "9:16"])
    styling_level: str = "basic"
    granularity: str = "line"            # default preset for blocks
    phrase_words: int = 4
    auto_pause_s: float = 0.6
    min_gap_s: float = 4.0               # instrumental gap detection threshold
    sync_offset_ms: float = 0.0          # global offset applied at export
    pre_roll_ms: float = 0.0
    post_roll_ms: float = 0.0
    min_clip_frames: int = 6
    hold_until_next: bool = True
    fade_after_ms: float = 0.0
    case: str = "keep"                   # keep | upper | lower | title
    strip_punctuation: bool = False
    max_chars: int = 42
    font_size_px: int = 0                # 0 = automatic per layout (see layout.default_font_px)
    max_lines: int = 2


class ProjectError(ValueError):
    pass


@dataclass
class Project:
    name: str = "Untitled"
    schema_version: int = SCHEMA_VERSION
    created: str = field(default_factory=_now)
    modified: str = field(default_factory=_now)
    language: str = ""
    lyrics: str | None = None            # user lyrics (forced alignment), line breaks kept
    audio: dict = field(default_factory=dict)      # PreparedAudio.to_dict()
    transcription: dict = field(default_factory=dict)  # model, mode, params
    analysis: dict = field(default_factory=dict)   # bpm, beats, key, energy (Phase 5)
    words: list[Word] = field(default_factory=list)
    blocks: list[Block] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    gaps: list[Gap] = field(default_factory=list)
    settings: ProjectSettings = field(default_factory=ProjectSettings)
    extra: dict = field(default_factory=dict)

    # ---------------------------------------------------------------- lookups
    def word_index(self) -> dict[str, int]:
        return {w.id: i for i, w in enumerate(self.words)}

    def word_map(self) -> dict[str, Word]:
        return {w.id: w for w in self.words}

    def block_words(self, block: Block) -> list[Word]:
        wm = self.word_map()
        return [wm[i] for i in block.word_ids if i in wm]

    def block_text(self, block: Block) -> str:
        if block.text_override is not None:
            return block.text_override
        return " ".join(w.text for w in self.block_words(block)).strip()

    def block_span(self, block: Block) -> tuple[float, float]:
        ws = self.block_words(block)
        if not ws:
            raise ProjectError(f"block {block.id} has no words")
        return ws[0].start, ws[-1].end

    def next_id(self, prefix: str) -> str:
        used = {x.id for x in [*self.words, *self.blocks, *self.sections, *self.gaps]}
        n = len(used) + 1
        while f"{prefix}{n:04d}" in used:
            n += 1
        return f"{prefix}{n:04d}"

    # ---------------------------------------------------------------- validation
    def validate(self) -> list[str]:
        """Return problems (empty = valid). Blocks: consecutive words, ordered, no word twice."""
        problems: list[str] = []
        idx = self.word_index()
        if len(idx) != len(self.words):
            problems.append("duplicate word ids")
        for w in self.words:
            if w.end < w.start:
                problems.append(f"word {w.id} ends before it starts")
        seen: set[str] = set()
        last_pos = -1
        for b in self.blocks:
            if not b.word_ids:
                problems.append(f"block {b.id} is empty")
                continue
            missing = [i for i in b.word_ids if i not in idx]
            if missing:
                problems.append(f"block {b.id} references unknown words {missing}")
                continue
            pos = [idx[i] for i in b.word_ids]
            if pos != list(range(pos[0], pos[0] + len(pos))):
                problems.append(f"block {b.id} words are not consecutive")
            if pos[0] <= last_pos:
                problems.append(f"block {b.id} is out of order or overlaps the previous block")
            last_pos = max(last_pos, pos[-1])
            dup = seen.intersection(b.word_ids)
            if dup:
                problems.append(f"block {b.id} reuses words {sorted(dup)}")
            seen.update(b.word_ids)
        for g in self.gaps:
            if g.end <= g.start:
                problems.append(f"gap {g.id} has no length")
        return problems

    # ---------------------------------------------------------------- serialisation
    def to_dict(self) -> dict:
        d = asdict(self)
        extra = d.pop("extra")
        d["extra"] = extra
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Project":
        data = migrate(dict(data))
        p = _from(cls, {k: v for k, v in data.items()
                        if k not in ("words", "blocks", "sections", "gaps", "settings")})
        p.words = [_from(Word, w) for w in data.get("words", [])]
        p.blocks = [_from(Block, b) for b in data.get("blocks", [])]
        p.sections = [_from(Section, s) for s in data.get("sections", [])]
        p.gaps = [_from(Gap, g) for g in data.get("gaps", [])]
        p.settings = _from(ProjectSettings, data.get("settings", {}))
        return p


def migrate(data: dict) -> dict:
    version = int(data.get("schema_version", 1) or 1)
    if version > SCHEMA_VERSION:
        raise ProjectError(f"project was saved by a newer app version (schema {version}); update the app")
    return data


def save(project: Project, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    project.modified = _now()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(project.to_dict(), indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return path


def load(path: Path) -> Project:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ProjectError(f"cannot read project {path}: {exc}") from exc
    return Project.from_dict(data)


# ---------------------------------------------------------------- building
def make_words(raw: Iterable[dict]) -> list[Word]:
    """raw: dicts with text/start/end/confidence(/line). Strips whitespace, drops empty tokens."""
    out: list[Word] = []
    for r in raw:
        text = str(r.get("text", "")).strip()
        if not text:
            continue
        start, end = float(r["start"]), float(r["end"])
        out.append(Word(f"w{len(out) + 1:05d}", text, round(start, 3), round(max(end, start), 3),
                        round(float(r.get("confidence", 1.0)), 3), r.get("line")))
    return out


def blocks_by_line(words: list[Word], prefix: str = "b") -> list[Block]:
    """One block per lyric line / Whisper segment (consecutive words with the same .line)."""
    blocks: list[Block] = []
    current: list[str] = []
    current_line = object()
    for w in words:
        if current and w.line != current_line:
            blocks.append(Block(f"{prefix}{len(blocks) + 1:04d}", current))
            current = []
        current.append(w.id)
        current_line = w.line
    if current:
        blocks.append(Block(f"{prefix}{len(blocks) + 1:04d}", current))
    return blocks


# ---------------------------------------------------------------- autosave
class Autosaver:
    """Debounced autosave: call touch() after each edit, tick() regularly (e.g. every second)."""

    def __init__(self, project: Project, path: Path, delay_s: float = 2.0,
                 clock: Callable[[], float] = time.monotonic):
        self.project, self.path, self.delay, self.clock = project, Path(path), delay_s, clock
        self._dirty_since: float | None = None
        self.saves = 0

    @property
    def dirty(self) -> bool:
        return self._dirty_since is not None

    def touch(self) -> None:
        self._dirty_since = self.clock()  # restart the debounce window

    def tick(self, force: bool = False) -> bool:
        if self._dirty_since is None:
            return False
        if force or self.clock() - self._dirty_since >= self.delay:
            save(self.project, self.path)
            self._dirty_since = None
            self.saves += 1
            return True
        return False
