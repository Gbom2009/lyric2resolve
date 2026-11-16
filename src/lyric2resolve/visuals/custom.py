"""Custom Blender scenes (written by you or by Claude in the Assistant) and how lyric2resolve runs them."""

from __future__ import annotations

import re
from pathlib import Path

EXAMPLES_DIR = Path(__file__).resolve().parent / "scene_examples"
SCENES_DIR = "scenes"   # inside the project folder: scenes/<name>/scene.py

GUIDE = """\
# Writing a custom lyric2resolve scene (Blender Python)

Put the script at `scenes/<name>/scene.py` inside the project folder and define ONE function:

    def build_scene(ctx) -> dict:
        ...build objects, materials, animation with ctx["bpy"]...
        return {"camera": ((x, y, z), (rot_x, rot_y, rot_z))}   # radians; default looks at the origin from -Y

lyric2resolve already did: empty scene, world background, render settings (Eevee/Cycles, resolution for 16:9 or
9:16, fps), an `L2R_Controller` object carrying the audio curves, and it adds AFTER your function: the camera at
your position with a small beat shake, a point light following the loudness, optional 3D lyrics, bloom/glare, saving
and rendering. Do not create a camera, do not save files, do not change render settings.

## ctx
- bpy: the Blender module. aspect: "16:9" or "9:16". fps: float. frames: last frame of the song.
- frame_of(seconds) -> frame number. time_range: [start_s, end_s] of the clip being rendered (or None = whole song).
- beats, downbeats: lists of seconds (bars start on downbeats). bpm: float or None.
- lyrics: [{"text", "start", "end", "words": [{"text","start","end"}]}] in seconds.
- ctrl: the controller object. Audio-reactive animation = drivers on its custom properties
  "bass", "mids", "highs", "rms", "onset", "beat" (0..1, smoothed) and "section" (intensity per song part).
- add_driver(target, data_path, ctrl, "bass", "expression with v (the band) and s (section)", index=-1)
  e.g. add_driver(obj, "scale", ctrl, "bass", "1 + v * 0.3", 2)
       add_driver(principled.inputs["Emission Strength"], "default_value", ctrl, "highs", "2 + v * 10 * s")
- emissive_material(name, ctrl, band, "#rrggbb", strength) -> ready glowing material driven by a band.
- hex_rgba("#rrggbb") -> linear RGBA for colour sockets. colors: {"bass","mids","highs"} hex colours of the project.
- floor(z): adds a dark reflective floor plane at height z. mk(op, **kw): run a bpy.ops.mesh.* add op, return the object.
- load_image(path): load an image (e.g. one of the user's reference files in ../../context/).
- folder: the render folder (Path). data["params"]: extra values passed when rendering (e.g. {"text": "ACID"}).

## Rules
- Keep it renderable: Eevee by default; avoid physics simulations that need baking (use animated shaders,
  keyframes, drivers, geometry nodes instead). Liquid looks: Wave/Noise textures moving over time + emission +
  low roughness, drops = small spheres keyframed along Z.
- Animate only inside time_range (frame_of(start) .. frame_of(end)) when it is set; the rest is not rendered.
- Keep it self-contained (only bpy, math, random, mathutils). Any error in build_scene stops the render and is shown.
- Then call the `render_clip` tool with the script path and the time range; the clip lands on the editor's clips track.

## Example: scenes/acid/scene.py  (3D "ACID" with glowing green liquid dripping down)
"""


def guide() -> str:
    return GUIDE + "\n```python\n" + (EXAMPLES_DIR / "acid_drip.py").read_text(encoding="utf-8") + "```\n"


def safe_name(name: str) -> str:
    return re.sub(r"[^\w\-]+", "_", (name or "").strip()).strip("_")[:60] or "scene"


def scene_path(project_dir: Path, name: str) -> Path:
    return Path(project_dir) / SCENES_DIR / safe_name(name) / "scene.py"


def resolve_script(project_dir: Path, script: str) -> Path:
    """A script path from Claude/the UI -> absolute path, only inside the project folder."""
    root = Path(project_dir).resolve()
    p = (root / script).resolve() if not Path(script).is_absolute() else Path(script).resolve()
    if root not in p.parents or p.suffix != ".py" or not p.is_file():
        raise FileNotFoundError(f"scene script not found inside the project folder: {script}")
    return p
