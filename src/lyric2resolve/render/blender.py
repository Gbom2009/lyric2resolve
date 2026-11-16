"""Blender detection and command building (no Blender needed to test this module)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from lyric2resolve import setup_tools

INSTALL_HELP = (
    "Blender was not found. Install it (free) from https://www.blender.org/download/ "
    "(or: winget install BlenderFoundation.Blender), then restart the app. If it is installed in an unusual "
    "folder, set its path in Settings (blender_path).")

# Small script run inside Blender to report GPU render devices (OptiX preferred, then CUDA).
GPU_PROBE = r'''
import bpy, json
out = {"backends": {}}
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for backend in ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"):
        try:
            prefs.compute_device_type = backend
            prefs.get_devices()
            devs = [d.name for d in prefs.devices if d.type == backend]
            if devs:
                out["backends"][backend] = devs
        except TypeError:
            pass
except Exception as exc:
    out["error"] = str(exc)
print("L2R_GPU" + json.dumps(out))
'''


def find_blender(configured: str = "", **kw) -> Path | None:
    return setup_tools.find_tool("blender", configured, **kw)


def parse_version(text: str) -> tuple[int, int, int] | None:
    m = re.search(r"Blender (\d+)\.(\d+)(?:\.(\d+))?", text or "")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)) if m else None


def parse_gpu_probe(stdout: str) -> dict:
    for line in (stdout or "").splitlines():
        if line.startswith("L2R_GPU"):
            try:
                return json.loads(line[7:])
            except ValueError:
                break
    return {"backends": {}}


def choose_device(probe: dict) -> tuple[str, str]:
    """('OPTIX'|'CUDA'|'HIP'|'ONEAPI'|'METAL'|'CPU', human message)."""
    backends = probe.get("backends") or {}
    for b in ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"):
        if backends.get(b):
            return b, f"GPU rendering with {b}: {', '.join(backends[b])}"
    return "CPU", ("WARNING: no GPU found for Cycles - rendering on the CPU will be much slower. Check the NVIDIA "
                   "driver, or use Eevee (it uses the GPU through OpenGL/Vulkan anyway).")


def build_command(blender: Path, scene_script: Path, scene_data: Path) -> list[str]:
    """Build the .blend files from scene_data.json."""
    return [str(blender), "-b", "--factory-startup", "-noaudio", "-P", str(scene_script), "--", str(scene_data)]


def render_command(blender: Path, blend: Path, setup_script: Path, job: Path, start: int, end: int) -> list[str]:
    """Render frames start..end (Blender runs the setup script first, then renders the animation)."""
    # Blender reads its arguments in order and stops at "--": the setup script must run before -s/-e/-a,
    # and everything after "--" (the job file) is only for the script.
    return [str(blender), "-b", "--factory-startup", "-noaudio", str(blend), "-P", str(setup_script),
            "-s", str(start), "-e", str(end), "-a", "--", str(job)]


# Runs inside Blender before rendering: applies preset, GPU device, resume settings and output path.
RENDER_SETUP = r'''
import bpy, json, sys
argv = sys.argv[sys.argv.index("--") + 1:]
job = json.load(open(argv[0], encoding="utf-8"))
sc = bpy.context.scene
r = sc.render
r.resolution_x, r.resolution_y = job["width"], job["height"]
r.resolution_percentage = 100
if job.get("fps"):
    fps = job["fps"]
    ntsc = {23.976: 24, 29.97: 30, 59.94: 60}
    base = next((v for k, v in ntsc.items() if abs(fps - k) < 0.01), None)
    r.fps, r.fps_base = (base, 1.001) if base else (int(round(fps)), 1.0)
engines = {e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
if job["engine"] == "CYCLES":
    r.engine = "CYCLES"
    sc.cycles.samples = job["samples"]
    sc.cycles.use_denoising = job["denoise"]
    dev = job.get("device", "CPU")
    if dev != "CPU":
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = dev
        prefs.get_devices()
        for d in prefs.devices:
            d.use = d.type == dev
        sc.cycles.device = "GPU"
    else:
        sc.cycles.device = "CPU"
else:
    r.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in engines else "BLENDER_EEVEE_NEXT"
    try:
        sc.eevee.taa_render_samples = job["samples"]
    except AttributeError:
        pass
try:
    sc.view_settings.view_transform = job.get("view_transform", "AgX")
except TypeError:
    pass
r.filepath = job["output"]
r.image_settings.file_format = "PNG"
r.use_overwrite = False      # resume: frames that already exist are skipped
r.use_placeholder = True     # lets several Blender processes share a frame range safely
print("L2R_SETUP ok", r.engine, r.resolution_x, r.resolution_y, flush=True)
'''
