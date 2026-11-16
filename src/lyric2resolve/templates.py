"""Project templates: reuse a look on a new song.

A template stores: text styles (presets + default), section styling, band-to-visual mapping, render preset,
layout settings (layouts, size, fps, font size, max lines, text options) and the styling level.
Saved as JSON in <data>/templates/<name>.json.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from lyric2resolve import paths
from lyric2resolve import project as proj

LAYOUT_KEYS = ("fps", "start_timecode", "width", "height", "layouts", "styling_level", "granularity", "phrase_words",
               "auto_pause_s", "min_gap_s", "pre_roll_ms", "post_roll_ms", "min_clip_frames", "hold_until_next",
               "fade_after_ms", "case", "strip_punctuation", "max_chars", "font_size_px", "max_lines")
TEMPLATE_VERSION = 1


class TemplateError(ValueError):
    pass


def templates_dir() -> Path:
    d = paths.ensure_data_dir() / "templates"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _file(name: str, folder: Path | None = None) -> Path:
    safe = re.sub(r"[^\w\- ]+", "", name).strip()
    if not safe:
        raise TemplateError("template needs a name")
    return (folder or templates_dir()) / f"{safe}.json"


def from_project(p: proj.Project, name: str, mapping: dict | None = None, render_preset: str = "standard",
                 visual_template: str | None = None) -> dict:
    s = p.settings
    return {
        "version": TEMPLATE_VERSION,
        "name": name,
        "styles": json.loads(json.dumps(p.styles or {})),
        "section_presets": {sec.label.lower(): sec.preset for sec in p.sections if sec.preset},
        "settings": {k: getattr(s, k) for k in LAYOUT_KEYS},
        "mapping": mapping or p.extra.get("visual_mapping") or {},
        "render_preset": render_preset,
        "visual_template": visual_template or p.extra.get("visual_template"),
    }


def save(p: proj.Project, name: str, folder: Path | None = None, **kw) -> Path:
    path = _file(name, folder)
    path.write_text(json.dumps(from_project(p, name, **kw), indent=1), encoding="utf-8")
    return path


def load(name: str, folder: Path | None = None) -> dict:
    path = _file(name, folder)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TemplateError(f"cannot read template {name}: {exc}") from exc
    if int(data.get("version", 1)) > TEMPLATE_VERSION:
        raise TemplateError("template was made by a newer app version")
    return data


def list_templates(folder: Path | None = None) -> list[str]:
    return sorted(p.stem for p in (folder or templates_dir()).glob("*.json"))


def apply(p: proj.Project, t: dict) -> None:
    """Apply a template to a project (keeps words/blocks/timing; only look and settings change)."""
    from lyric2resolve import styling

    styles = t.get("styles") or {}
    styling.StyleBook.from_project(styles)  # validates presets (broken ones are dropped)
    p.styles = json.loads(json.dumps(styles))
    for k, v in (t.get("settings") or {}).items():
        if k in LAYOUT_KEYS:
            cur = getattr(p.settings, k)
            setattr(p.settings, k, type(cur)(v) if isinstance(cur, (int, float, str, bool)) and v is not None else v)
    presets = t.get("section_presets") or {}
    for sec in p.sections:
        if sec.label.lower() in presets:
            sec.preset = presets[sec.label.lower()]
    if t.get("mapping"):
        p.extra["visual_mapping"] = t["mapping"]
    if t.get("render_preset"):
        p.extra["render_preset"] = t["render_preset"]
    if t.get("visual_template"):
        p.extra["visual_template"] = t["visual_template"]
    p.extra["template"] = t.get("name")


def op_apply_template(p: proj.Project, name: str) -> None:
    """Editor operation (undoable)."""
    apply(p, load(name))
