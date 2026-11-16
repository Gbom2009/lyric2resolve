"""End-to-end CLI: one song -> project + exports (+ optional rendered visuals).

    lyric2resolve --song full.wav --acapella vocals.wav [--lyrics lyrics.txt] [--sections sections.yaml]
                  [--granularity line] [--fps 25] [--model large-v3] [--language en]
                  [--formats fcpxml resolve srt_csv_edl] [--render-preset standard [--template tunnel]]
                  [--out ./out] [--name "My song"] [--open-editor]

Without --acapella the vocals are separated from the song (slower). Other commands: `lyric2resolve editor`,
`batch`, `assets sync`, `render`, `claude`, `check-update`, `update` ... (see README.md).
"""

from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_FORMATS = ["fcpxml", "resolve", "srt_csv_edl"]


def parser() -> argparse.ArgumentParser:
    from lyric2resolve.render import presets
    from lyric2resolve.visuals import mapping

    ap = argparse.ArgumentParser(prog="lyric2resolve", description="Song + acapella -> Resolve lyric timeline.")
    ap.add_argument("--song", type=Path, required=True, help="full song (mp3/wav/flac/m4a) - goes on the timeline")
    ap.add_argument("--acapella", type=Path, help="acapella; the only file Whisper listens to")
    ap.add_argument("--lyrics", type=Path, help="lyrics .txt (forced alignment; your line breaks are kept)")
    ap.add_argument("--sections", type=Path, help="sections.yaml: block preset per section")
    ap.add_argument("--granularity", choices=["word", "line", "phrase", "auto"], help="default block preset")
    ap.add_argument("--fps", type=float, help="timeline fps (23.976/24/25/29.97/30/50/60)")
    ap.add_argument("--model", help="Whisper model (default from settings: large-v3)")
    ap.add_argument("--language", help="e.g. en, nl (default: auto-detect)")
    ap.add_argument("--formats", nargs="+", default=DEFAULT_FORMATS, help="fcpxml resolve srt_csv_edl")
    ap.add_argument("--render-preset", choices=list(presets.PRESETS), help="also render audio-reactive visuals")
    ap.add_argument("--template", default="spectrum_bars", choices=mapping.TEMPLATES)
    ap.add_argument("--compensate", action="store_true", help="auto-compensate an A/B offset")
    ap.add_argument("--no-analyze", action="store_true", help="skip BPM/sections/gaps analysis")
    ap.add_argument("--name", help="project name (default: song file name)")
    ap.add_argument("--out", type=Path, help="output folder (default: data folder/projects)")
    ap.add_argument("--open-editor", action="store_true", help="open the result in the browser editor")
    return ap


def main(argv: list[str], engine=None, ffmpeg=None, render=None) -> int:
    """engine/ffmpeg/render are injectable for tests (FakeEngine, fake ffmpeg runner, fake render)."""
    from lyric2resolve import batch, paths
    from lyric2resolve.audio import Ffmpeg
    from lyric2resolve.settings import load_settings
    from lyric2resolve.setup_tools import FFMPEG_HELP, find_tool

    a = parser().parse_args(argv)
    s, warnings = load_settings()
    for w in warnings:
        print(w)
    if ffmpeg is None:
        exe = find_tool("ffmpeg", s.ffmpeg_path)
        if not exe:
            print(FFMPEG_HELP)
            return 1
        ffmpeg = Ffmpeg(str(exe))
    if engine is None:
        from lyric2resolve.transcription import engine_from_settings

        engine = engine_from_settings(a.model, a.language)
    data = paths.ensure_data_dir()
    out = a.out or data / "projects"
    job = batch.BatchJob(str(a.song), str(a.acapella) if a.acapella else None, str(a.lyrics) if a.lyrics else None,
                         str(a.sections) if a.sections else None, a.name)
    res = batch.run_song(job, out, settings=s, engine=engine, ffmpeg=ffmpeg, cache_dir=data / "cache",
                         formats=a.formats, granularity=a.granularity, fps=a.fps, analyze=not a.no_analyze,
                         compensate=a.compensate, install_resolve_script=True)
    for m in res.messages:
        if m and not m.startswith("Traceback"):
            print(m.splitlines()[0])
    if not res.ok:
        print(f"ERROR: {res.error}")
        return 1
    print(f"\nProject: {res.project}")
    for f in res.files:
        print(f"  {f}")
    code = 0
    if a.render_preset:
        render = render or __import__("lyric2resolve.render", fromlist=["render_project"]).render_project
        try:
            rep = render(Path(res.project), template=a.template, preset_name=a.render_preset)
            for v in rep.videos:
                print(f"  video: {v}")
            for m in rep.messages:
                print(m)
            if not rep.ok:
                code = 3
        except (RuntimeError, ValueError, FileNotFoundError) as exc:
            print(f"Visuals not rendered: {exc}\n(The project and exports above are fine.)")
            code = 3
    print("\nNext: open it in the editor (`lyric2resolve editor --project \"%s\"`) to review, then export again." %
          res.project)
    if a.open_editor:
        from lyric2resolve.editor.app import main as editor_main

        return editor_main(["--project", res.project])
    return code


def wants_pipeline(argv: list[str]) -> bool:
    """`lyric2resolve --song ...` (option style) goes here; sub-commands go elsewhere."""
    return bool(argv) and argv[0].startswith("--") and argv[0] not in ("--help", "-h") and "--song" in argv
