"""Resolve script export: job JSON for resolve_build_timeline + installing the script into Resolve."""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import asdict
from pathlib import Path

from lyric2resolve import paths

from .timeline import Plan

SCRIPT_NAME = "lyric2resolve_build_timeline.py"
TEMPLATE = Path(__file__).resolve().parent / "resolve_template" / SCRIPT_NAME


def job_dict(plans: list[Plan], fcpxml_paths: dict[str, str]) -> dict:
    p0 = plans[0]
    return {
        "version": 1,
        "project_name": p0.project_name,
        "song_path": p0.song_path,
        "fps": float(p0.rate.fps),
        "start_timecode": _tc(p0),
        "styling_level": p0.styling_level,
        "timelines": [{
            "layout": p.layout,
            "name": f"{p.project_name or 'Lyrics'} {p.layout.replace(':', 'x')} (l2r)",
            "width": p.width, "height": p.height,
            "duration_frames": p.duration_frames,
            "fcpxml": fcpxml_paths.get(p.layout, ""),
            "clips": [{"start": c.start_frame, "end": c.end_frame, "text": c.text, "lines": c.lines,
                       "font_px": c.font_px, "x": c.x, "y": c.y, "style": c.style.to_dict(),
                       "words": [[w.text, w.start_frame, w.end_frame] for w in c.words]} for c in p.clips],
            "markers": [asdict(m) for m in p.markers],
        } for p in plans],
    }


def _tc(plan: Plan) -> str:
    from .timecode import frames_to_tc

    return frames_to_tc(plan.start_tc_frames, plan.rate)


def write_job(plans: list[Plan], fcpxml_paths: dict[str, str], out: Path, base: str,
              data_root: Path | None = None) -> list[Path]:
    """Write <base>_resolve_job.json + point the 'last job' file (read by the script) at it."""
    job_path = out / f"{base}_resolve_job.json"
    job_path.write_text(json.dumps(job_dict(plans, fcpxml_paths), indent=1, ensure_ascii=False), encoding="utf-8")
    root = data_root or paths.ensure_data_dir()
    pointer = root / "exports" / "last_resolve_job.json"
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(json.dumps({"job": str(job_path.resolve())}), encoding="utf-8")
    script_copy = out / SCRIPT_NAME
    shutil.copy2(TEMPLATE, script_copy)
    return [job_path, script_copy]


def resolve_scripts_dir(env: dict | None = None, platform: str | None = None) -> Path:
    """Per-user Resolve scripts folder (Utility = listed on every page)."""
    env = os.environ if env is None else env
    platform = platform or sys.platform
    if platform.startswith("win"):
        base = Path(env.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
        return base / "Blackmagic Design" / "DaVinci Resolve" / "Support" / "Fusion" / "Scripts" / "Utility"
    if platform == "darwin":
        return (Path.home() / "Library" / "Application Support" / "Blackmagic Design" / "DaVinci Resolve" /
                "Fusion" / "Scripts" / "Utility")
    return Path.home() / ".local" / "share" / "DaVinciResolve" / "Fusion" / "Scripts" / "Utility"


def install_script(target_dir: Path | None = None, store_python: bool | None = None, run=None) -> Path:
    target_dir = target_dir or resolve_scripts_dir()
    dst = target_dir / SCRIPT_NAME
    if store_python is None:
        store_python = sys.platform.startswith("win") and paths.store_python()
    if store_python:
        # Microsoft Store Python hides what it writes in AppData from other programs (Resolve would never see the
        # script). A child process is not affected, so let cmd.exe create the folder and copy the file.
        import subprocess

        run = run or (lambda cmd: subprocess.run(cmd, capture_output=True, text=True,
                                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)))
        run(["cmd", "/c", "mkdir", str(target_dir)])
        res = run(["cmd", "/c", "copy", "/Y", str(TEMPLATE), str(dst)])
        if getattr(res, "returncode", 0) != 0:
            raise OSError(f"could not copy the Resolve script to {dst}: {getattr(res, 'stderr', '')}")
        return dst
    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TEMPLATE, dst)
    return dst
