"""Visuals page API: everything `lyric2resolve render` can do, from the browser.

Rendering itself runs in the background via render.jobs.RenderJobs (/api/render, /api/render/progress,
/api/render/cancel in editor/app.py). This module adds the options, the finished videos and file serving.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

TEMPLATE_INFO = {
    "spectrum_bars": ("Spectrum bars", "A row of glowing bars that jump with bass, mids and highs. Clean and "
                                       "readable behind lyrics."),
    "pulsing_blob": ("Pulsing blob", "A liquid, glowing blob that swells on the bass and ripples on the highs."),
    "tunnel": ("Tunnel", "Flying through a neon tunnel; rings flash on the beat. Great for drops."),
    "particle_field": ("Particle field", "Thousands of sparkles drifting in space, bursting on hits."),
    "floor_grid": ("Neon floor grid", "Retro synthwave grid floor with a glowing horizon that pulses on the bass."),
}
VIDEO_EXT = (".mp4", ".mov", ".webm")


def template_list() -> list[dict]:
    from lyric2resolve.visuals import mapping

    return [{"id": t, "name": TEMPLATE_INFO.get(t, (t, ""))[0], "description": TEMPLATE_INFO.get(t, ("", ""))[1]}
            for t in mapping.TEMPLATES]


def preset_list() -> list[dict]:
    from lyric2resolve.render import presets

    out = []
    for name, p in presets.PRESETS.items():
        out.append({"name": name, "description": p.description, "height": p.height, "engine": p.engine,
                    "fps": p.fps, "max_seconds": p.max_seconds})
    return out


_GPU: list = []


def machine_preset(detect=None) -> dict:
    """The preset the Visuals page selects first on this machine (GPU check runs once: sysctl/nvidia-smi)."""
    from lyric2resolve import setup_tools
    from lyric2resolve.render import presets

    if detect is not None or not _GPU:
        try:
            gpu = (detect or setup_tools.detect_gpu)()
        except Exception:
            gpu = setup_tools.GpuInfo()
        if detect is None:
            _GPU.append(gpu)
    else:
        gpu = _GPU[0]
    name, why = presets.recommended(gpu)
    return {"name": name, "reason": why}


def tool_status(settings) -> dict:
    from lyric2resolve import setup_tools
    from lyric2resolve.render.blender import find_blender

    bl = find_blender(settings.blender_path)
    ff = setup_tools.find_tool("ffmpeg", settings.ffmpeg_path)
    return {"blender": str(bl or ""), "blender_help": "" if bl else setup_tools.BLENDER_HELP,
            "ffmpeg": str(ff or ""), "ffmpeg_help": "" if ff else setup_tools.FFMPEG_HELP}


def list_videos(project_dir: Path) -> list[dict]:
    """Finished videos under <project>/visuals (newest first), with paths relative to the project folder."""
    root = Path(project_dir) / "visuals"
    if not root.is_dir():
        return []
    out = []
    for f in root.rglob("*"):
        if f.suffix.lower() in VIDEO_EXT and f.is_file() and "_estimate" not in f.parts:
            st = f.stat()
            rel = f.relative_to(project_dir).as_posix()
            out.append({"name": f.name, "path": rel, "folder": f.parent.relative_to(project_dir).as_posix(),
                        "size_mb": round(st.st_size / 1e6, 1), "modified": time.strftime(
                            "%Y-%m-%d %H:%M", time.localtime(st.st_mtime)), "mtime": st.st_mtime,
                        "instructions": (f.parent / "RENDER_INSTRUCTIONS.md").is_file()})
    out.sort(key=lambda d: d["mtime"], reverse=True)
    return out


def open_in_explorer(path: Path, opener: Callable[[list[str]], object] | None = None) -> None:
    path = Path(path)
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # noqa: S606 - local folder of the user's own project
        return
    cmd = ["open" if sys.platform == "darwin" else "xdg-open", str(path)]
    (opener or (lambda c: subprocess.Popen(c)))(cmd)


def register(app, current, settings_dir: Path | None = None, opener=None) -> None:
    from fastapi import Body, HTTPException
    from fastapi.responses import FileResponse

    def project_dir() -> Path:
        return current().path.parent

    @app.get("/api/visuals/options")
    def options():
        from lyric2resolve.settings import load_settings

        s = current()
        p = s.project
        return {"templates": template_list(), "presets": preset_list(), "recommended": machine_preset(),
                "layouts": list(p.settings.layouts), "fps": p.settings.fps,
                "sections": [{"id": x.id, "label": x.label, "start": x.start, "end": x.end} for x in p.sections],
                "tools": tool_status(load_settings(settings_dir)[0]), "folder": str(project_dir() / "visuals")}

    @app.get("/api/visuals/videos")
    def videos():
        return {"videos": list_videos(project_dir()), "folder": str(project_dir() / "visuals")}

    @app.get("/api/visuals/file/{rel:path}")
    def video_file(rel: str):
        root = (project_dir() / "visuals").resolve()
        f = (project_dir() / rel).resolve()
        if root not in f.parents or not f.is_file() or f.suffix.lower() not in VIDEO_EXT + (".md", ".png"):
            raise HTTPException(status_code=404, detail="file not found")
        media = {".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm", ".md": "text/markdown",
                 ".png": "image/png"}[f.suffix.lower()]
        return FileResponse(f, media_type=media)

    @app.post("/api/visuals/open-folder")
    def open_folder(body: dict = Body(default_factory=dict)):
        root = (project_dir() / "visuals").resolve()
        root.mkdir(parents=True, exist_ok=True)
        target = (project_dir() / str(body.get("folder") or "visuals")).resolve()
        if target != root and root not in target.parents:
            raise HTTPException(status_code=403, detail="only folders inside the project's visuals folder")
        if not target.is_dir():
            raise HTTPException(status_code=404, detail="folder not found")
        try:
            open_in_explorer(target, opener)
        except OSError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"opened": str(target)}
