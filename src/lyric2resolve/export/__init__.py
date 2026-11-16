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


def _text(plan: Plan, out: Path, base: str) -> list[Path]:
    from . import textformats

    return textformats.write_all(plan, out, base, LAYOUT_TAG[plan.layout])


# format -> writer(plan, out_dir, base_name) for per-layout formats
FORMATS: dict[str, Callable[[Plan, Path, str], list[Path]]] = {"fcpxml": _fcpxml, "srt_csv_edl": _text}
# formats that need all layouts at once
MULTI_FORMATS = ("resolve",)
ALL_FORMATS = sorted(FORMATS) + list(MULTI_FORMATS)


def export(project: proj.Project, out_dir: Path, formats: list[str] | None = None,
           layouts: list[str] | None = None, beat_markers: str = "downbeats", data_root: Path | None = None,
           install_resolve_script: bool = False) -> dict:
    """Write the requested formats for each layout. Returns {"files": [...], "warnings": [...]}."""
    formats = formats or ["fcpxml"]
    layouts = layouts or list(project.settings.layouts)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = safe_name(project.name)
    files: list[Path] = []
    warnings: list[str] = []
    for fmt in formats:
        if fmt not in ALL_FORMATS:
            raise ValueError(f"unknown export format {fmt!r}; available: {', '.join(ALL_FORMATS)}")
    per_layout = [f for f in formats if f in FORMATS]
    if "resolve" in formats and "fcpxml" not in per_layout:
        per_layout.append("fcpxml")  # the Resolve script falls back to the FCPXML
    plans: list[Plan] = []
    fcpxml_paths: dict[str, str] = {}
    for layout in layouts:
        plan = build_plan(project, layout, beat_markers)
        problems = check_plan(plan)
        if problems:  # never write a timeline that breaks the rules (e.g. clips in gaps)
            raise RuntimeError("export blocked: " + "; ".join(problems))
        warnings += [f"{layout}: {w}" for w in plan.warnings]
        plans.append(plan)
        for fmt in per_layout:
            written = FORMATS[fmt](plan, out_dir, base)
            if fmt == "fcpxml":
                fcpxml_paths[layout] = str(written[0].resolve())
            files += written
    installed = None
    if "resolve" in formats and plans:
        from . import resolve_job

        files += resolve_job.write_job(plans, fcpxml_paths, out_dir, base, data_root)
        if install_resolve_script:
            try:
                installed = str(resolve_job.install_script())
            except OSError as exc:
                warnings.append(f"could not install the Resolve script: {exc}")
    return {"files": [str(f) for f in files], "warnings": warnings, "resolve_script": installed}


def main(argv: list[str]) -> int:
    """lyric2resolve export project.json [--format fcpxml ...] [--layout 16:9|9:16|both] [--out DIR]"""
    import argparse

    ap = argparse.ArgumentParser(prog="lyric2resolve export")
    ap.add_argument("project", type=Path)
    ap.add_argument("--format", nargs="+", default=["fcpxml"], choices=ALL_FORMATS + ["all"])
    ap.add_argument("--layout", default="both", choices=["16:9", "9:16", "both"])
    ap.add_argument("--beats", default="downbeats", choices=["downbeats", "all", "none"],
                    help="beat markers on the timeline")
    ap.add_argument("--out", type=Path, help="output folder (default: <project folder>/export)")
    args = ap.parse_args(argv)
    p = proj.load(args.project)
    formats = ALL_FORMATS if "all" in args.format else args.format
    layouts = ["16:9", "9:16"] if args.layout == "both" else [args.layout]
    try:
        res = export(p, args.out or args.project.parent / "export", formats, layouts, args.beats,
                     install_resolve_script="resolve" in formats)
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1
    for f in res["files"]:
        print("written:", f)
    for w in res["warnings"]:
        print("warning:", w)
    if res.get("resolve_script"):
        print(f"Resolve script installed: {res['resolve_script']}\n"
              "In Resolve: Workspace > Scripts > Utility > lyric2resolve_build_timeline")
    return 0
