"""Batch mode: a simple queue of songs through the pipeline (convert -> transcribe -> analyze -> blocks -> export).

    lyric2resolve batch <folder | queue.yaml> [--out DIR] [--formats fcpxml resolve srt_csv_edl]
                        [--granularity line] [--model large-v3] [--no-analyze] [--dry-run]

Folder mode pairs files by name: `Song.mp3` + `Song (Acapella).wav` / `Song - acapella.wav` / `Song_vocals.flac`;
an optional `Song.txt` holds the lyrics (forced alignment, your line breaks are kept). A song without an
acapella is separated automatically (slower). queue.yaml:

    jobs:
      - song: songs/One.mp3
        acapella: songs/One acapella.wav   # optional
        lyrics: songs/One.txt              # optional
        sections: sections.yaml            # optional (preset per section)
        name: One                          # optional

One failing song never stops the queue; `batch_report.md` in the output folder lists the result per song.
`run_song` is also the single-song pipeline of the end-to-end CLI.
"""

from __future__ import annotations

import re
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from lyric2resolve import project as proj

AUDIO_EXT = (".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".aif", ".aiff")
# "acapella"/"vocals"/"vox" as a separate word; "_" counts as a separator (Song_vocals.wav)
_VOCAL_TOKEN = re.compile(r"(?:^|[\s_\-.(\[]+)(a\s*-?\s*cap+ella|vocals?|vox|voice)(?=$|[\s_\-.)\]])[)\]]*", re.I)


@dataclass
class BatchJob:
    song: str
    acapella: str | None = None
    lyrics: str | None = None
    sections: str | None = None
    name: str | None = None

    @property
    def title(self) -> str:
        return self.name or Path(self.song).stem


@dataclass
class JobResult:
    name: str
    ok: bool
    project: str = ""
    files: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    error: str = ""
    seconds: float = 0.0


def _base(stem: str) -> str:
    return re.sub(r"\s+", " ", _VOCAL_TOKEN.sub("", stem)).strip(" -_").lower()


def find_jobs(folder: Path) -> list[BatchJob]:
    """Pair songs and acapellas in a folder by file name (see module docstring)."""
    folder = Path(folder)
    files = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in AUDIO_EXT)
    plain = {p.stem.strip().lower() for p in files if not _VOCAL_TOKEN.search(p.stem)} | \
        {_base(p.stem) for p in files if not _VOCAL_TOKEN.search(p.stem)}
    # a "vocals" file only counts as an acapella when a song with the same base name exists
    # ("The Voice.mp3" alone is a song)
    vocals = {_base(p.stem): p for p in files if _VOCAL_TOKEN.search(p.stem) and _base(p.stem) in plain}
    jobs = []
    for p in files:
        if p in vocals.values():
            continue
        lyr = p.with_suffix(".txt")
        aca = vocals.get(p.stem.strip().lower()) or vocals.get(_base(p.stem))
        jobs.append(BatchJob(str(p), str(aca) if aca else None, str(lyr) if lyr.is_file() else None))
    return jobs


def load_queue(path: Path) -> list[BatchJob]:
    import yaml

    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    items = data.get("jobs", []) if isinstance(data, dict) else data
    jobs = []
    for i, it in enumerate(items or []):
        if not isinstance(it, dict) or not it.get("song"):
            raise ValueError(f"{path}: job {i + 1} needs at least 'song'")

        def rel(key: str) -> str | None:
            v = it.get(key)
            return str((path.parent / v).resolve()) if v else None

        jobs.append(BatchJob(rel("song"), rel("acapella"), rel("lyrics"), rel("sections"), it.get("name")))
    return jobs


def jobs_from(source: Path) -> list[BatchJob]:
    source = Path(source)
    if source.is_dir():
        return find_jobs(source)
    if source.suffix.lower() in (".yaml", ".yml"):
        return load_queue(source)
    raise ValueError(f"{source}: give a folder with songs or a queue .yaml file")


