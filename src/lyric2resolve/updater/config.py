"""Updater settings (JSON file in the data folder; a UI follows in Phase 18)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from lyric2resolve import paths

CONFIG_NAME = "updater.json"
STATE_NAME = "updater_state.json"


@dataclass
class UpdaterConfig:
    remote: str = "origin"
    branch: str = "main"
    # Optional: expected remote URL. If set, the updater refuses to fetch when the
    # clone's remote points elsewhere (only fetch from the configured remote).
    repo_url: str = ""
    check_at_launch: bool = True
    check_at_login: bool = False
    fetch_timeout_s: int = 20
    keep_rollback_tags: int = 5

    @classmethod
    def from_dict(cls, data: dict) -> "UpdaterConfig":
        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in (data or {}).items() if k in known}
        cfg = cls(**clean)
        cfg.fetch_timeout_s = max(3, int(cfg.fetch_timeout_s))
        cfg.keep_rollback_tags = max(1, int(cfg.keep_rollback_tags))
        return cfg

    def to_dict(self) -> dict:
        return asdict(self)


def config_path(settings_dir: Path | None = None) -> Path:
    return (settings_dir or paths.settings_dir()) / CONFIG_NAME


def load_config(settings_dir: Path | None = None) -> UpdaterConfig:
    path = config_path(settings_dir)
    try:
        return UpdaterConfig.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return UpdaterConfig()


def save_config(cfg: UpdaterConfig, settings_dir: Path | None = None) -> Path:
    path = config_path(settings_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg.to_dict(), indent=2), encoding="utf-8")
    return path


@dataclass
class UpdaterState:
    """Things the updater remembers between runs (not user-editable)."""

    requirements_hash: str = ""
    last_update_from: str = ""
    last_update_to: str = ""
    extra: dict = field(default_factory=dict)


def state_path(settings_dir: Path | None = None) -> Path:
    return (settings_dir or paths.settings_dir()) / STATE_NAME


def load_state(settings_dir: Path | None = None) -> UpdaterState:
    try:
        data = json.loads(state_path(settings_dir).read_text(encoding="utf-8"))
        known = {f.name for f in fields(UpdaterState)}
        return UpdaterState(**{k: v for k, v in data.items() if k in known})
    except (OSError, ValueError, TypeError):
        return UpdaterState()


def save_state(state: UpdaterState, settings_dir: Path | None = None) -> None:
    path = state_path(settings_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")
