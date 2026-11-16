"""Exports generated from the edited blocks: FCPXML (Resolve), and more formats in later phases."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from lyric2resolve import project as proj

from .timeline import Plan, build_plan, check_plan

LAYOUT_TAG = {"16:9": "16x9", "9:16": "9x16"}


def safe_name(name: str) -> str:
    return re.sub(r"[^\w\-]+", "_", name).strip("_") or "lyrics"


def _fcpxml(plan: Plan, out: Path, base: str) -> list[Path]:
    from . import fcpxml

    return [fcpxml.write(plan, out / f"{base}_{LAYOUT_TAG[plan.layout]}.fcpxml")]


# format -> writer(plan, out_dir, base_name) for per-layout formats
FORMATS: dict[str, Callable[[Plan, Path, str], list[Path]]] = {"fcpxml": _fcpxml}


def export(project: proj.Project, out_dir: Path, formats: list[str] | None = None,
           layouts: list[str] | None = None, beat_markers: str = "downbeats") -> dict:
    """Write the requested formats for each layout. Returns {"files": [...], "warnings": [...]}."""
    formats = formats or ["fcpxml"]
    layouts = layouts or list(project.settings.layouts)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = safe_name(project.name)
    files: list[Path] = []
    warnings: list[str] = []
    for fmt in formats:
        if fmt not in FORMATS:
            raise ValueError(f"unknown export format {fmt!r}; available: {', '.join(FORMATS)}")
    for layout in layouts:
        plan = build_plan(project, layout, beat_markers)
        problems = check_plan(plan)
        if problems:  # never write a timeline that breaks the rules (e.g. clips in gaps)
            raise RuntimeError("export blocked: " + "; ".join(problems))
        warnings += [f"{layout}: {w}" for w in plan.warnings]
        for fmt in formats:
            files += FORMATS[fmt](plan, out_dir, base)
    return {"files": [str(f) for f in files], "warnings": warnings}


def main(argv: list[str]) -> int:
    """lyric2resolve export project.json [--format fcpxml ...] [--layout 16:9|9:16|both] [--out DIR]"""
    import argparse

    ap = argparse.ArgumentParser(prog="lyric2resolve export")
    ap.add_argument("project", type=Path)
    ap.add_argument("--format", nargs="+", default=["fcpxml"], choices=sorted(FORMATS) + ["all"])
    ap.add_argument("--layout", default="both", choices=["16:9", "9:16", "both"])
    ap.add_argument("--beats", default="downbeats", choices=["downbeats", "all", "none"],
                    help="beat markers on the timeline")
    ap.add_argument("--out", type=Path, help="output folder (default: <project folder>/export)")
    args = ap.parse_args(argv)
    p = proj.load(args.project)
    formats = sorted(FORMATS) if "all" in args.format else args.format
    layouts = ["16:9", "9:16"] if args.layout == "both" else [args.layout]
    try:
        res = export(p, args.out or args.project.parent / "export", formats, layouts, args.beats)
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1
    for f in res["files"]:
        print("written:", f)
    for w in res["warnings"]:
        print("warning:", w)
    return 0
