"""Band -> visual target mapping (YAML), with validation and sensible defaults.

Default: bass = glowing orange + scale pulse, mids = glowing blue (+ slow rotation),
highs = glowing green + sparkles, RMS = light intensity, beats = camera shake.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path

TARGETS = ("emission_color", "emission_strength", "scale", "displacement", "position", "rotation",
           "sparkles", "camera_shake", "light_intensity")
SOURCES = ("bass", "mids", "highs", "rms", "onset", "beat")
TEMPLATES = ("spectrum_bars", "pulsing_blob", "tunnel", "particle_field", "floor_grid")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

DEFAULT_MAPPING: dict = {
    "bass": [{"target": "emission_color", "color": "#ff7a1a"}, {"target": "emission_strength", "amount": 6.0},
             {"target": "scale", "amount": 0.25}],
    "mids": [{"target": "emission_color", "color": "#2f7bff"}, {"target": "emission_strength", "amount": 4.0},
             {"target": "rotation", "amount": 0.3}],
    "highs": [{"target": "emission_color", "color": "#33ff88"}, {"target": "emission_strength", "amount": 5.0},
              {"target": "sparkles", "amount": 1.0}],
    "rms": [{"target": "light_intensity", "amount": 800.0}],
    "beat": [{"target": "camera_shake", "amount": 0.04}],
    # optional per-section colours: {"chorus": {"bass": "#ff2a6d"}}
    "palettes": {},
    # per-section intensity multipliers (0..1+)
    "section_levels": {"intro": 0.5, "verse": 0.7, "pre-chorus": 0.85, "chorus": 1.0, "drop": 1.0,
                       "bridge": 0.6, "breakdown": 0.45, "outro": 0.5},
}


class MappingError(ValueError):
    pass


def validate(m: dict) -> dict:
    out = copy.deepcopy(DEFAULT_MAPPING)
    for key, val in (m or {}).items():
        if key in SOURCES:
            if not isinstance(val, list):
                raise MappingError(f"{key}: expected a list of targets")
            items = []
            for t in val:
                if not isinstance(t, dict) or t.get("target") not in TARGETS:
                    raise MappingError(f"{key}: unknown target {t!r}; use one of {TARGETS}")
                if "color" in t and not _HEX.match(str(t["color"])):
                    raise MappingError(f"{key}: colour must look like #ff8800")
                if "amount" in t:
                    try:
                        t = dict(t, amount=float(t["amount"]))
                    except (TypeError, ValueError) as exc:
                        raise MappingError(f"{key}: amount must be a number") from exc
                items.append(dict(t))
            out[key] = items
        elif key == "palettes":
            for sec, cols in (val or {}).items():
                for band, col in (cols or {}).items():
                    if band not in SOURCES or not _HEX.match(str(col)):
                        raise MappingError(f"palettes.{sec}.{band}: expected band name and #rrggbb colour")
            out["palettes"] = {str(k).lower(): dict(v) for k, v in (val or {}).items()}
        elif key == "section_levels":
            out["section_levels"].update({str(k).lower(): float(v) for k, v in (val or {}).items()})
        else:
            raise MappingError(f"unknown key {key!r}; use {SOURCES + ('palettes', 'section_levels')}")
    return out


def load(path: Path | None) -> dict:
    if path is None:
        return validate({})
    import yaml

    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise MappingError("mapping YAML must be a mapping")
    return validate(data)


def band_color(m: dict, band: str, default: str = "#ffffff") -> str:
    for t in m.get(band, []):
        if t["target"] == "emission_color":
            return t["color"]
    return default


def amount(m: dict, band: str, target: str, default: float = 0.0) -> float:
    for t in m.get(band, []):
        if t["target"] == target:
            return float(t.get("amount", default or 1.0))
    return default


def to_yaml(m: dict) -> str:
    import yaml

    return yaml.safe_dump(m, sort_keys=False)