def project_settings(s) -> proj.ProjectSettings:
    return proj.ProjectSettings(fps=s.default_fps, start_timecode=s.start_timecode, width=s.width, height=s.height,
                                layouts=list(s.layouts), styling_level=s.styling_level)


def run_song(job: BatchJob, out_root: Path, *, settings, engine, ffmpeg, cache_dir: Path,
             formats: list[str] | None = None, granularity: str | None = None, fps: float | None = None,
             analyze: bool = True, compensate: bool = False, install_resolve_script: bool = False,
             do_export: bool = True, overwrite: bool = False, log: Callable[[str], None] = print) -> JobResult:
    """One song through the whole pipeline. Never raises: errors come back in the result."""
    from lyric2resolve import export as ex
    from lyric2resolve import transcription
    from lyric2resolve.audio import prepare_inputs
    from lyric2resolve.editor import presets

    t0 = time.perf_counter()
    res = JobResult(job.title, False)
    try:
        for label, f in (("song", job.song), ("acapella", job.acapella), ("lyrics", job.lyrics),
                         ("sections", job.sections)):
            if f and not Path(f).is_file():
                raise FileNotFoundError(f"{label} file not found: {f}")
        log(f"[{job.title}] converting audio + checking alignment…")
        prepared = prepare_inputs(Path(job.song), Path(job.acapella) if job.acapella else None, cache_dir, ffmpeg,
                                  auto_compensate=compensate)
        res.messages += prepared.messages
        lyrics = Path(job.lyrics).read_text(encoding="utf-8") if job.lyrics else None
        log(f"[{job.title}] {'aligning lyrics' if lyrics else 'transcribing'}…")
        ps = project_settings(settings)
        if fps:
            ps.fps = float(fps)
        try:
            p = transcription.run(Path(prepared.vocals_wav), engine, job.title, lyrics, prepared.to_dict(), ps)
        finally:
            if hasattr(engine, "close") and getattr(engine, "close_after_use", True):
                engine.close()  # give the memory back (8 GB Macs: Blender, analysis)
        if getattr(engine, "fallback_reason", ""):
            res.messages.append("WARNING: " + engine.fallback_reason)
            log(f"[{job.title}] WARNING: {engine.fallback_reason}")
        if analyze:
            from lyric2resolve.analysis import analyze_project
            from lyric2resolve.audio import wavio

            log(f"[{job.title}] analysing music (BPM, sections, gaps)…")
            song, sr = wavio.read(Path(prepared.song_wav))
            vocals, _ = wavio.read(Path(prepared.vocals_wav))
            flags = analyze_project(p, song, vocals, sr)
            if flags:
                res.messages.append(f"{len(flags)} words flagged for review (open the project in the editor)")
        if job.sections:
            presets.apply_sections_config(p, presets.load_sections_yaml(Path(job.sections)))
        presets.apply_presets(p, granularity)
        folder = Path(out_root) / ex.safe_name(job.title)
        if (folder / proj.PROJECT_FILE).exists() and not overwrite:
            raise FileExistsError(f"a project '{job.title}' already exists in {folder} (your edits are kept). "
                                  "Use --overwrite to replace it, or rename the song.")
        path = proj.save(p, folder / proj.PROJECT_FILE)
        res.project = str(path)
        if not do_export:
            res.ok = True
            res.seconds = round(time.perf_counter() - t0, 1)
            log(f"[{job.title}] done ({res.seconds} s)")
            return res
        log(f"[{job.title}] exporting {', '.join(formats or ['fcpxml'])}…")
        out = ex.export(p, folder / "export", formats or ["fcpxml"],
                        install_resolve_script=install_resolve_script and "resolve" in (formats or []))
        if out.get("resolve_script"):
            res.messages.append(f"Resolve script installed: {out['resolve_script']} (Workspace > Scripts)")
        res.files = out["files"]
        res.messages += out["warnings"]
        res.ok = True
    except Exception as exc:  # one bad song must not stop the queue
        res.error = f"{type(exc).__name__}: {exc}"
        res.messages.append(traceback.format_exc(limit=3))
    res.seconds = round(time.perf_counter() - t0, 1)
    log(f"[{job.title}] {'done' if res.ok else 'FAILED: ' + res.error} ({res.seconds} s)")
    return res


