"""Music analysis, instrumental gap detection and the rough-cut sanity check."""

from __future__ import annotations

from pathlib import Path

from lyric2resolve import project as proj

from . import gaps, sanity

__all__ = ["analyze_project", "gaps", "sanity"]


def analyze_project(project: proj.Project, song=None, vocals=None, sr: int = 44100,
                    replace_sections: bool = False) -> list[sanity.Flag]:
    """Fill project.analysis/sections/gaps from audio arrays; return sanity flags.

    song/vocals: arrays (samples, channels) or None to skip that part.
    """
    activity = None
    duration = float(project.audio.get("duration_s") or 0.0)
    if song is not None:
        from .music import analyze

        res = analyze(song, sr)
        duration = res.duration
        project.analysis = res.to_dict()
        if replace_sections or not project.sections:
            project.sections = [proj.Section(f"s{i + 1:04d}", s["label"], s["start"], s["end"])
                                for i, s in enumerate(res.sections)]
    if vocals is not None:
        activity = gaps.vocal_activity(vocals, sr)
        project.analysis["vocal_activity"] = activity
        duration = duration or len(vocals) / sr
    if not duration and project.words:
        duration = project.words[-1].end
    found = gaps.detect_gaps(project.words, duration, project.settings.min_gap_s, activity)
    gaps.apply_auto_gaps(project, found)
    return sanity.check(project, activity)


def main(argv: list[str]) -> int:
    """lyric2resolve analyze path/to/project.json [--replace-sections]"""
    import argparse

    from lyric2resolve.audio import wavio

    ap = argparse.ArgumentParser(prog="lyric2resolve analyze")
    ap.add_argument("project", type=Path)
    ap.add_argument("--replace-sections", action="store_true")
    args = ap.parse_args(argv)
    p = proj.load(args.project)
    song = vocals = None
    sr = 44100
    if p.audio.get("song_wav") and Path(p.audio["song_wav"]).exists():
        song, sr = wavio.read(Path(p.audio["song_wav"]))
    if p.audio.get("vocals_wav") and Path(p.audio["vocals_wav"]).exists():
        vocals, sr = wavio.read(Path(p.audio["vocals_wav"]))
    flags = analyze_project(p, song, vocals, sr, args.replace_sections)
    proj.save(p, args.project)
    a = p.analysis
    if a.get("bpm"):
        print(f"BPM {a['bpm']}, key {a['key']}, {len(a['beats'])} beats, {len(p.sections)} sections")
    for s in p.sections:
        print(f"  {s.label:8} {s.start:7.2f} - {s.end:7.2f}")
    print(f"{len(p.gaps)} instrumental gaps, {len(flags)} flagged words")
    for f in flags[:20]:
        print(f"  [{f.kind}] {f.message}")
    return 0
