"""Audio inputs: conversion, A/B alignment check, instrumental stem, separation fallback."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .convert import SAMPLE_RATE, AudioError, Ffmpeg, cached_wav, file_hash

__all__ = ["PreparedAudio", "prepare_inputs", "AudioError", "Ffmpeg"]


@dataclass
class PreparedAudio:
    song_source: str
    song_wav: str               # Track A (timeline audio)
    vocals_wav: str             # what Whisper analyses
    instrumental_wav: str       # karaoke mode
    offset_ms: float = 0.0
    offset_confidence: float = 0.0
    compensated: bool = False
    vocals_source: str = "acapella"   # "acapella" | "separation:<backend>"
    duration_s: float = 0.0
    messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def prepare_inputs(song: Path, acapella: Path | None, cache_dir: Path, ffmpeg: Ffmpeg | None = None,
                   auto_compensate: bool = False, separators=None) -> PreparedAudio:
    """Convert inputs to 44.1 kHz wav, check A/B alignment, build/cached instrumental."""
    from . import align, stems, wavio

    ffmpeg = ffmpeg or Ffmpeg()
    cache_dir = Path(cache_dir)
    song_wav = cached_wav(Path(song), cache_dir, ffmpeg)
    song_data, sr = wavio.read(song_wav)
    duration = len(song_data) / sr
    msgs: list[str] = []

    if acapella is None:
        backends = separators if separators is not None else [stems.AudioSeparatorBackend(
            model_dir=cache_dir.parent / "models" / "separation"), stems.DemucsBackend()]
        v, inst, name = stems.separate_cached(song_wav, file_hash(song_wav), cache_dir, backends)
        msgs.append(f"No acapella given: vocals separated with {name} (cached).")
        return PreparedAudio(str(song), str(song_wav), str(v), str(inst), vocals_source=f"separation:{name}",
                             duration_s=duration, messages=msgs)

    aca_wav = cached_wav(Path(acapella), cache_dir, ffmpeg)
    aca_data, sr2 = wavio.read(aca_wav)
    if sr2 != sr:
        raise AudioError(f"Sample rates differ after conversion ({sr} vs {sr2})")
    off = align.estimate_offset(song_data, aca_data, sr)
    msgs.append(off.message())
    compensated = False
    key = f"{file_hash(song_wav)}-{file_hash(aca_wav)}-v{stems.STEM_VERSION}"
    if auto_compensate and off.significant and off.reliable:
        aca_data = align.compensate(aca_data, sr, off.offset_ms, length=len(song_data))
        aca_wav = wavio.write(cache_dir / "aligned" / f"acapella-{key}-{off.offset_ms:+.1f}ms.wav", aca_data, sr)
        compensated = True
        msgs.append(f"Acapella shifted by {-off.offset_ms:+.1f} ms to match the song.")
    else:
        aca_data = align.compensate(aca_data, sr, 0.0, length=len(song_data))

    inst_wav = cache_dir / "stems" / f"instrumental-{key}{'-comp' if compensated else ''}.wav"
    if not inst_wav.exists():
        res = stems.subtract_vocals(song_data, aca_data)
        wavio.write(inst_wav, res.instrumental, sr)
        (inst_wav.with_suffix(".json")).write_text(json.dumps({"gain": res.gain, "residual": res.residual_ratio}))
        if res.residual_ratio > 0.98:
            msgs.append("Note: subtracting the acapella barely changed the song - the instrumental may still "
                        "contain vocals (is the acapella from the same master?).")
    return PreparedAudio(str(song), str(song_wav), str(aca_wav), str(inst_wav), off.offset_ms, off.confidence,
                         compensated, duration_s=duration, messages=msgs)


def main(argv: list[str]) -> int:
    """lyric2resolve audio-check --song A [--acapella B] [--compensate]"""
    import argparse

    from lyric2resolve import paths
    from lyric2resolve.settings import load_settings
    from lyric2resolve.setup_tools import FFMPEG_HELP, find_tool

    ap = argparse.ArgumentParser(prog="lyric2resolve audio-check")
    ap.add_argument("--song", type=Path, required=True)
    ap.add_argument("--acapella", type=Path)
    ap.add_argument("--compensate", action="store_true", help="auto-compensate a detected offset")
    args = ap.parse_args(argv)
    exe = find_tool("ffmpeg", load_settings()[0].ffmpeg_path)
    if not exe:
        print(FFMPEG_HELP)
        return 1
    try:
        res = prepare_inputs(args.song, args.acapella, paths.ensure_data_dir() / "cache", Ffmpeg(str(exe)),
                             auto_compensate=args.compensate)
    except (AudioError, RuntimeError) as exc:
        print(f"ERROR: {exc}")
        return 1
    for m in res.messages:
        print(m)
    print(json.dumps(res.to_dict(), indent=2))
    return 0
