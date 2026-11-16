"""ffmpeg conversion to 44.1 kHz wav, behind a small interface, with a content-hash cache."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

SAMPLE_RATE = 44100
SUPPORTED = (".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg", ".aiff", ".aif")


class AudioError(RuntimeError):
    pass


def file_hash(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()[:16]


Runner = Callable[[list[str]], tuple[int, str]]  # -> (returncode, stderr)


def default_runner(cmd: list[str]) -> tuple[int, str]:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform.startswith("win") else 0
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              creationflags=flags)
    except FileNotFoundError:
        return 127, f"{cmd[0]} not found"
    return proc.returncode, proc.stderr


@dataclass
class Ffmpeg:
    exe: str = "ffmpeg"
    runner: Runner = default_runner

    def wav_command(self, src: Path, dst: Path, sample_rate: int = SAMPLE_RATE) -> list[str]:
        # stereo, 16-bit PCM wav, no metadata; -vn drops cover art streams in mp3/m4a
        return [self.exe, "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-vn",
                "-ac", "2", "-ar", str(sample_rate), "-c:a", "pcm_s16le", "-map_metadata", "-1", str(dst)]

    def to_wav(self, src: Path, dst: Path, sample_rate: int = SAMPLE_RATE) -> Path:
        src = Path(src)
        if not src.is_file():
            raise AudioError(f"Audio file not found: {src}")
        if src.suffix.lower() not in SUPPORTED:
            raise AudioError(f"Unsupported audio type {src.suffix!r}; use one of {', '.join(SUPPORTED)}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.stem + ".part.wav")
        code, err = self.runner(self.wav_command(src, tmp, sample_rate))
        if code != 0 or not tmp.exists():
            tmp.unlink(missing_ok=True)
            hint = ""
            if "No such file or directory" in err and src.is_file():
                # Python sees the file, ffmpeg does not: e.g. Microsoft Store Python's AppData redirection
                from lyric2resolve.paths import store_python

                hint = ("\nPython can see this file but ffmpeg cannot. " + (
                    "This Python is the Microsoft Store version, which hides files it writes in AppData from other "
                    "programs. Restart the launcher (the app then uses a folder all programs can see) or install "
                    "Python from python.org and run install.bat again." if store_python() else
                    "Check that the file is not on a disconnected/cloud-only drive and that ffmpeg is a normal "
                    "Windows ffmpeg (winget install Gyan.FFmpeg)."))
            raise AudioError(f"ffmpeg could not convert {src.name}: {err.strip()[-500:]}{hint}")
        tmp.replace(dst)
        return dst


def cached_wav(src: Path, cache_dir: Path, ffmpeg: Ffmpeg, sample_rate: int = SAMPLE_RATE) -> Path:
    """Convert once per file content; later calls return the cached wav."""
    dst = Path(cache_dir) / "wav" / f"{Path(src).stem[:40]}-{file_hash(Path(src))}-{sample_rate}.wav"
    if dst.exists():
        return dst
    return ffmpeg.to_wav(Path(src), dst, sample_rate)
