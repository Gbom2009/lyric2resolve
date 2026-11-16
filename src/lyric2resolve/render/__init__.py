"""Headless rendering pipeline: scene -> .blend -> (estimate) -> PNG frames -> MP4 with the song."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from lyric2resolve import project as proj

from . import blender as bl
from . import instructions, mux, presets
from .runner import BlenderRunner, Estimate, Progress


@dataclass
class RenderReport:
    folder: str
    blends: list[str] = field(default_factory=list)
    videos: list[str] = field(default_factory=list)
    estimates: dict = field(default_factory=dict)
    messages: list[str] = field(default_factory=list)
    ok: bool = True
    cancelled: bool = False


def _safe(name: str) -> str:
    import re

    return re.sub(r"[^\w\-]+", "_", name).strip("_")[:60] or "scene"


def section_ranges(p: proj.Project, labels: list[str], fps: float, frames: int) -> list[tuple[int, int, str]]:
    want = {x.lower() for x in labels}
    out = []
    for s in p.sections:
        if s.label.lower() in want or s.id in labels:
            a, b = max(1, int(s.start * fps) + 1), min(frames, int(s.end * fps))
            if b >= a:
                out.append((a, b, f"{s.label}_{s.start:.0f}s"))
    return out


def render_project(project_path: Path, template: str = "spectrum_bars", preset_name="preview",
                   aspects: list[str] | None = None, sections: list[str] | None = None, fps: float | None = None,
                   estimate_only: bool = False, do_mux: bool = True, texture: str | None = None,
                   hdri: str | None = None, mapping_path: Path | None = None, blender: Path | None = None,
                   ffmpeg: str | None = None, runner: BlenderRunner | None = None,
                   on_progress: Callable[[str, Progress], None] = lambda a, p: None,
                   log: Callable[[str], None] = print, cancel: threading.Event | None = None,
                   audio=None, textures_root: Path | None = None, custom_script: Path | None = None,
                   time_range: tuple | None = None, lyrics_3d: bool = False, name: str | None = None,
                   params: dict | None = None, video_only: bool = False) -> RenderReport:
    """Render a scene template (or template='custom' + custom_script) for the whole song, some sections, or a
    time_range (start_s, end_s) = a clip. lyrics_3d adds the lyrics as 3D text. video_only: MP4 without the song
    (for clips on the editor's timeline; the song is already on its own track)."""
    from lyric2resolve.settings import load_settings
    from lyric2resolve.setup_tools import FFMPEG_HELP, find_tool
    from lyric2resolve.visuals import blender_gen

    s, _ = load_settings()
    p = proj.load(project_path)
    if isinstance(preset_name, presets.RenderPreset):
        preset = preset_name if fps is None else presets.replace(preset_name, fps=fps)
    else:
        preset = presets.get(preset_name, fps=fps)
    fps = preset.fps or p.settings.fps
    aspects = aspects or list(p.settings.layouts)
    if runner is None:
        exe = blender or bl.find_blender(s.blender_path)
        if not exe:
            raise RuntimeError(bl.INSTALL_HELP)
        runner = BlenderRunner(exe)
    folder = project_path.parent / "visuals" / ((name and _safe(name)) or template) / preset.name
    render_opts = {"engine": preset.engine, "samples": preset.samples, "denoise": preset.denoise,
                   "bloom": preset.bloom, "resolution_scale": preset.scale(), "view_transform": preset.view_transform}
    data_path = blender_gen.generate(p, folder, template, aspects, mapping_path, texture, hdri, fps=fps,
                                     render=render_opts, audio=audio, textures_root=textures_root,
                                     custom_script=custom_script, lyrics_3d=lyrics_3d, time_range=time_range,
                                     name=name, params=params)
    import json

    data = json.loads(data_path.read_text(encoding="utf-8"))
    frames = int(data["frames"])
    report = RenderReport(str(folder))
    log(f"Building the Blender scene ({template}, {preset.name}, {fps} fps)...")
    blends = runner.build(folder / blender_gen.SCRIPT.name, data_path, log=lambda line: None)
    report.blends = [str(b) for b in blends]
    device, msg = ("EEVEE", "Eevee renders on the GPU automatically.")
    if preset.engine == "CYCLES":
        device, msg = runner.detect_gpu(folder)
    report.messages.append(msg)
    log(msg)
    ranges = [(1, frames, "full")]
    if preset.max_seconds:
        ranges = [(1, min(frames, int(preset.max_seconds * fps)), "preview")]
    if sections:
        ranges = section_ranges(p, sections, fps, frames)
        if not ranges:
            raise RuntimeError(f"no sections named {sections} in this project")
    if time_range:
        a = max(1, int(round(float(time_range[0]) * fps)) + 1)
        b = min(frames, max(a, int(round(float(time_range[1]) * fps))))
        ranges = [(a, b, "clip")]
    dirs = {a: f"frames/{a.replace(':', 'x')}" for a in aspects}
    (folder / "RENDER_INSTRUCTIONS.md").write_text(instructions.blender_markdown(
        p.name, template, fps, frames, frames / fps, preset, aspects,
        {a: Path(b).name for a, b in zip(aspects, blends)}, dirs), encoding="utf-8")
    ff = ffmpeg or (str(find_tool("ffmpeg", s.ffmpeg_path) or "") if do_mux else "")
    if do_mux and not ff and not estimate_only:
        report.messages.append(FFMPEG_HELP)
    song = p.audio.get("song_wav") or p.audio.get("song_source")
    for aspect, blend in zip(aspects, blends):
        w, h = preset.size(aspect)
        out_dir = folder / dirs[aspect]
        job = {"width": w, "height": h, "fps": fps, "engine": preset.engine, "samples": preset.samples,
               "denoise": preset.denoise, "device": device, "view_transform": preset.view_transform,
               "output": str(out_dir / "frame_")}
        est: Estimate = runner.estimate(Path(blend), job, ranges[0][0], ranges[0][1])
        report.estimates[aspect] = est.summary()
        log(f"{aspect}: estimate {est.summary()}")
        if estimate_only:
            continue
        for a, b, label in ranges:
            res = runner.render(Path(blend), job, a, b, lambda pr, asp=aspect: on_progress(asp, pr), cancel)
            if res.cancelled:
                report.ok, report.cancelled = False, True
                report.messages.append("Render cancelled - run the same command again to resume.")
                return report
            if not res.ok:
                report.ok = False
                report.messages.append(res.error)
                return report
            if ff and song and Path(song).exists():
                tag = f"{data['name']}_{aspect.replace(':', 'x')}" + ("" if label == "full" else f"_{label}")
                pattern = str(out_dir / "frame_%04d.png")
                base = mux.MuxSettings(fps=fps, start_seconds=(a - 1) / fps, audio=not video_only)
                encoder = "h264_nvenc" if mux.has_encoder(ff, "h264_nvenc") else "libx264"
                for suffix, box in (("", None), ("_dj", (1920, 1080))):
                    if suffix == "_dj" and (video_only or (w <= 1920 and h <= 1080)):
                        continue  # the master already fits the decks
                    out = folder / f"{tag}{suffix}.mp4"
                    settings = mux.MuxSettings(**{**base.__dict__, "encoder": encoder, "fit_box": box})
                    encoder = mux.encode(ff, pattern, a, Path(song), out, settings, (w, h))
                    report.videos.append(str(out))
                    log(f"video: {out}")
    return report


def main(argv: list[str]) -> int:
    """lyric2resolve render project.json [--template T] [--render-preset NAME] [--aspect 16:9|9:16|both]
    [--sections chorus drop] [--fps 30] [--estimate-only] [--no-mux] [--engine CYCLES] [--samples N] [--height H]"""
    import argparse
    import signal

    from lyric2resolve.visuals import mapping

    ap = argparse.ArgumentParser(prog="lyric2resolve render")
    ap.add_argument("project", type=Path)
    ap.add_argument("--template", default="spectrum_bars", choices=mapping.TEMPLATES)
    ap.add_argument("--render-preset", default="preview", choices=list(presets.PRESETS) + ["custom"])
    ap.add_argument("--aspect", default="both", choices=["16:9", "9:16", "both"])
    ap.add_argument("--sections", nargs="+", help="render only these sections (labels or ids)")
    ap.add_argument("--fps", type=float, help="render at another fps (e.g. 30)")
    ap.add_argument("--engine", choices=["EEVEE", "CYCLES"])
    ap.add_argument("--samples", type=int)
    ap.add_argument("--height", type=int, help="custom height, e.g. 1440")
    ap.add_argument("--texture")
    ap.add_argument("--hdri")
    ap.add_argument("--mapping", type=Path)
    ap.add_argument("--estimate-only", action="store_true")
    ap.add_argument("--no-mux", action="store_true")
    args = ap.parse_args(argv)
    cancel = threading.Event()
    signal.signal(signal.SIGINT, lambda *a: cancel.set())

    def show(aspect: str, pr: Progress) -> None:
        eta = f", ETA {int(pr.eta_s // 60)}:{int(pr.eta_s % 60):02d}" if pr.eta_s else ""
        print(f"\r{aspect} {pr.done}/{pr.total} frames ({pr.fraction:.0%}{eta})   ", end="", flush=True)

    try:
        preset = presets.get(args.render_preset, engine=args.engine, samples=args.samples, height=args.height)
        rep = render_project(args.project, args.template, preset, ["16:9", "9:16"] if args.aspect == "both"
                             else [args.aspect], args.sections, args.fps, args.estimate_only, not args.no_mux,
                             args.texture, args.hdri, args.mapping, on_progress=show, cancel=cancel)
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        print(f"\nERROR: {exc}")
        return 1
    print()
    for m in rep.messages:
        print(m)
    for v in rep.videos:
        print("video:", v)
    print(f"Folder: {rep.folder} (see RENDER_INSTRUCTIONS.md)")
    return 0 if rep.ok else 1
