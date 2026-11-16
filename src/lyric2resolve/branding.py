"""Theme / "Team Funqtion branding" toggle.

Brand tokens come from `config/brand_funqtion.json` (taken from github.com/Gbom2009/funqtion-site).
To change them without touching the code folder (the updater refuses to update a modified code folder),
copy that file to `<data>/settings/brand_funqtion.json` and edit the copy: it wins over the repo file.

Every page loads `/theme.css`: empty for the default theme, CSS variable overrides when branding is on.
Fonts come only from the local font library (offline, no Google requests); otherwise the fallbacks apply.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from lyric2resolve import paths

BRAND_FILE = "brand_funqtion.json"
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
REQUIRED_COLORS = ("page", "surface", "hairline", "text", "text_strong", "text_dim", "accent", "accent_text")


class BrandError(ValueError):
    pass


@dataclass
class Brand:
    name: str
    colors: dict
    fonts: dict = field(default_factory=dict)
    radius_px: int = 0
    logo: str = ""
    video_text_style: dict = field(default_factory=dict)
    source: str = ""


def repo_brand_path() -> Path:
    return paths.code_dir() / "config" / BRAND_FILE


def user_brand_path(settings_dir: Path | None = None) -> Path:
    return (settings_dir or paths.settings_dir()) / BRAND_FILE


def load_brand(path: Path | None = None, settings_dir: Path | None = None) -> Brand:
    """User copy in the data folder > repo config. Raises BrandError on a broken file."""
    if path is None:
        user = user_brand_path(settings_dir)
        path = user if user.is_file() else repo_brand_path()
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BrandError(f"could not read brand file {path}: {exc}") from exc
    colors = dict(data.get("colors") or {})
    missing = [k for k in REQUIRED_COLORS if k not in colors]
    bad = [k for k, v in colors.items() if not _HEX.match(str(v))]
    if missing or bad:
        raise BrandError(f"brand file {path}: missing colors {missing}, invalid colors {bad} (use #rrggbb)")
    return Brand(str(data.get("name") or "Brand"), colors, dict(data.get("fonts") or {}),
                 int(data.get("radius_px") or 0), str(data.get("logo") or ""),
                 dict(data.get("video_text_style") or {}), str(data.get("source") or ""))


def branding_on(settings) -> bool:
    return bool(getattr(settings, "funqtion_branding", False)) or getattr(settings, "theme", "") == "funqtion"


def _mix(a: str, b: str, t: float) -> str:
    """Blend two #rrggbb colors (t = share of b)."""
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ca, cb))


def _q(family: str) -> str:
    return "'" + family.replace("'", "") + "'"


def font_faces(families: list[str], fonts: list[dict]) -> str:
    """@font-face rules for brand families that exist in the local font library."""
    out = []
    want = {f.lower() for f in families if f}
    for f in fonts:
        if f["family"].lower() not in want or f.get("source") == "system":
            continue
        for rel in f.get("files", []):
            m = re.search(r"-(Thin|ExtraLight|Light|Regular|Medium|SemiBold|Bold|ExtraBold|Black)(Italic)?\.",
                          rel, re.I)
            weight = {"thin": 100, "extralight": 200, "light": 300, "regular": 400, "medium": 500, "semibold": 600,
                      "bold": 700, "extrabold": 800, "black": 900}[m.group(1).lower()] if m else 400
            style = "italic" if m and m.group(2) else "normal"
            out.append(f"@font-face {{ font-family: {_q(f['family'])}; src: url('/api/fonts/file/{rel}'); "
                       f"font-weight: {weight}; font-style: {style}; font-display: swap; }}")
    return "\n".join(out)


def theme_css(brand: Brand, fonts: list[dict] | None = None) -> str:
    c = brand.colors
    body = brand.fonts.get("body", "")
    display = brand.fonts.get("display", "")
    body_stack = ", ".join(x for x in (_q(body) if body else "", brand.fonts.get("body_fallback", "monospace")) if x)
    disp_stack = ", ".join(x for x in (_q(display) if display else "", brand.fonts.get("display_fallback", "sans-serif")) if x)
    r = f"{brand.radius_px}px"
    vars_ = {
        # editor / library / ideas / settings (style.css)
        "--bg": c["page"], "--panel": c["surface"], "--text": c["text"], "--muted": c["text_dim"],
        "--line": c["hairline"], "--accent": c["accent"], "--accent-text": c["accent_text"],
        "--select": c["accent"], "--select-text": c["accent_text"], "--playing": c["accent"],
        "--block-bg": _mix(c["surface"], c["text"], 0.05), "--block-active": _mix(c["surface"], c["accent"], 0.22),
        "--gap": "rgba(255, 255, 255, 0.07)", "--flag": "#ff6b5e", "--warn": "#f2c14e", "--ok": "#4cc38a",
        "--wave": c["text_dim"], "--wave-progress": c["accent"], "--radius": r, "--font": body_stack,
        # karaoke (karaoke.css)
        "--bg1": c["page"], "--bg2": _mix(c["page"], c["accent"], 0.12), "--dim": c["text_dim"], "--sung": c["accent"],
    }
    lines = [f"/* {brand.name} branding (generated from {BRAND_FILE}) */",
             font_faces([body, display], fonts or []),
             ":root { color-scheme: dark; " + " ".join(f"{k}: {v};" for k, v in vars_.items()) + " }",
             f"h1, h2, .brand, .cd-num, .line.current {{ font-family: {disp_stack}; letter-spacing: -0.02em; }}",
             "button, input, select, textarea, dialog, .card, .block, .word, .concept, .sec { border-radius: var(--radius) !important; }",
             f"button.primary, .btnlink.primary {{ color: {c['accent_text']}; }}",
             f"a {{ color: {c['accent']}; }}",
             "input, select, textarea { background: var(--bg); color: var(--text); }",
             f"::selection {{ background: {c['text']}; color: {c['page']}; }}"]
    if brand.logo:
        lines.append(f".brand .logo {{ background: url('/static/{brand.logo}') center / contain no-repeat; color: transparent; "
                     "width: 30px; height: 30px; padding: 0; display: inline-block; overflow: hidden; }")
    return "\n".join(x for x in lines if x) + "\n"


def current_css(settings, settings_dir: Path | None = None, fonts: list[dict] | None = None) -> str:
    """CSS for the active theme ('' = default theme). A broken brand file falls back to the default theme."""
    if not branding_on(settings):
        return "/* default theme */\n"
    try:
        brand = load_brand(settings_dir=settings_dir)
    except BrandError as exc:
        return f"/* branding off: {str(exc).replace('*/', '')} */\n"
    return theme_css(brand, fonts)
