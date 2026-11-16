"""PNG sequence -> MP4 with the full song muxed in, for DJ decks (Rekordbox / Serato) and Resolve.

Format (checked against the Rekordbox video FAQ and Serato's supported-formats article, 2026-11-16):
H.264 (High profile, yuv420p) in MP4, constant frame rate, keyframe at least every second (Serato asks for
15-25 frames), AAC 320 kbps stereo, faststart. Rekordbox plays video up to 1920x1080, so DJ encodes are
scaled down to fit 1080p when the frames are larger.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

NTSC = {23.976: "24000/1001", 29.97: "30000/1001", 59.94: "60000/1001"}


def rate_str(fps: float) -> str:
    for k, v in NTSC.items():
        if abs(fps - k) < 0.01:
            return v
    return str(int(round(fps))) if abs(fps - round(fps)) < 1e-6 else str(fps)


@dataclass
class MuxSettings:
    fps: float
    audio_bitrate: str = "320k"
    audio_rate: int = 48000
    crf: int = 18
    preset: str = "slow"
    encoder: str = "libx264"        # or h264_nvenc (NVIDIA) / h264_videotoolbox (Mac)
    fit_box: tuple[int, int] | None = None   # e.g. (1920, 1080) for the Rekordbox-safe DJ copy
    start_seconds: float = 0.0      # audio offset for a partial (section) render
    audio: bool = True              # False: video only (timeline clips - the song is already on its own track)


def gop(fps: float) -> int:
    """Keyframe interval: 1 s, capped at 25 frames (Serato recommends 15-25)."""
    return max(1, min(25, int(round(fps))))


def mux_command(ffmpeg: str, frames_pattern: str, start_number: int, song: Path, out: Path,
                s: MuxSettings, frame_size: tuple[int, int] | None = None) -> list[str]:
    r = rate_str(s.fps)
    g = gop(s.fps)
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
           "-framerate", r, "-start_number", str(start_number), "-i", frames_pattern]
    if s.audio:
        if s.start_seconds:
            cmd += ["-ss", f"{s.start_seconds:.3f}"]
        cmd += ["-i", str(song), "-map", "0:v:0", "-map", "1:a:0"]
    else:
        cmd += ["-map", "0:v:0", "-an"]
    vf = []
    if s.fit_box and frame_size and (frame_size[0] > s.fit_box[0] or frame_size[1] > s.fit_box[1]):
        bw, bh = s.fit_box
        vf.append(f"scale={bw}:{bh}:force_original_aspect_ratio=decrease:force_divisible_by=2:flags=lanczos")
    vf.append("format=yuv420p")
    cmd += ["-vf", ",".join(vf)]
    if s.encoder == "h264_nvenc":
        cmd += ["-c:v", "h264_nvenc", "-preset", "p6", "-rc", "vbr", "-cq", str(s.crf + 1), "-b:v", "0"]
    elif s.encoder == "h264_videotoolbox":
        # Apple's hardware encoder (M chips): constant quality (-q:v 1-100, higher = better); allow_sw lets macOS
        # use its software path instead of failing when the hardware is busy
        cmd += ["-c:v", "h264_videotoolbox", "-q:v", str(vt_quality(s.crf)), "-allow_sw", "1"]
    else:
        cmd += ["-c:v", "libx264", "-preset", s.preset, "-crf", str(s.crf)]
    cmd += ["-profile:v", "high", "-r", r, "-fps_mode", "cfr", "-g", str(g), "-keyint_min", str(g),
            "-sc_threshold", "0"]
    if s.audio:
        cmd += ["-c:a", "aac", "-b:a", s.audio_bitrate, "-ar", str(s.audio_rate), "-ac", "2"]
    cmd += ["-movflags", "+faststart", str(out)]
    return cmd


HW_ENCODERS = {"darwin": ("h264_videotoolbox",), "other": ("h264_nvenc",)}


def vt_quality(crf: int) -> int:
    """x264 CRF (lower = better) -> VideoToolbox -q:v (higher = better). CRF 18 -> 65."""
    return max(1, min(100, 101 - 2 * crf))


def pick_encoder(ffmpeg: str, platform: str | None = None, has=None) -> str:
    """Hardware H.264 encoder when ffmpeg has one for this OS (VideoToolbox on Mac, NVENC elsewhere), else libx264."""
    has = has or has_encoder
    key = "darwin" if (platform or sys.platform) == "darwin" else "other"
    for name in HW_ENCODERS[key]:
        if has(ffmpeg, name):
            return name
    return "libx264"


def has_encoder(ffmpeg: str, name: str) -> bool:
    try:
        out = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.TimeoutExpired):
        return False
    return f" {name} " in out


def run(cmd: list[str]) -> None:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform.startswith("win") else 0
    proc = subprocess.run(cmd, capture_output=True, text=True, creationflags=flags)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr.strip()[-800:]}")


def probe(ffprobe: str, path: Path) -> dict:
    out = subprocess.run([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def check_dj_file(info: dict, fps: float) -> list[str]:
    """Problems that would stop a file from playing well on Rekordbox/Serato (empty = fine)."""
    problems = []
    v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
    if not v or v.get("codec_name") != "h264":
        problems.append("video must be H.264")
    if not a or a.get("codec_name") != "aac":
        problems.append("audio must be AAC (DJ software cannot play video without audio)")
    if v:
        if v.get("pix_fmt") != "yuv420p":
            problems.append("pixel format must be yuv420p")
        if int(v.get("height", 0)) > 1920 or int(v.get("width", 0)) > 1920:
            problems.append("larger than 1920 pixels: Rekordbox plays up to 1920x1080")
        r = v.get("r_frame_rate", "0/1")
        avg = v.get("avg_frame_rate", r)
        if r != avg and avg not in ("0/0",):
            problems.append(f"frame rate is not constant ({r} vs {avg})")
        if abs(float(Fraction(r)) - fps) > 0.01:
            problems.append(f"frame rate {r} does not match {fps}")
    return problems


def encode(ffmpeg: str, frames_pattern: str, start_number: int, song: Path, out: Path, s: "MuxSettings",
           frame_size: tuple[int, int] | None = None) -> str:
    """Encode with the hardware encoder (NVENC / VideoToolbox) when it works here, otherwise libx264.
    Returns the encoder used."""
    from dataclasses import replace

    if s.encoder != "libx264":
        try:
            run(mux_command(ffmpeg, frames_pattern, start_number, song, out, s, frame_size))
            return s.encoder
        except RuntimeError:
            s = replace(s, encoder="libx264")  # listed but unusable (no GPU/driver, busy): fall back
    run(mux_command(ffmpeg, frames_pattern, start_number, song, out, s, frame_size))
    return s.encoder
