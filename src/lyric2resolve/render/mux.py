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
    cmd += encoder_args(s.encoder, s.crf, s.preset)
    cmd += (["-profile:v", "high"] if s.encoder in HIGH_PROFILE_OK else []) + ["-r", r, "-fps_mode", "cfr", "-g", str(g), "-keyint_min", str(g),
            "-sc_threshold", "0"]
    if s.audio:
        cmd += ["-c:a", "aac", "-b:a", s.audio_bitrate, "-ar", str(s.audio_rate), "-ac", "2"]
    cmd += ["-movflags", "+faststart", str(out)]
    return cmd


# H.264 encoders in order of preference. Not every ffmpeg build has libx264 (LGPL builds leave it out - then even
# "-preset" is an unknown option), so the app picks what this ffmpeg really has.
H264_ORDER = {"darwin": ("h264_videotoolbox", "libx264", "libopenh264"),
              "other": ("h264_nvenc", "libx264", "h264_qsv", "h264_amf", "h264_mf", "libopenh264")}
HIGH_PROFILE_OK = {"libx264", "h264_nvenc", "h264_videotoolbox", "h264_qsv", "h264_amf"}
NO_H264_HELP = ("This ffmpeg has no H.264 encoder (it was built without libx264). Install a full build: Windows: "
                "winget install Gyan.FFmpeg (or the 'full' build from https://www.gyan.dev/ffmpeg/builds/), Mac: "
                "brew install ffmpeg - then set its path in Settings if needed.")


def encoder_args(enc: str, crf: int = 18, preset: str = "slow") -> list[str]:
    """Quality settings per encoder (only options that encoder knows)."""
    if enc == "libx264":
        return ["-c:v", "libx264", "-preset", preset, "-crf", str(crf)]
    if enc == "h264_nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p6", "-rc", "vbr", "-cq", str(crf + 1), "-b:v", "0"]
    if enc == "h264_videotoolbox":
        # Apple's hardware encoder (M chips): constant quality (-q:v 1-100, higher = better); allow_sw lets macOS
        # use its software path instead of failing when the hardware is busy
        return ["-c:v", "h264_videotoolbox", "-q:v", str(vt_quality(crf)), "-allow_sw", "1"]
    # QSV / AMF / Media Foundation / OpenH264: a high fixed bitrate (DJ guide: 16-20 Mb/s at 1080p)
    return ["-c:v", enc, "-b:v", "18M", "-maxrate", "20M", "-bufsize", "40M"]


def vt_quality(crf: int) -> int:
    """x264 CRF (lower = better) -> VideoToolbox -q:v (higher = better). CRF 18 -> 65."""
    return max(1, min(100, 101 - 2 * crf))


def h264_candidates(ffmpeg: str, platform: str | None = None, has=None) -> list[str]:
    """The H.264 encoders this ffmpeg has, best first (may be empty)."""
    has = has or has_encoder
    key = "darwin" if (platform or sys.platform) == "darwin" else "other"
    return [name for name in H264_ORDER[key] if has(ffmpeg, name)]


def pick_encoder(ffmpeg: str, platform: str | None = None, has=None) -> str:
    """Hardware H.264 encoder when ffmpeg has one for this OS (VideoToolbox on Mac, NVENC elsewhere), else libx264,
    else another H.264 encoder this ffmpeg has. libx264 when nothing is found (encode() then explains)."""
    found = h264_candidates(ffmpeg, platform, has)
    return found[0] if found else "libx264"


_ENCODERS: dict[str, str] = {}


def list_encoders(ffmpeg: str) -> str:
    """`ffmpeg -encoders` output (cached per ffmpeg path)."""
    if ffmpeg not in _ENCODERS:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform.startswith("win") else 0
        try:
            _ENCODERS[ffmpeg] = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True,
                                               timeout=30, creationflags=flags).stdout or ""
        except (OSError, subprocess.TimeoutExpired):
            return ""
    return _ENCODERS[ffmpeg]


def has_encoder(ffmpeg: str, name: str) -> bool:
    return f" {name} " in list_encoders(ffmpeg)


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
           frame_size: tuple[int, int] | None = None, candidates: list[str] | None = None) -> str:
    """Encode with s.encoder; when it fails (listed but unusable: no GPU/driver, busy), try the other H.264 encoders
    this ffmpeg has. Returns the encoder used."""
    from dataclasses import replace

    order = [s.encoder] + [e for e in (h264_candidates(ffmpeg) if candidates is None else candidates)
                           if e != s.encoder]
    errors = []
    for enc in order:
        try:
            run(mux_command(ffmpeg, frames_pattern, start_number, song, out, replace(s, encoder=enc), frame_size))
            return enc
        except RuntimeError as exc:
            errors.append(f"{enc}: {exc}")
    if not (candidates if candidates is not None else h264_candidates(ffmpeg)):
        raise RuntimeError(NO_H264_HELP + "\n" + errors[-1])
    raise RuntimeError("Encoding the video failed with every H.264 encoder:\n" + "\n".join(errors))
