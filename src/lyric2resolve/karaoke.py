"""Karaoke mode data: word timings per line for a saved project + saved playlists (queues).

Everything is read from local project files, so karaoke works fully offline.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from lyric2resolve import paths
from lyric2resolve import project as proj
from lyric2resolve.editor.presets import display_text

PLAYLIST_FILE = "karaoke_playlists.json"


def karaoke_data(p: proj.Project) -> dict:
    """Lines (= blocks) with word timings in seconds from the song start, gaps, audio availability.

    The global sync offset is applied so karaoke matches the exported video.
    """
    off = p.settings.sync_offset_ms / 1000.0
    lines = []
    for b in p.blocks:
        words = p.block_words(b)
        if not words:
            continue
        display = display_text(p, b)
        parts = display.split()
        # if the user overrode the block text and the word count differs, highlight per line instead
        per_word = len(parts) == len(words)
        lines.append({
            "id": b.id,
            "start": round(words[0].start + off, 3),
            "end": round(words[-1].end + off, 3),
            "text": display,
            "words": [{"text": parts[i] if per_word else w.text, "start": round(w.start + off, 3),
                       "end": round(max(w.end, w.start + 0.05) + off, 3)} for i, w in enumerate(words)]
            if per_word else [{"text": display, "start": round(words[0].start + off, 3),
                               "end": round(words[-1].end + off, 3)}],
        })
    lines.sort(key=lambda x: x["start"])
    audio = p.audio or {}
    has = {k: bool(audio.get(v)) and Path(audio[v]).is_file()
           for k, v in (("song", "song_wav"), ("vocals", "vocals_wav"), ("instrumental", "instrumental_wav"))}
    duration = float(audio.get("duration_s") or (lines[-1]["end"] + 3 if lines else 0))
    return {"name": p.name, "duration": duration, "lines": lines,
            "gaps": [{"start": g.start, "end": g.end} for g in sorted(p.gaps, key=lambda g: g.start)],
            "audio": has, "bpm": p.analysis.get("bpm")}


def line_at(lines: list[dict], t: float) -> tuple[int, int]:
    """(index of the line being sung or -1, index of the next upcoming line or -1) at time t."""
    current, upcoming = -1, -1
    for i, ln in enumerate(lines):
        if ln["start"] <= t < ln["end"] + 0.25:
            current = i
        if ln["start"] > t and upcoming == -1:
            upcoming = i
    return current, upcoming


# ------------------------------------------------------------------ playlists
@dataclass
class Playlists:
    playlists: dict[str, list[str]] = field(default_factory=lambda: {"Karaoke night": []})
    current: str = "Karaoke night"

    def to_dict(self) -> dict:
        return {"playlists": self.playlists, "current": self.current}


def playlists_path(settings_dir: Path | None = None) -> Path:
    return (settings_dir or paths.settings_dir()) / PLAYLIST_FILE


def load_playlists(settings_dir: Path | None = None) -> Playlists:
    try:
        data = json.loads(playlists_path(settings_dir).read_text(encoding="utf-8"))
        pl = {str(k): [str(x) for x in v] for k, v in (data.get("playlists") or {}).items() if isinstance(v, list)}
        if not pl:
            return Playlists()
        cur = data.get("current") if data.get("current") in pl else next(iter(pl))
        return Playlists(pl, cur)
    except (OSError, ValueError, AttributeError):
        return Playlists()


def save_playlists(pls: Playlists, settings_dir: Path | None = None) -> Path:
    if not pls.playlists:
        raise ValueError("at least one playlist is required")
    if pls.current not in pls.playlists:
        raise ValueError(f"current playlist {pls.current!r} does not exist")
    from lyric2resolve.paths import atomic_write_text

    return atomic_write_text(playlists_path(settings_dir), json.dumps(pls.to_dict(), indent=1))
