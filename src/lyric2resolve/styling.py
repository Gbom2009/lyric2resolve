"""Text style presets, per-section styles and the styling level (BASIC / STYLED / FULL).

Stored in project.styles:
    {"presets": {name: TextStyle dict}, "default": name, "by_section": {label: name}}
Built-in presets are always available and cannot be deleted (they can be copied).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, fields, replace

LEVELS = ("basic", "styled", "full")
ANIMATIONS = ("none", "fade", "pop", "slide_up", "word_reveal")
ALIGN = ("left", "center", "right")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


class StyleError(ValueError):
    pass


@dataclass
class TextStyle:
    font_family: str = "Arial"
    font_style: str = "Bold"           # as Resolve/Fusion names it: Regular, Bold, Italic, Bold Italic, Black ...
    size_px: int = 0                   # 0 = automatic per layout
    fill: str = "#ffffff"
    fill_opacity: float = 1.0
    outline_color: str = "#000000"
    outline_width: float = 0.0         # px at 1080p
    shadow_color: str = "#000000"
    shadow_opacity: float = 0.0
    shadow_offset_x: float = 4.0
    shadow_offset_y: float = 4.0
    shadow_blur: float = 6.0
    glow_color: str = "#00e5ff"
    glow_size: float = 0.0             # 0 = no glow
    glow_strength: float = 1.0
    align: str = "center"
    position_y_16x9: float = 0.80      # centre of the text block, fraction of frame height from the top
    position_y_9x16: float = 0.62
    letter_spacing: float = 0.0        # em
    line_spacing: float = 1.15
    animation_in: str = "fade"         # used only at styling level FULL
    animation_out: str = "fade"
    animation_ms: int = 150

    def validate(self) -> None:
        for name in ("fill", "outline_color", "shadow_color", "glow_color"):
            if not _HEX.match(str(getattr(self, name))):
                raise StyleError(f"{name} must be a colour like #ff8800, got {getattr(self, name)!r}")
        for name in ("fill_opacity", "shadow_opacity", "position_y_16x9", "position_y_9x16"):
            v = float(getattr(self, name))
            if not 0.0 <= v <= 1.0:
                raise StyleError(f"{name} must be between 0 and 1")
        if self.align not in ALIGN:
            raise StyleError(f"align must be one of {ALIGN}")
        for name in ("animation_in", "animation_out"):
            if getattr(self, name) not in ANIMATIONS:
                raise StyleError(f"{name} must be one of {ANIMATIONS}")
        if int(self.size_px) < 0 or float(self.outline_width) < 0 or float(self.glow_size) < 0:
            raise StyleError("sizes cannot be negative")
        if not str(self.font_family).strip():
            raise StyleError("font_family cannot be empty")

    @classmethod
    def from_dict(cls, data: dict) -> "TextStyle":
        known = {f.name for f in fields(cls)}
        base = cls()
        clean = {}
        for k, v in (data or {}).items():
            if k not in known:
                continue
            cur = getattr(base, k)
            try:
                clean[k] = type(cur)(v)
            except (TypeError, ValueError) as exc:
                raise StyleError(f"{k}: invalid value {v!r}") from exc
        s = cls(**clean)
        s.validate()
        return s

    def to_dict(self) -> dict:
        return asdict(self)

    def position_y(self, layout: str) -> float:
        return self.position_y_9x16 if layout == "9:16" else self.position_y_16x9


BUILTIN: dict[str, TextStyle] = {
    "Clean": TextStyle(font_family="Arial", font_style="Bold", outline_width=4.0),
    "Bold Yellow": TextStyle(font_family="Impact", font_style="Regular", fill="#ffd400", outline_width=6.0,
                             shadow_opacity=0.6),
    "Neon": TextStyle(font_family="Arial", font_style="Bold", fill="#e8fdff", glow_color="#00e5ff", glow_size=18.0,
                      glow_strength=1.4, outline_width=0.0, animation_in="pop"),
    "Minimal": TextStyle(font_family="Segoe UI", font_style="Semibold", outline_width=0.0, shadow_opacity=0.55,
                         shadow_blur=10.0, animation_in="fade"),
    "Karaoke Big": TextStyle(font_family="Arial", font_style="Black", fill="#ffffff", outline_width=8.0,
                             position_y_16x9=0.5, position_y_9x16=0.5, animation_in="word_reveal"),
    # lyric-video looks: the words are the main event (big, centred, glowing, animated) - not subtitles
    "Lyric Video": TextStyle(font_family="Arial Black", font_style="Regular", size_px=124, fill="#ffffff",
                             outline_width=0.0, shadow_opacity=0.55, shadow_blur=18.0, shadow_offset_x=0.0,
                             shadow_offset_y=6.0, glow_color="#ff3c8e", glow_size=10.0, glow_strength=0.9,
                             position_y_16x9=0.5, position_y_9x16=0.5, line_spacing=1.0, letter_spacing=-0.01,
                             animation_in="pop", animation_out="fade", animation_ms=180),
    "Lyric Video Neon": TextStyle(font_family="Arial Black", font_style="Regular", size_px=116, fill="#eafcff",
                                  outline_width=0.0, glow_color="#00e5ff", glow_size=20.0, glow_strength=1.5,
                                  position_y_16x9=0.5, position_y_9x16=0.5, line_spacing=1.0,
                                  animation_in="word_reveal", animation_out="fade", animation_ms=140),
    "Lyric Video Punch": TextStyle(font_family="Impact", font_style="Regular", size_px=150, fill="#ffe14d",
                                   outline_color="#000000", outline_width=6.0, shadow_opacity=0.7,
                                   shadow_blur=4.0, position_y_16x9=0.5, position_y_9x16=0.48, line_spacing=0.95,
                                   animation_in="pop", animation_out="none", animation_ms=120),
}
LYRIC_VIDEO_STYLE = "Lyric Video"   # default look of projects made with "Look: Lyric video"
DEFAULT_STYLE = "Clean"
BASIC_STYLE = TextStyle(font_family="Arial", font_style="Bold", outline_width=0.0, animation_in="none",
                        animation_out="none")


@dataclass
class StyleBook:
    presets: dict[str, TextStyle] = field(default_factory=dict)   # user presets (built-ins are implicit)
    default: str = DEFAULT_STYLE
    by_section: dict[str, str] = field(default_factory=dict)      # section label or id -> preset name

    @classmethod
    def from_project(cls, styles: dict | None) -> "StyleBook":
        styles = styles or {}
        presets = {}
        for name, d in (styles.get("presets") or {}).items():
            try:
                presets[name] = TextStyle.from_dict(d)
            except StyleError:
                continue  # a broken user preset is skipped, never fatal
        return cls(presets, styles.get("default") or DEFAULT_STYLE, dict(styles.get("by_section") or {}))

    def to_project(self) -> dict:
        return {"presets": {k: v.to_dict() for k, v in self.presets.items()}, "default": self.default,
                "by_section": dict(self.by_section)}

    def all(self) -> dict[str, TextStyle]:
        out = dict(BUILTIN)
        out.update(self.presets)
        return out

    def get(self, name: str | None) -> TextStyle | None:
        return self.all().get(name) if name else None


def resolve(book: StyleBook, block_style: str | None = None, section_label: str | None = None,
            section_id: str | None = None, section_style: str | None = None, level: str = "styled") -> TextStyle:
    """Pick the style for a block: block > section (own field > by id > by label) > default.

    BASIC level ignores presets: plain text with a default font/size/colour.
    FULL keeps animations; STYLED switches them off.
    """
    if level not in LEVELS:
        raise StyleError(f"styling level must be one of {LEVELS}")
    if level == "basic":
        return replace(BASIC_STYLE)
    for name in (block_style, section_style, book.by_section.get(section_id or ""),
                 book.by_section.get((section_label or "").lower()), book.default, DEFAULT_STYLE):
        s = book.get(name)
        if s is not None:
            s = replace(s)
            if level == "styled":
                s.animation_in = s.animation_out = "none"
            return s
    return replace(BUILTIN[DEFAULT_STYLE])  # pragma: no cover


def style_for_block(project, block, level: str | None = None) -> TextStyle:
    """Convenience: resolve the style of a project block (section by the block's start time)."""
    book = StyleBook.from_project(getattr(project, "styles", None))
    start, _ = project.block_span(block)
    sec = next((s for s in project.sections if s.start <= start < s.end), None)
    return resolve(book, block.style, sec.label if sec else None, sec.id if sec else None,
                   sec.style if sec else None, level or project.settings.styling_level)


# ------------------------------------------------------------------ edit ops (used by the editor)
def op_save_style(project, name: str, style: dict) -> None:
    name = (name or "").strip()
    if not name:
        raise StyleError("a style needs a name")
    if name in BUILTIN:
        raise StyleError(f"'{name}' is a built-in style; save it under another name")
    book = StyleBook.from_project(project.styles)
    book.presets[name] = TextStyle.from_dict(style)
    project.styles = book.to_project()


def op_delete_style(project, name: str) -> None:
    book = StyleBook.from_project(project.styles)
    if name in BUILTIN:
        raise StyleError("built-in styles cannot be deleted")
    if name not in book.presets:
        raise StyleError(f"unknown style {name}")
    del book.presets[name]
    if book.default == name:
        book.default = DEFAULT_STYLE
    book.by_section = {k: v for k, v in book.by_section.items() if v != name}
    for b in project.blocks:
        if b.style == name:
            b.style = None
    project.styles = book.to_project()


def op_set_default_style(project, name: str) -> None:
    book = StyleBook.from_project(project.styles)
    if name not in book.all():
        raise StyleError(f"unknown style {name}")
    book.default = name
    project.styles = book.to_project()


def op_set_section_style(project, section_label: str, name: str | None) -> None:
    """Style per section label (e.g. all 'chorus' sections). name None = back to default."""
    book = StyleBook.from_project(project.styles)
    key = (section_label or "").strip().lower()
    if not key:
        raise StyleError("section label required")
    if name:
        if name not in book.all():
            raise StyleError(f"unknown style {name}")
        book.by_section[key] = name
    else:
        book.by_section.pop(key, None)
    project.styles = book.to_project()


def op_set_styling_level(project, level: str) -> None:
    if level not in LEVELS:
        raise StyleError(f"styling level must be one of {LEVELS}")
    project.settings.styling_level = level
