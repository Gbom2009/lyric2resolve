"""Render presets (UI + CLI --render-preset): PREVIEW, DRAFT, STANDARD, HIGH, ULTRA, CUSTOM.

Heights are for the 16:9 layout; 9:16 swaps width/height. Rekordbox plays video up to 1920x1080, so
ULTRA (4K) is for Resolve/YouTube, not for the DJ decks (the DJ encode is capped at 1080p).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace

__all__ = ["RenderPreset", "PRESETS", "get", "recommended", "replace"]


@dataclass
class RenderPreset:
    name: str
    height: int                 # 16:9 frame height (540, 720, 1080, 2160)
    engine: str = "EEVEE"       # EEVEE | CYCLES
    samples: int = 32
    denoise: bool = True
    bloom: bool = True
    fps: float | None = None    # None = project fps
    max_seconds: float | None = None   # only the first N seconds (preview)
    view_transform: str = "AgX"
    description: str = ""

    def size(self, aspect: str) -> tuple[int, int]:
        w = int(round(self.height * 16 / 9 / 2)) * 2
        return (w, self.height) if aspect == "16:9" else (self.height, w)

    def scale(self) -> float:
        """resolution_scale for the scene script (base 1080p)."""
        return self.height / 1080.0

    def to_dict(self) -> dict:
        return asdict(self)


PRESETS: dict[str, RenderPreset] = {
    "preview": RenderPreset("preview", 540, "EEVEE", 8, False, True, fps=15, max_seconds=25,
                            description="540p, Eevee, minimal samples, 15 fps, first 25 s - check the look fast"),
    "draft": RenderPreset("draft", 720, "EEVEE", 16, True, True,
                          description="720p Eevee, full length - check timing against the song"),
    "standard": RenderPreset("standard", 1080, "EEVEE", 64, True, True,
                             description="1080p Eevee, medium samples, bloom, denoise - the normal final render"),
    "high": RenderPreset("high", 1080, "EEVEE", 128, True, True,
                         description="1080p Eevee, high samples - cleaner glow and motion"),
    "ultra": RenderPreset("ultra", 2160, "CYCLES", 256, True, True,
                          description="4K Cycles - very slow; for YouTube/Resolve, not needed for DJ decks"),
}


def get(name: str, **overrides) -> RenderPreset:
    """Preset by name; 'custom' starts from STANDARD. Overrides: height, engine, samples, denoise, fps, ..."""
    key = name.lower()
    if key == "custom":
        base = replace(PRESETS["standard"], name="custom", description="custom settings")
    elif key in PRESETS:
        base = PRESETS[key]
    else:
        raise ValueError(f"unknown render preset {name!r}; use {', '.join(list(PRESETS) + ['custom'])}")
    clean = {k: v for k, v in overrides.items() if v is not None}
    for k in clean:
        if k not in RenderPreset.__dataclass_fields__ or k == "name":
            raise ValueError(f"unknown render setting {k}")
    if "engine" in clean and str(clean["engine"]).upper() not in ("EEVEE", "CYCLES"):
        raise ValueError("engine must be EEVEE or CYCLES")
    p = replace(base, **clean)
    p.engine = p.engine.upper()
    return p


def recommended(gpu) -> tuple[str, str]:
    """(preset name, reason) for this machine. A setup_tools.GpuInfo goes in.

    Apple Silicon shares its memory between CPU and GPU, and a base MacBook Air (8 GB, no fan) slows down on long
    renders: Draft first there, Standard only for the final video."""
    if getattr(gpu, "apple", False):
        gb = round((gpu.memory_mb or 0) / 1024)
        if gb and gb <= 8:
            return "draft", (f"{gb} GB Mac: start with Draft (or Preview); render Standard only for the final video, "
                             "with other apps closed. A fanless MacBook Air slows down during long renders.")
        return "standard", "Mac (Apple Silicon): Eevee renders on the GPU through Metal."
    return "standard", ""
