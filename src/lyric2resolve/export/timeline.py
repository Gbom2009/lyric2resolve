"""Turn an edited project into a frame-accurate clip plan (shared by all exporters).

Rules (in this order):
1. A block's clip starts at its first word (+ global sync offset - pre-roll) and ends at its last
   word (+ post-roll), or holds until the next block / fades out after N ms, per the settings.
2. Times are snapped to whole frames of the timeline rate.
3. Clips never overlap and NEVER touch an instrumental gap: a clip running into a gap is cut at the
   gap start, a clip starting inside a gap starts at the gap end, a clip fully inside a gap is dropped.
4. Clips shorter than the minimum length are extended forward when there is room (never into a gap
   or the next clip); a clip of 0 frames is dropped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from lyric2resolve import layout as lay
from lyric2resolve import styling
from lyric2resolve.editor.presets import display_text
from lyric2resolve.project import Project

from .timecode import Rate, tc_to_frames


@dataclass
class WordTiming:
    text: str
    start_frame: int
    end_frame: int


@dataclass
class Clip:
    block_id: str
    text: str                  # display text (case/punctuation options applied)
    lines: list[str]           # wrapped for this layout
    start_frame: int           # relative to the song start (frame 0 = first audio sample)
    end_frame: int             # exclusive
    style: styling.TextStyle
    font_px: int
    x: float                   # text centre, pixels from the frame centre (FCPXML convention)
    y: float
    words: list[WordTiming] = field(default_factory=list)

    @property
    def duration(self) -> int:
        return self.end_frame - self.start_frame


@dataclass
class Marker:
    frame: int
    name: str
    kind: str                  # section | downbeat | beat
    note: str = ""


@dataclass
class MediaClip:
    clip_id: str
    name: str
    path: str                  # absolute media path
    start_frame: int           # on the song timeline (like Clip)
    end_frame: int             # exclusive
    in_frame: int = 0          # offset into the media
    hide_lyrics: bool = False

    @property
    def duration(self) -> int:
        return self.end_frame - self.start_frame


@dataclass
class Plan:
    layout: str
    width: int
    height: int
    rate: Rate
    start_tc_frames: int
    duration_frames: int
    song_path: str
    clips: list[Clip]
    markers: list[Marker]
    gaps: list[tuple[int, int]]   # [start, end) frames
    warnings: list[str] = field(default_factory=list)
    project_name: str = ""
    styling_level: str = "basic"
    media: list[MediaClip] = field(default_factory=list)   # the clips track (video lane under the titles)


def _gap_frames(project: Project, rate: Rate) -> list[tuple[int, int]]:
    out = []
    for g in sorted(project.gaps, key=lambda g: g.start):
        a, b = rate.frames(g.start), rate.frames(g.end)
        if b > a:
            if out and a <= out[-1][1]:
                out[-1] = (out[-1][0], max(out[-1][1], b))
            else:
                out.append((a, b))
    return out


def _cut_by_gaps(s: int, e: int, gaps: list[tuple[int, int]]) -> tuple[int, int]:
    for a, b in gaps:
        if s >= a and s < b:          # starts inside a gap -> start after it
            s = b
        if s < a < e:                 # runs into a gap -> stop at its start
            e = a
    return s, e


def song_path(project: Project) -> str:
    a = project.audio or {}
    for key in ("song_source", "song_wav"):
        if a.get(key) and Path(a[key]).exists():
            return str(Path(a[key]).resolve())
    return str(a.get("song_source") or a.get("song_wav") or "song.wav")


def song_duration(project: Project) -> float:
    a = project.audio or {}
    if a.get("duration_s"):
        return float(a["duration_s"])
    if project.analysis.get("duration"):
        return float(project.analysis["duration"])
    ends = [w.end for w in project.words] + [g.end for g in project.gaps]
    return (max(ends) + 2.0) if ends else 10.0


def media_path(project_dir: Path | None, path: str) -> str:
    p = Path(path)
    if not p.is_absolute() and project_dir is not None:
        p = Path(project_dir) / p
    return str(p.resolve()) if p.exists() else str(p)


def media_plan(project: Project, rate: Rate, dur_f: int, project_dir: Path | None = None,
               layout: str = "16:9") -> tuple[list[MediaClip], list[tuple[int, int]]]:
    """Clips track -> frame-snapped media clips (never inside gaps, never overlapping) + ranges without titles."""
    gaps = _gap_frames(project, rate)
    out: list[MediaClip] = []
    hidden: list[tuple[int, int]] = []
    for c in sorted(getattr(project, "clips", []) or [], key=lambda c: c.start):
        s_f, e_f = rate.frames(c.start), min(dur_f, rate.frames(c.end))
        s_f, e_f = _cut_by_gaps(s_f, e_f, gaps)
        if out and s_f < out[-1].end_frame:
            s_f = out[-1].end_frame
        if e_f <= s_f:
            continue
        path = (c.info.get("paths") or {}).get(layout) or c.path   # rendered clips: one video per layout
        out.append(MediaClip(c.id, c.name or Path(c.path).stem, media_path(project_dir, path), s_f, e_f,
                             rate.frames(c.in_point), c.hide_lyrics))
        if c.hide_lyrics:
            hidden.append((s_f, e_f))
    return out, hidden


def build_plan(project: Project, layout: str = "16:9", beat_markers: str = "downbeats",
               level: str | None = None) -> Plan:
    cfg = project.settings
    rate = Rate.of(cfg.fps)
    fr = lay.frame(layout, cfg.width, cfg.height)
    level = level or cfg.styling_level
    gaps = _gap_frames(project, rate)
    dur_f = rate.frames(song_duration(project))
    off = cfg.sync_offset_ms / 1000.0
    blocks = [b for b in project.blocks if project.block_words(b)]
    spans = [project.block_span(b) for b in blocks]
    warnings: list[str] = []

    raw: list[tuple[int, int]] = []
    for i, (s, e) in enumerate(spans):
        start = s + off - cfg.pre_roll_ms / 1000.0
        if cfg.hold_until_next and i + 1 < len(spans):
            end = spans[i + 1][0] + off - cfg.pre_roll_ms / 1000.0
        elif cfg.fade_after_ms > 0:
            end = e + off + cfg.fade_after_ms / 1000.0
        else:
            end = e + off + cfg.post_roll_ms / 1000.0
        if cfg.hold_until_next and i + 1 == len(spans):
            end = e + off + max(cfg.post_roll_ms, cfg.fade_after_ms, 1000.0) / 1000.0
        raw.append((max(0, rate.frames(start)), min(dur_f, rate.frames(end))))

    media, hidden = media_plan(project, rate, dur_f, layout=layout)
    # titles avoid instrumental gaps AND clips that replace the lyrics ("hide lyrics")
    no_text = sorted(gaps + hidden)
    clips: list[Clip] = []
    for i, (b, (s_f, e_f)) in enumerate(zip(blocks, raw)):
        mid = rate.frames((spans[i][0] + spans[i][1]) / 2 + off)
        if any(a <= mid < z for a, z in hidden):   # sung during a clip that replaces the lyrics
            warnings.append(f"block {b.id} is replaced by a clip (not shown as text)")
            continue
        s_f, e_f = _cut_by_gaps(s_f, e_f, no_text)
        if e_f <= s_f:  # entirely inside a gap (or empty): never revive it after the gap
            warnings.append(f"block {b.id} dropped: it lies inside an instrumental gap or has no duration")
            continue
        if clips and s_f < clips[-1].end_frame:          # never overlap the previous clip
            clips[-1].end_frame = max(clips[-1].start_frame, s_f)
            if clips[-1].duration <= 0:
                warnings.append(f"block {clips[-1].block_id} dropped (no room)")
                clips.pop()
        next_start = raw[i + 1][0] if i + 1 < len(raw) else dur_f
        if e_f - s_f < cfg.min_clip_frames:              # extend forward if there is room
            limit = min(next_start, dur_f, *(a for a, _ in no_text if a >= s_f), s_f + cfg.min_clip_frames)
            e_f = max(e_f, limit)
        if e_f <= s_f:
            warnings.append(f"block {b.id} dropped: it lies inside an instrumental gap or has no duration")
            continue
        style = styling.style_for_block(project, b, level)
        font_px = style.size_px or cfg.font_size_px or lay.default_font_px(fr)
        text = display_text(project, b)
        lines = lay.balanced_wrap(text, font_px, fr.safe_width)
        y_from_top = style.position_y(layout) * fr.height
        x = {"left": -fr.safe_width / 2, "right": fr.safe_width / 2}.get(style.align, 0.0)
        words = [WordTiming(w.text, rate.frames(w.start + off), rate.frames(w.end + off)) for w in project.block_words(b)]
        clips.append(Clip(b.id, text, lines, s_f, e_f, style, int(font_px), round(x, 1),
                          round(fr.height / 2 - y_from_top, 1), words))

    markers: list[Marker] = []
    for sec in project.sections:
        markers.append(Marker(rate.frames(sec.start), sec.label.title(), "section", f"{sec.label} {sec.start:.2f}s"))
    beats_key = {"downbeats": "downbeats", "all": "beats"}.get(beat_markers)
    if beats_key:
        for i, t in enumerate(project.analysis.get(beats_key) or []):
            f = rate.frames(t)
            if any(a <= f < b for a, b in gaps):        # no beat markers inside gaps
                continue
            markers.append(Marker(f, f"Bar {i + 1}" if beats_key == "downbeats" else f"Beat {i + 1}",
                                  "downbeat" if beats_key == "downbeats" else "beat"))
    markers = sorted({(m.frame, m.kind): m for m in markers if 0 <= m.frame < dur_f}.values(), key=lambda m: m.frame)
    return Plan(layout, fr.width, fr.height, rate, tc_to_frames(cfg.start_timecode, rate), dur_f,
                song_path(project), clips, markers, gaps, warnings, project.name, level, media)


def check_plan(plan: Plan) -> list[str]:
    """Invariants every exporter relies on (used by tests and before writing files)."""
    problems = []
    prev = None
    for c in plan.clips:
        if c.duration <= 0:
            problems.append(f"{c.block_id}: empty clip")
        if prev and c.start_frame < prev.end_frame:
            problems.append(f"{c.block_id}: overlaps {prev.block_id}")
        for a, b in plan.gaps:
            if c.start_frame < b and c.end_frame > a:
                problems.append(f"{c.block_id}: inside instrumental gap {a}-{b}")
        if c.end_frame > plan.duration_frames:
            problems.append(f"{c.block_id}: ends after the song")
        for m in plan.media:
            if m.hide_lyrics and c.start_frame < m.end_frame and c.end_frame > m.start_frame:
                problems.append(f"{c.block_id}: shown during clip {m.clip_id}, which hides the lyrics")
        prev = c
    prev_m = None
    for m in plan.media:
        if m.duration <= 0:
            problems.append(f"clip {m.clip_id}: empty")
        if prev_m and m.start_frame < prev_m.end_frame:
            problems.append(f"clip {m.clip_id}: overlaps clip {prev_m.clip_id}")
        for a, b in plan.gaps:
            if m.start_frame < b and m.end_frame > a:
                problems.append(f"clip {m.clip_id}: inside instrumental gap {a}-{b}")
        prev_m = m
    return problems
