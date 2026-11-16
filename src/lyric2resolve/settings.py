"""App settings (JSON in <data>/settings/app.json). Stdlib only.

The settings UI arrives in Phase 18; until then the file can be edited by hand.
Unknown keys are kept (forward compatible), invalid values fall back to defaults.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from lyric2resolve import paths

SETTINGS_NAME = "app.json"
SCHEMA_VERSION = 1

FPS_CHOICES = (23.976, 24.0, 25.0, 29.97, 30.0, 50.0, 60.0)
STYLING_LEVELS = ("basic", "styled", "full")
WHISPER_MODELS = ("tiny", "base", "small", "medium", "large-v2", "large-v3", "large-v3-turbo", "turbo")
THEMES = ("default", "funqtion")
# "" = CLI default. bypassPermissions is deliberately not offered.
CLAUDE_PERMISSION_MODES = ("", "default", "acceptEdits", "plan", "dontAsk", "auto")


@dataclass
class AppSettings:
    schema_version: int = SCHEMA_VERSION
    # tool paths ("" = auto-detect)
    ffmpeg_path: str = ""
    blender_path: str = ""
    claude_cli_path: str = ""
    # Claude link (optional Assistant; uses the user's own `claude` login)
    claude_model: str = ""             # "" = the CLI's default
    claude_permission_mode: str = ""   # "" = default (only the app's MCP tools are pre-allowed)
    claude_blender_mcp: bool = False   # also register the community Blender MCP server
    # transcription
    # Mac (Apple Silicon): MLX on the M chip; large-v3-turbo fits comfortably in 8 GB
    whisper_model: str = field(default_factory=lambda: "large-v3-turbo" if sys.platform == "darwin" else "large-v3")
    device: str = field(default_factory=lambda: "mps" if sys.platform == "darwin" else "cuda")  # cuda | mps | cpu
    compute_type: str = "float16"
    language: str = ""            # "" = auto-detect
    vad_threshold: float = 0.35   # voice filter sensitivity; Silero's default 0.5 is tuned for speech and can
                                  # drop soft/reverb-heavy sung lines (e.g. a whole first sentence). 0 = filter off
    # timeline / export
    default_fps: float = 25.0
    width: int = 1920
    height: int = 1080
    layouts: list[str] = field(default_factory=lambda: ["16:9", "9:16"])
    start_timecode: str = "01:00:00:00"
    styling_level: str = "basic"
    # UI
    theme: str = "default"
    funqtion_branding: bool = False
    editor_host: str = "127.0.0.1"
    editor_port: int = 8765
    extra: dict = field(default_factory=dict)  # unknown keys from newer versions

    def validate(self) -> list[str]:
        """Fix invalid values in place; return human-readable warnings."""
        warnings: list[str] = []
        d = AppSettings()

        def reset(name: str, why: str) -> None:
            warnings.append(f"settings: {name} {why}; using default {getattr(d, name)!r}")
            setattr(self, name, getattr(d, name))

        try:
            fps = float(self.default_fps)
            match = [f for f in FPS_CHOICES if abs(f - fps) < 1e-3]
            if match:
                self.default_fps = match[0]
            else:
                reset("default_fps", f"{self.default_fps!r} is not one of {FPS_CHOICES}")
        except (TypeError, ValueError):
            reset("default_fps", "is not a number")
        if self.styling_level not in STYLING_LEVELS:
            reset("styling_level", f"must be one of {STYLING_LEVELS}")
        if self.whisper_model not in WHISPER_MODELS:
            reset("whisper_model", f"must be one of {WHISPER_MODELS}")
        if self.device not in ("cuda", "mps", "cpu"):
            reset("device", "must be 'cuda' (NVIDIA), 'mps' (Apple Silicon) or 'cpu'")
        try:
            if not 0.0 <= float(self.vad_threshold) <= 0.9:
                raise ValueError
            self.vad_threshold = float(self.vad_threshold)
        except (TypeError, ValueError):
            reset("vad_threshold", "must be a number between 0 and 0.9")
        if self.claude_permission_mode not in CLAUDE_PERMISSION_MODES:
            reset("claude_permission_mode", f"must be one of {CLAUDE_PERMISSION_MODES}")
        if self.theme not in THEMES:
            reset("theme", f"must be one of {THEMES}")
        for name in ("width", "height", "editor_port"):
            try:
                if int(getattr(self, name)) <= 0:
                    raise ValueError
                setattr(self, name, int(getattr(self, name)))
            except (TypeError, ValueError):
                reset(name, "must be a positive integer")
        if not isinstance(self.layouts, list) or not set(self.layouts) <= {"16:9", "9:16"} or not self.layouts:
            reset("layouts", "must be a non-empty list of '16:9'/'9:16'")
        return warnings

    @classmethod
    def from_dict(cls, data: dict) -> "AppSettings":
        data = migrate(dict(data or {}))
        known = {f.name for f in fields(cls)} - {"extra"}
        obj = cls(**{k: v for k, v in data.items() if k in known})
        obj.extra = {k: v for k, v in data.items() if k not in known and k != "extra"}
        obj.extra.update(data.get("extra") or {})
        return obj

    def to_dict(self) -> dict:
        out = asdict(self)
        extra = out.pop("extra")
        for k, v in extra.items():
            out.setdefault(k, v)
        return out


def migrate(data: dict) -> dict:
    """Upgrade older settings files. v0 (no schema_version) used 'fps' and 'resolution'."""
    version = int(data.get("schema_version", 0) or 0)
    if version < 1:
        if "fps" in data and "default_fps" not in data:
            data["default_fps"] = data.pop("fps")
        res = data.pop("resolution", None)
        if isinstance(res, str) and "x" in res:
            w, _, h = res.partition("x")
            data.setdefault("width", int(w))
            data.setdefault("height", int(h))
        data["schema_version"] = 1
    return data


def settings_path(settings_dir: Path | None = None) -> Path:
    return (settings_dir or paths.settings_dir()) / SETTINGS_NAME


def load_settings(settings_dir: Path | None = None) -> tuple[AppSettings, list[str]]:
    path = settings_path(settings_dir)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return AppSettings(), []
    except (OSError, ValueError) as exc:
        return AppSettings(), [f"settings: could not read {path} ({exc}); using defaults"]
    s = AppSettings.from_dict(raw if isinstance(raw, dict) else {})
    return s, s.validate()


def save_settings(s: AppSettings, settings_dir: Path | None = None) -> Path:
    return paths.atomic_write_text(settings_path(settings_dir), json.dumps(s.to_dict(), indent=2))
