"""Transcription / forced alignment of the acapella -> project words + initial blocks."""

from __future__ import annotations

import re
from pathlib import Path

from lyric2resolve import project as proj

from .engine import Engine, EngineOptions, FakeEngine, StableTsEngine, Transcript, TranscriptWord

__all__ = ["Engine", "EngineOptions", "FakeEngine", "StableTsEngine", "Transcript", "build_project",
           "clean_lyrics", "assign_lines"]


def clean_lyrics(text: str) -> list[str]:
    """Keep the user's line breaks; drop empty lines and [section] tags like [Chorus]."""
    lines = []
    for raw in (text or "").splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if not line or re.fullmatch(r"[\[(].*[\])]", line):
            continue
        lines.append(line)
    return lines


def assign_lines(words: list[TranscriptWord], lines: list[str]) -> list[int]:
    """Map aligned words back to lyric lines by counting whitespace tokens per line.

    Falls back to the engine's segment index when the counts don't match.
    """
    counts = [len(ln.split()) for ln in lines]
    if sum(counts) != len(words):
        return [w.segment for w in words]
    out: list[int] = []
    for li, n in enumerate(counts):
        out.extend([li] * n)
    return out


def build_project(transcript: Transcript, name: str, lyrics: str | None = None,
                  audio: dict | None = None, settings: proj.ProjectSettings | None = None) -> proj.Project:
    lines = clean_lyrics(lyrics) if lyrics else []
    line_idx = assign_lines(transcript.words, lines) if lines else [w.segment for w in transcript.words]
    raw = [{"text": w.text, "start": w.start, "end": w.end, "confidence": w.confidence, "line": li}
           for w, li in zip(transcript.words, line_idx)]
    words = proj.make_words(raw)
    p = proj.Project(name=name, language=transcript.language, lyrics=lyrics, audio=audio or {},
                     transcription=dict(transcript.params, mode=transcript.mode),
                     words=words, blocks=proj.blocks_by_line(words),
                     settings=settings or proj.ProjectSettings())
    return p


def run(vocals_wav: Path, engine: Engine, name: str, lyrics: str | None = None, audio: dict | None = None,
        settings: proj.ProjectSettings | None = None) -> proj.Project:
    lines = clean_lyrics(lyrics) if lyrics else []
    if lines:
        transcript = engine.align(str(vocals_wav), "\n".join(lines))
    else:
        transcript = engine.transcribe(str(vocals_wav))
    if not transcript.words:
        raise RuntimeError("No words were recognised in the acapella. Is it the right file / does it contain vocals?")
    return build_project(transcript, name, lyrics if lines else None, audio, settings)


def engine_from_settings(model: str | None = None, language: str | None = None) -> StableTsEngine:
    from lyric2resolve import paths
    from lyric2resolve.settings import load_settings

    s, _ = load_settings()
    backend = choose_backend(s.device)
    device = "cpu" if s.device == "mps" else s.device   # CTranslate2 (faster-whisper) has no Apple GPU support
    return StableTsEngine(EngineOptions(
        model=model or s.whisper_model, device=device,
        compute_type=s.compute_type if device == "cuda" else "int8",
        language=language or s.language or None, vad_threshold=float(s.vad_threshold),
        model_dir=str(paths.ensure_data_dir() / "models" / "whisper"), backend=backend))


def choose_backend(device: str, platform: str | None = None, has_mlx: bool | None = None) -> str:
    """Apple Silicon (device 'mps') -> MLX when installed; everything else -> faster-whisper."""
    import importlib.util
    import sys

    platform = platform or sys.platform
    if has_mlx is None:
        has_mlx = importlib.util.find_spec("mlx_whisper") is not None
    return "mlx" if platform == "darwin" and device == "mps" and has_mlx else "faster-whisper"


def main(argv: list[str]) -> int:
    """lyric2resolve transcribe --song A --acapella B [--lyrics L] [--model M] [--language xx] [--out DIR]"""
    import argparse

    from lyric2resolve import paths
    from lyric2resolve.audio import AudioError, Ffmpeg, prepare_inputs
    from lyric2resolve.settings import load_settings
    from lyric2resolve.setup_tools import FFMPEG_HELP, find_tool

    ap = argparse.ArgumentParser(prog="lyric2resolve transcribe")
    ap.add_argument("--song", type=Path, required=True)
    ap.add_argument("--acapella", type=Path)
    ap.add_argument("--lyrics", type=Path, help="text file; keeps your line breaks (forced alignment)")
    ap.add_argument("--model")
    ap.add_argument("--language", help="e.g. en, nl (default: auto-detect)")
    ap.add_argument("--compensate", action="store_true", help="auto-compensate an A/B offset")
    ap.add_argument("--name")
    ap.add_argument("--out", type=Path, help="project folder (default: data folder/projects/<name>)")
    args = ap.parse_args(argv)

    settings, _ = load_settings()
    exe = find_tool("ffmpeg", settings.ffmpeg_path)
    if not exe:
        print(FFMPEG_HELP)
        return 1
    name = args.name or args.song.stem
    out_dir = args.out or (paths.ensure_data_dir() / "projects" / name)
    try:
        prepared = prepare_inputs(args.song, args.acapella, paths.ensure_data_dir() / "cache", Ffmpeg(str(exe)),
                                  auto_compensate=args.compensate)
        for m in prepared.messages:
            print(m)
        lyrics = args.lyrics.read_text(encoding="utf-8") if args.lyrics else None
        print("Loading Whisper and transcribing (first run downloads the model)...")
        project = run(Path(prepared.vocals_wav), engine_from_settings(args.model, args.language), name, lyrics,
                      prepared.to_dict(), proj.ProjectSettings(fps=settings.default_fps,
                                                               start_timecode=settings.start_timecode,
                                                               width=settings.width, height=settings.height,
                                                               layouts=list(settings.layouts),
                                                               styling_level=settings.styling_level))
    except (AudioError, RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}")
        return 1
    path = proj.save(project, out_dir / proj.PROJECT_FILE)
    print(f"{len(project.words)} words, {len(project.blocks)} blocks, language {project.language or '?'}")
    print(f"Project saved: {path}")
    return 0
