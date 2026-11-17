"""Clips track API: your own videos/images and Blender-rendered clips (incl. Claude's custom scenes).

Clips live in the project (project.clips, edited with the undoable ops add_clip/update_clip/remove_clip);
their files are stored in <project>/clips/ (uploads) or <project>/visuals/<name>/... (renders).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

VIDEO_EXT = (".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
_DUR = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


def _flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform.startswith("win") else 0


def media_duration(ffmpeg: str, path: Path) -> float | None:
    """Seconds, read from `ffmpeg -i` (ffprobe is not always installed next to ffmpeg)."""
    try:
        out = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path)], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=60, creationflags=_flags())
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = _DUR.search(out.stderr or "")
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else None


def image_to_video(ffmpeg: str, image: Path, out: Path, seconds: float, fps: float, size: tuple[int, int]) -> Path:
    """A still image as a short H.264 video (so every clip on the track is a video)."""
    w, h = size
    vf = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,"
          "format=yuv420p")
    from lyric2resolve.render import mux

    base = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-loop", "1", "-i", str(image), "-t", f"{seconds:.3f}",
            "-r", f"{fps:g}", "-vf", vf]
    encoders = mux.h264_candidates(ffmpeg) or ["libx264"]
    err = ""
    for enc in encoders:  # this ffmpeg's H.264 encoders, best first (some builds have no libx264)
        res = subprocess.run(base + mux.encoder_args(enc, 18, "fast") + ["-an", str(out)], capture_output=True,
                             text=True, creationflags=_flags())
        if res.returncode == 0 and out.exists():
            return out
        err = res.stderr.strip()[-300:]
    raise RuntimeError(f"could not turn the image into a video: {err}"
                       + ("" if mux.h264_candidates(ffmpeg) else f"\n{mux.NO_H264_HELP}"))


def unique_file(folder: Path, name: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    name = Path(name or "clip").name.replace("..", "_") or "clip"
    dst, n = folder / name, 2
    while dst.exists():
        dst = folder / f"{Path(name).stem} ({n}){Path(name).suffix}"
        n += 1
    return dst


def clip_from_render(progress: dict, layouts: list[str]) -> dict:
    """Render result -> add_clip arguments (path per layout)."""
    videos = (progress.get("report") or {}).get("videos") or []
    paths = {}
    for lay in layouts:
        tag = lay.replace(":", "x")
        hit = next((v for v in videos if tag in Path(v).name and not Path(v).stem.endswith("_dj")), None)
        if hit:
            paths[lay] = hit
    if not paths and videos:
        paths[layouts[0]] = videos[0]
    return {"path": paths.get(layouts[0]) or next(iter(paths.values())), "paths": paths}


def register(app, current, jobs_getter: Callable, settings_dir: Path | None = None) -> None:
    from fastapi import Body, File, Form, HTTPException, UploadFile
    from fastapi.responses import FileResponse

    from lyric2resolve.editor import ops

    def ffmpeg_exe() -> str:
        from lyric2resolve.settings import load_settings
        from lyric2resolve.setup_tools import FFMPEG_HELP, find_tool

        exe = find_tool("ffmpeg", load_settings(settings_dir)[0].ffmpeg_path)
        if not exe:
            raise HTTPException(status_code=424, detail=FFMPEG_HELP)
        return str(exe)

    def apply(name: str, args: dict) -> dict:
        try:
            return current().apply(name, args)
        except ops.OpError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def upload_clip(file: UploadFile = File(...), start: float = Form(...), end: float = Form(0.0),
                    hide_lyrics: bool = Form(False), snap: bool = Form(False)):
        s = current()
        ext = Path(file.filename or "").suffix.lower()
        if ext not in VIDEO_EXT + IMAGE_EXT:
            raise HTTPException(status_code=400, detail=f"use a video ({', '.join(VIDEO_EXT)}) or an image "
                                                        f"({', '.join(IMAGE_EXT)})")
        folder = s.path.parent / "clips"
        dst = unique_file(folder, file.filename or f"clip{ext}")
        with open(dst, "wb") as f:
            shutil.copyfileobj(file.file, f, 1024 * 1024)
        ff = ffmpeg_exe()
        if ext in IMAGE_EXT:
            length = (end - start) if end > start else 4.0
            cfg = s.project.settings
            size = (cfg.width, cfg.height)
            dst = image_to_video(ff, dst, dst.with_suffix(".mp4"), length, cfg.fps, size)
            end = start + length
        else:
            dur = media_duration(ff, dst)
            if end <= start:
                end = start + min(dur or 4.0, 30.0)
            elif dur:
                end = min(end, start + dur)  # a clip cannot be longer than its file
        return apply("add_clip", {"path": str(dst.resolve()), "start": start, "end": end, "name": dst.stem,
                                  "source": "file", "hide_lyrics": hide_lyrics, "snap": snap})

    upload_clip.__annotations__["file"] = UploadFile  # real class: FastAPI + `from __future__ import annotations`
    app.post("/api/clips/upload")(upload_clip)

    @app.post("/api/clips/render")
    def render_clip(body: dict = Body(...)):
        """Render a scene for a time range as a clip; when it is done it is put on the clips track."""
        from lyric2resolve.visuals import custom

        s = current()
        p = s.project
        start, end = float(body.get("start", 0)), float(body.get("end", 0))
        if body.get("snap"):
            start, end = ops.snap_to_bar(p, start), ops.snap_to_bar(p, end)
        if end <= start:
            raise HTTPException(status_code=400, detail="the clip needs an end after its start")
        name = custom.safe_name(str(body.get("name") or "clip"))
        template = str(body.get("template") or "custom")
        script = None
        if template == "custom":
            try:
                script = custom.resolve_script(s.path.parent, str(body.get("script") or
                                                                  custom.scene_path(s.path.parent, name)))
            except FileNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
        layouts = list(body.get("layouts") or p.settings.layouts)
        hide = bool(body.get("hide_lyrics", False))
        info = {"template": template, "script": str(script) if script else None, "preset": body.get("preset"),
                "params": body.get("params") or {}, "prompt": body.get("prompt", "")}

        def done(progress: dict) -> None:
            res = clip_from_render(progress, layouts)
            existing = next((c for c in s.project.clips if c.info.get("render_name") == name), None)
            args = {"path": res["path"], "start": start, "end": end, "name": name, "source": "render",
                    "hide_lyrics": hide, "info": {**info, "paths": res["paths"], "render_name": name}}
            if existing:  # re-render of the same clip: replace it in place
                s.apply("remove_clip", {"clip_id": existing.id})
            s.apply("add_clip", args)

        try:
            return jobs_getter().start(s.path, template=template, preset=str(body.get("preset") or "preview"),
                                       aspects=layouts, custom_script=script, time_range=(start, end),
                                       lyrics_3d=bool(body.get("lyrics_3d", False)), name=name,
                                       params=body.get("params") or {}, video_only=True, on_done=done)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/clips/file/{clip_id}")
    def clip_file(clip_id: str, layout: str = ""):
        c = next((x for x in current().project.clips if x.id == clip_id), None)
        if c is None:
            raise HTTPException(status_code=404, detail="no such clip")
        f = Path((c.info.get("paths") or {}).get(layout) or c.path)
        if not f.is_file():
            raise HTTPException(status_code=404, detail=f"clip file missing: {f}")
        return FileResponse(f)

    @app.get("/api/clips/guide")
    def clip_guide():
        from lyric2resolve.visuals import custom

        return {"guide": custom.guide()}