def report_markdown(results: list[JobResult]) -> str:
    ok = sum(r.ok for r in results)
    lines = ["# Batch report", "", f"{ok} of {len(results)} songs done.", "",
             "| song | result | project | files | time |", "|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r.name} | {'✅' if r.ok else '❌ ' + r.error.replace('|', '/')} | {r.project} | "
                     f"{len(r.files)} | {r.seconds} s |")
    for r in results:
        notes = [m for m in r.messages if m and not m.startswith("Traceback")]
        if notes:
            lines += ["", f"## {r.name}", *[f"- {m.splitlines()[0]}" for m in notes]]
    return "\n".join(lines) + "\n"


def run_batch(jobs: list[BatchJob], out_root: Path, **kw) -> list[JobResult]:
    out_root = Path(out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    results = []
    for i, job in enumerate(jobs, 1):
        kw.get("log", print)(f"=== {i}/{len(jobs)}: {job.title} ===")
        results.append(run_song(job, out_root, **kw))
        (out_root / "batch_report.md").write_text(report_markdown(results), encoding="utf-8")  # after every song
    return results


def main(argv: list[str]) -> int:
    import argparse
    import json

    from lyric2resolve import paths
    from lyric2resolve.audio import Ffmpeg
    from lyric2resolve.settings import load_settings
    from lyric2resolve.setup_tools import FFMPEG_HELP, find_tool

    ap = argparse.ArgumentParser(prog="lyric2resolve batch")
    ap.add_argument("source", type=Path, help="folder with songs (+ acapellas) or a queue .yaml")
    ap.add_argument("--out", type=Path, help="output folder (default: data folder/projects)")
    ap.add_argument("--formats", nargs="+", default=["fcpxml", "srt_csv_edl"])
    ap.add_argument("--granularity", choices=["word", "line", "phrase", "auto"])
    ap.add_argument("--model")
    ap.add_argument("--language")
    ap.add_argument("--fps", type=float)
    ap.add_argument("--no-analyze", action="store_true")
    ap.add_argument("--compensate", action="store_true", help="auto-compensate A/B offsets")
    ap.add_argument("--dry-run", action="store_true", help="only list the jobs")
    ap.add_argument("--overwrite", action="store_true", help="replace existing projects with the same name")
    a = ap.parse_args(argv)
    try:
        jobs = jobs_from(a.source)
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}")
        return 1
    if not jobs:
        print("No songs found.")
        return 1
    for j in jobs:
        print(f"- {j.title}: song={Path(j.song).name}, acapella={Path(j.acapella).name if j.acapella else '(separate)'}"
              f"{', lyrics' if j.lyrics else ''}")
    if a.dry_run:
        return 0
    s, _ = load_settings()
    exe = find_tool("ffmpeg", s.ffmpeg_path)
    if not exe:
        print(FFMPEG_HELP)
        return 1
    from lyric2resolve.transcription import engine_from_settings

    data = paths.ensure_data_dir()
    out = a.out or data / "projects"
    results = run_batch(jobs, out, settings=s, engine=engine_from_settings(a.model, a.language),
                        ffmpeg=Ffmpeg(str(exe)), cache_dir=data / "cache", formats=a.formats,
                        granularity=a.granularity, fps=a.fps, analyze=not a.no_analyze, compensate=a.compensate,
                        install_resolve_script=True, overwrite=a.overwrite)
    print(f"\n{sum(r.ok for r in results)}/{len(results)} done. Report: {out / 'batch_report.md'}")
    (out / "batch_report.json").write_text(json.dumps([asdict(r) for r in results], indent=2), encoding="utf-8")
    return 0 if all(r.ok for r in results) else 2
