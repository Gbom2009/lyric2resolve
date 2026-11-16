"""Folder conventions.

Code folder = the git clone (replaced by updates).
Data folder = everything that belongs to the user (projects, assets, settings,
caches, models, logs, renders). It lives OUTSIDE the code folder so the updater
can never touch it.

Windows: %LOCALAPPDATA%\\lyric2resolve
Other:   $XDG_DATA_HOME/lyric2resolve or ~/.local/share/lyric2resolve
Override: environment variable LYRIC2RESOLVE_DATA
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "lyric2resolve"
DATA_ENV = "LYRIC2RESOLVE_DATA"

SUBDIRS = (
    "settings",
    "projects",
    "assets/fonts/custom",
    "assets/textures/custom",
    "cache",
    "models",
    "logs",
    "renders",
)


def code_dir() -> Path:
    """Root of the git clone (folder containing pyproject.toml)."""
    return Path(__file__).resolve().parents[2]


def data_dir(env: dict[str, str] | None = None, platform: str | None = None) -> Path:
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    override = env.get(DATA_ENV)
    if override:
        return Path(override).expanduser()
    if platform.startswith("win"):
        base = env.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_NAME
    if platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    base = env.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_NAME


def ensure_data_dir(root: Path | None = None) -> Path:
    root = data_dir() if root is None else root
    for sub in SUBDIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def settings_dir() -> Path:
    return data_dir() / "settings"


def logs_dir() -> Path:
    return data_dir() / "logs"
