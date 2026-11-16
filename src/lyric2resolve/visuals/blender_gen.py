"""Prepare an audio-reactive Blender scene for a project: curves + scene_data.json + the bpy script.

Output folder (default <project>/visuals/<template>/):
    scene_data.json   settings for the scene script (fps, frames, template, colours, textures, ...)
    curves.json/.csv  band curves at the project fps (edit/re-tune without re-analysing)
    mapping.yaml      band -> target mapping used
    l2r_scene.py      the Blender script; run:  blender -b -P l2r_scene.py -- scene_data.json
The .blend files are produced by running that script (render/runner.py does it, or by hand).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from lyric2resolve import project as proj

from . import bands, mapping

SCRIPT = Path(__file__).resolve().parent / "blender_template" / "l2r_scene.py"


def pick_texture(textures: list[dict], want: str | None, kind: str = "texture") -> dict | None:
    """want = asset id, a category name, or None (first texture of that kind)."""
    cands = [t for t in textures if t.get("kind") == kind]
    if want:
        exact = [t for t in cands if t["id"] == want] or [t for t in cands if t.get("category") == want]
        return exact[0] if exact else None
    return cands[0] if cands else None


def absolute_maps(asset: dict | None, root: Path) -> dict:
    if not asset:
        return {}
    return {k: str((root / v).resolve()) for k, v in (asset.get("maps") or {}).items()}


def generate(p: proj.Project, out_dir: Path, template: str = "spectrum_bars", aspects: list[str] | None = None,
             mapping_path: Path | None = None, texture: str | None = None, hdri: str | None = None,
             fps: float | None = None, curve_cfg: bands.CurveConfig | None = None, audio=None,
             textures_root: Path | None = None, count: int | None = None, render: dict | None = None) -> Path:
    """Write the scene folder; returns the path of scene_data.json. audio = (array, sr) or None to load."""
    if template not in mapping.TEMPLATES:
        raise ValueError(f"unknown template {template!r}; use one of {mapping.TEMPLATES}")
    # explicit YAML > mapping stored by a project template > defaults
    m = mapping.load(mapping_path) if mapping_path else mapping.validate(p.extra.get("visual_mapping") or {})
    fps = fps or p.settings.fps
    cfg = curve_cfg or bands.CurveConfig(fps=fps)
    cfg.fps = fps
    if audio is None:
        from lyric2resolve.audio import wavio

        song = p.audio.get("song_wav")
        if not song or not Path(song).exists():
            raise FileNotFoundError("the project has no converted song wav (run transcribe/audio-check first)")
        audio = wavio.read(Path(song))
    y, sr = audio
    curves = bands.compute(y, sr, cfg, p.analysis.get("beats"))
    out_dir = Path(out_dir)
    curves.save(out_dir)
    sections = [{"label": s.label, "start": s.start, "end": s.end} for s in p.sections]
    from lyric2resolve.assets import textures as tx

    troot = textures_root or tx.textures_dir()
    lib = tx.list_textures(troot)
    tex_asset = pick_texture(lib, texture, "texture")
    hdri_asset = pick_texture(lib, hdri, "hdri") if hdri else None
    data = {
        "name": f"{proj_safe(p.name)}_{template}",
        "template": template,
        "fps": fps,
        "frames": curves.frames,
        "aspects": aspects or list(p.settings.layouts),
        "curves_file": "curves.json",
        "colors": {b: mapping.band_color(m, b, d) for b, d in (("bass", "#ff7a1a"), ("mids", "#2f7bff"),
                                                                ("highs", "#33ff88"))},
        "mapping": m,
        "sections": sections,
        "section_curve": bands.section_intensity(sections, curves.frames, fps, m["section_levels"]),
        "texture": absolute_maps(tex_asset, troot),
        "texture_info": {k: tex_asset[k] for k in ("id", "name", "source", "license", "url")} if tex_asset else None,
        "hdri": absolute_maps(hdri_asset, troot).get("hdri") if hdri_asset else None,
        "count": count,
        "engine": "EEVEE", "samples": 32, "denoise": True, "bloom": True, "resolution_scale": 1.0,
        "view_transform": "AgX",
    }
    data.update(render or {})
    (out_dir / "scene_data.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
    (out_dir / "mapping.yaml").write_text(mapping.to_yaml(m), encoding="utf-8")
    shutil.copy2(SCRIPT, out_dir / SCRIPT.name)
    return out_dir / "scene_data.json"


def proj_safe(name: str) -> str:
    import re

    return re.sub(r"[^\w\-]+", "_", name).strip("_") or "song"


def main(argv: list[str]) -> int:
    """lyric2resolve visuals project.json [--template T] [--aspect 16:9|9:16|both] [--texture ID|category]
    [--hdri ID] [--mapping mapping.yaml] [--out DIR] [--procedural cracks]"""
    import argparse

    ap = argparse.ArgumentParser(prog="lyric2resolve visuals")
    ap.add_argument("project", type=Path)
    ap.add_argument("--template", default="spectrum_bars", choices=mapping.TEMPLATES)
    ap.add_argument("--aspect", default="both", choices=["16:9", "9:16", "both"])
    ap.add_argument("--texture", help="texture id or category from the library (default: first available)")
    ap.add_argument("--hdri", help="HDRI id from the library")
    ap.add_argument("--mapping", type=Path, help="band -> target mapping YAML")
    ap.add_argument("--procedural", help="generate a procedural mask texture first (noise|grid|hex|cracks|stripes)")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    p = proj.load(args.project)
    if args.procedural:
        from lyric2resolve.assets import textures as tx

        from . import procedural

        procedural.generate(args.procedural, tx.textures_dir() / "procedural")
    out = args.out or args.project.parent / "visuals" / args.template
    aspects = ["16:9", "9:16"] if args.aspect == "both" else [args.aspect]
    try:
        data = generate(p, out, args.template, aspects, args.mapping, args.texture, args.hdri)
    except (ValueError, FileNotFoundError, mapping.MappingError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(f"Scene data: {data}\nBuild the .blend files with:\n  blender -b -P \"{out / SCRIPT.name}\" -- \"{data}\"")
    return 0
