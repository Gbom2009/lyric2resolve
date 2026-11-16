"""lyric2resolve - audio-reactive Blender scene builder (self-contained; Blender 4.2 - 5.x).

    blender -b -P l2r_scene.py -- scene_data.json        (or: python l2r_scene.py scene_data.json  with the bpy module)

Reads scene_data.json (written by lyric2resolve) + the curves JSON next to it and saves one .blend per
aspect ratio (16:9 and/or 9:16). How it works:
  - an empty "L2R_Controller" carries the audio curves as keyframed custom properties
    (bass, mids, highs, rms, onset, beat, section) - re-run apply_curves() after editing curves.json;
  - every reactive property (emission strength/colour, scale, displacement, rotation, sparkles, camera
    shake, light) is a simple-expression DRIVER on those properties (no Python auto-run needed);
  - materials layer audio-reactive emission on top of PBR textures from the library, masked by a
    noise/height pattern.
Alternative without this script: Graph Editor > Channel > Bake Sound to F-Curves (see RENDER_INSTRUCTIONS.md).
"""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

import bpy

CURVE_NAMES = ("bass", "mids", "highs", "rms", "onset", "beat", "section")


# ------------------------------------------------------------------ helpers
def hex_rgba(h: str, a: float = 1.0) -> tuple[float, float, float, float]:
    n = int(h[1:], 16)

    def lin(c: float) -> float:  # sRGB -> linear (Blender colour sockets are linear)
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return (lin(((n >> 16) & 255) / 255), lin(((n >> 8) & 255) / 255), lin((n & 255) / 255), a)


def clear_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def find_fcurve(idblock, data_path: str, index: int = 0):
    ad = idblock.animation_data
    action = ad.action if ad else None
    if action is None:
        return None
    fcurves = getattr(action, "fcurves", None)  # legacy actions (<= 4.3)
    if fcurves is None or not len(fcurves):
        try:  # slotted / layered actions (4.4+, 5.x)
            from bpy_extras import anim_utils

            bag = anim_utils.action_get_channelbag_for_slot(action, ad.action_slot)
            fcurves = bag.fcurves if bag else []
        except Exception:  # noqa: BLE001
            fcurves = []
    for fc in fcurves:
        if fc.data_path == data_path and fc.array_index == index:
            return fc
    return None


def set_curve(obj, prop: str, values: list[float], start_frame: int = 1, constant: bool = False) -> None:
    """Fast keyframing of a custom property (one key per frame) via keyframe_points.add + foreach_set."""
    if not values:
        values = [0.0]
    obj[prop] = float(values[0])
    path = f'["{prop}"]'
    fc = find_fcurve(obj, path)
    if fc is not None:
        fc.keyframe_points.clear()
    obj.keyframe_insert(data_path=path, frame=start_frame)
    fc = find_fcurve(obj, path)
    kp = fc.keyframe_points
    kp.add(len(values) - 1)
    co = []
    for i, v in enumerate(values):
        co += [float(start_frame + i), float(v)]
    kp.foreach_set("co", co)
    for k in kp:
        k.interpolation = "CONSTANT" if constant else "LINEAR"
    fc.update()


def add_driver(target, path: str, controller, var_prop: str, expr: str, index: int = -1):
    """Driver on target.path[index] = expr, with variable v = controller[var_prop] and s = section."""
    fcs = target.driver_add(path, index) if index >= 0 else target.driver_add(path)
    fcs = fcs if isinstance(fcs, list) else [fcs]
    for fc in fcs:
        d = fc.driver
        d.type = "SCRIPTED"
        for name, prop in (("v", var_prop), ("s", "section")):
            var = d.variables.new()
            var.name = name
            var.type = "SINGLE_PROP"
            var.targets[0].id_type = "OBJECT"
            var.targets[0].id = controller
            var.targets[0].data_path = f'["{prop}"]'
        d.expression = expr
    return fcs


def load_image(path: str | None, non_color: bool = False):
    if not path or not Path(path).exists():
        return None
    img = bpy.data.images.load(path, check_existing=True)
    if non_color:
        try:
            img.colorspace_settings.name = "Non-Color"
        except TypeError:
            pass
    return img


def emissive_material(name: str, ctrl, band: str, color: str, strength: float, base: str = "#0b0d12",
                      tex: dict | None = None, mask_scale: float = 6.0, palette_driven: bool = True):
    """Principled BSDF (+ optional PBR textures) with audio-driven emission masked by noise/height."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = hex_rgba(base)
    bsdf.inputs["Roughness"].default_value = 0.35
    tex = tex or {}
    tc = nt.nodes.new("ShaderNodeTexCoord")
    col = load_image(tex.get("color"))
    if col:
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = col
        nt.links.new(tc.outputs["UV"], n.inputs["Vector"])
        dark = nt.nodes.new("ShaderNodeMixRGB") if hasattr(bpy.types, "ShaderNodeMixRGB") else None
        if dark is not None:  # darken the photo so the glow reads
            dark.blend_type = "MULTIPLY"
            dark.inputs[0].default_value = 0.6
            dark.inputs[2].default_value = (0.35, 0.35, 0.35, 1)
            nt.links.new(n.outputs["Color"], dark.inputs[1])
            nt.links.new(dark.outputs[0], bsdf.inputs["Base Color"])
        else:
            nt.links.new(n.outputs["Color"], bsdf.inputs["Base Color"])
    rough = load_image(tex.get("roughness"), True)
    if rough:
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = rough
        nt.links.new(tc.outputs["UV"], n.inputs["Vector"])
        nt.links.new(n.outputs["Color"], bsdf.inputs["Roughness"])
    nrm = load_image(tex.get("normal"), True)
    if nrm:
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = nrm
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nt.links.new(tc.outputs["UV"], n.inputs["Vector"])
        nt.links.new(n.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    # emission mask: emission map > height map > procedural noise (crack-like voronoi edges for variety)
    mask_img = load_image(tex.get("emission") or tex.get("height"), True)
    if mask_img:
        mask = nt.nodes.new("ShaderNodeTexImage")
        mask.image = mask_img
        nt.links.new(tc.outputs["UV"], mask.inputs["Vector"])
        mask_out = mask.outputs["Color"]
    else:
        mask = nt.nodes.new("ShaderNodeTexNoise")
        mask.inputs["Scale"].default_value = mask_scale
        nt.links.new(tc.outputs["Object"], mask.inputs["Vector"])
        mask_out = mask.outputs["Fac"]
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.35
    nt.links.new(mask_out, ramp.inputs["Fac"])
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    nt.links.new(ramp.outputs["Color"], mul.inputs[0])
    nt.links.new(mul.outputs[0], bsdf.inputs["Emission Strength"])
    bsdf.inputs["Emission Color"].default_value = hex_rgba(color)
    # drivers: strength = band * amount * section ; colour = keyed per section (palette)
    add_driver(nt, f'nodes["{mul.name}"].inputs[1].default_value', ctrl, band, f"(0.15 + v) * {strength:.3f} * s")
    if palette_driven:
        for i, ch in enumerate("rgb"):
            add_driver(nt, f'nodes["{bsdf.name}"].inputs["Emission Color"].default_value', ctrl, f"{band}_{ch}",
                       "v", index=i)
    return mat


# ------------------------------------------------------------------ scene templates
def mk(obj_data_op, **kw):
    obj_data_op(**kw)
    return bpy.context.active_object


def template_spectrum_bars(ctx):
    bars = ctx["count"] or 32
    objs = []
    from mathutils import Matrix

    for i in range(bars):
        x = (i - (bars - 1) / 2) * 0.3
        ob = mk(bpy.ops.mesh.primitive_cube_add, size=0.22, location=(x, 0, 0))
        ob.data.transform(Matrix.Translation((0, 0, 0.11)))  # origin at the bottom: bars grow upwards
        band = "bass" if i < bars / 3 else "mids" if i < 2 * bars / 3 else "highs"
        ob.data.materials.append(ctx["mats"][band])
        amt = 6.0 + ctx["amount"](band, "scale", 0.25) * 20
        add_driver(ob, "scale", ctx["ctrl"], band, f"0.5 + v * {amt:.3f} * s * {0.55 + 0.45 * math.sin(i * 0.7) ** 2:.3f}", 2)
        objs.append(ob)
    ctx["floor"](0.0)
    return {"camera": ((0, -11.5, 2.6), (math.radians(82), 0, 0)), "focus": objs}


def template_pulsing_blob(ctx):
    ob = mk(bpy.ops.mesh.primitive_ico_sphere_add, subdivisions=5, radius=1.4, location=(0, 0, 1.4))
    bpy.ops.object.shade_smooth()
    tex = bpy.data.textures.new("L2R_BlobNoise", "CLOUDS")
    tex.noise_scale = 0.6
    disp = ob.modifiers.new("L2R_Displace", "DISPLACE")
    disp.texture = tex
    add_driver(disp, "strength", ctx["ctrl"], "mids", f"0.1 + v * {0.4 + ctx['amount']('mids', 'displacement', 0.0):.3f} * s")
    ob.data.materials.append(ctx["mats"]["bass"])
    amt = ctx["amount"]("bass", "scale", 0.25)
    for i in range(3):
        add_driver(ob, "scale", ctx["ctrl"], "bass", f"1 + v * {amt:.3f} * s", i)
    ring = mk(bpy.ops.mesh.primitive_torus_add, major_radius=2.6, minor_radius=0.04, location=(0, 0, 1.4))
    ring.data.materials.append(ctx["mats"]["mids"])
    ctx["rotate"](ring, "mids")
    ctx["floor"](0.0)
    return {"camera": ((0, -8.0, 2.2), (math.radians(84), 0, 0)), "focus": [ob]}


def template_tunnel(ctx):
    rings = []
    for i in range(40):
        ob = mk(bpy.ops.mesh.primitive_torus_add, major_radius=2.2, minor_radius=0.06, location=(0, i * 1.2, 0),
                rotation=(math.radians(90), 0, 0))
        band = ("bass", "mids", "highs")[i % 3]
        ob.data.materials.append(ctx["mats"][band])
        rings.append(ob)
    tube = mk(bpy.ops.mesh.primitive_cylinder_add, radius=2.6, depth=60, location=(0, 24, 0),
              rotation=(math.radians(90), 0, 0))
    tube.data.materials.append(ctx["mats"]["base"])
    for k, ob in enumerate(rings):  # rings spin around the tunnel axis (their local z)
        add_driver(ob, "rotation_euler", ctx["ctrl"], "mids",
                   f"frame * {0.01 * (1 if k % 2 else -1):.3f} + v * {ctx['amount']('mids', 'rotation', 0.3):.3f}", 2)
    return {"camera": ((0, -2, 0), (math.radians(90), 0, 0)), "focus": rings, "fly": 0.04}


def template_particle_field(ctx):
    rnd = random.Random(7)
    parent = mk(bpy.ops.object.empty_add, location=(0, 0, 1))
    src = mk(bpy.ops.mesh.primitive_ico_sphere_add, subdivisions=2, radius=0.06, location=(0, 0, 0))
    src.data.materials.append(ctx["mats"]["highs"])
    for i in range(int(ctx["count"] or 260)):
        ob = src.copy()  # linked duplicate: shared mesh + material
        ob.location = (rnd.uniform(-6, 6), rnd.uniform(-2, 10), rnd.uniform(-2.5, 4))
        bpy.context.collection.objects.link(ob)
        ob.parent = parent
        for k in range(3):
            add_driver(ob, "scale", ctx["ctrl"], "highs", f"0.4 + v * {1.5 * ctx['amount']('highs', 'sparkles', 1.0):.3f}", k)
    ctx["rotate"](parent, "rms")
    core = mk(bpy.ops.mesh.primitive_ico_sphere_add, subdivisions=4, radius=0.8, location=(0, 4, 1))
    core.data.materials.append(ctx["mats"]["bass"])
    for k in range(3):
        add_driver(core, "scale", ctx["ctrl"], "bass", f"1 + v * {ctx['amount']('bass', 'scale', 0.25):.3f}", k)
    return {"camera": ((0, -6, 1.2), (math.radians(88), 0, 0)), "focus": [core]}


def template_floor_grid(ctx):
    plane = mk(bpy.ops.mesh.primitive_plane_add, size=60, location=(0, 20, 0))
    mat = bpy.data.materials.new("L2R_Grid")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (0.005, 0.005, 0.01, 1)
    brick = nt.nodes.new("ShaderNodeTexBrick")
    brick.inputs["Scale"].default_value = 30
    brick.inputs["Mortar Size"].default_value = 0.03
    brick.offset = 0.0          # straight grid instead of offset bricks
    brick.inputs["Brick Width"].default_value = 0.5
    brick.inputs["Row Height"].default_value = 0.5
    brick.inputs["Color1"].default_value = (0, 0, 0, 1)
    brick.inputs["Color2"].default_value = (0, 0, 0, 1)
    brick.inputs["Mortar"].default_value = (1, 1, 1, 1)
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    nt.links.new(brick.outputs["Color"], mul.inputs[0])
    nt.links.new(mul.outputs[0], bsdf.inputs["Emission Strength"])
    bsdf.inputs["Emission Color"].default_value = hex_rgba(ctx["colors"]["mids"])
    add_driver(nt, f'nodes["{mul.name}"].inputs[1].default_value', ctx["ctrl"], "bass",
               f"(0.3 + v) * {ctx['amount']('bass', 'emission_strength', 6.0):.3f} * s")
    for i, ch in enumerate("rgb"):
        add_driver(nt, f'nodes["{bsdf.name}"].inputs["Emission Color"].default_value', ctx["ctrl"], f"mids_{ch}", "v", index=i)
    plane.data.materials.append(mat)
    sun = mk(bpy.ops.mesh.primitive_uv_sphere_add, radius=4, location=(0, 45, 5))
    sun.data.materials.append(ctx["mats"]["bass"])
    return {"camera": ((0, -4, 1.1), (math.radians(86), 0, 0)), "focus": [sun], "fly": 0.03}


TEMPLATES = {"spectrum_bars": template_spectrum_bars, "pulsing_blob": template_pulsing_blob,
             "tunnel": template_tunnel, "particle_field": template_particle_field, "floor_grid": template_floor_grid}


# ------------------------------------------------------------------ build
def apply_curves(ctrl, curves: dict, sections_curve: list[float], palettes: list[dict], frames: int) -> None:
    for name in ("bass", "mids", "highs", "rms", "onset", "beat"):
        set_curve(ctrl, name, (curves.get(name) or [0.0])[:frames])
    set_curve(ctrl, "section", sections_curve[:frames] or [1.0])
    for band, keys in palettes.items():  # per-section colour, constant between section starts
        for i, ch in enumerate("rgb"):
            vals = [0.0] * frames
            for start, rgba in keys:
                for f in range(max(0, start), frames):
                    vals[f] = rgba[i]
            set_curve(ctrl, f"{band}_{ch}", vals or [1.0], constant=True)


def set_fps(scene, fps: float) -> None:
    ntsc = {23.976: (24, 1.001), 29.97: (30, 1.001), 59.94: (60, 1.001)}
    for k, (f, base) in ntsc.items():
        if abs(fps - k) < 0.01:
            scene.render.fps, scene.render.fps_base = f, base
            return
    scene.render.fps, scene.render.fps_base = int(round(fps)), 1.0


def setup_render(scene, data: dict, aspect: str) -> None:
    w, h = (1920, 1080) if aspect == "16:9" else (1080, 1920)
    scale = data.get("resolution_scale", 1.0)
    scene.render.resolution_x, scene.render.resolution_y = int(w * scale), int(h * scale)
    scene.render.resolution_percentage = 100
    engines = {e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
    want = data.get("engine", "EEVEE")
    if want == "CYCLES":
        scene.render.engine = "CYCLES"
        scene.cycles.samples = int(data.get("samples", 64))
        scene.cycles.use_denoising = bool(data.get("denoise", True))
    else:
        scene.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in engines else "BLENDER_EEVEE_NEXT"
        try:
            scene.eevee.taa_render_samples = int(data.get("samples", 32))
        except AttributeError:
            pass
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.use_file_extension = True
    try:
        scene.view_settings.view_transform = data.get("view_transform", "AgX")
    except TypeError:
        scene.view_settings.view_transform = "Filmic"
    add_bloom(scene, data.get("bloom", True))


def add_bloom(scene, enabled: bool) -> None:
    """Glow via the compositor Glare node (Eevee's old bloom checkbox is gone since 4.2)."""
    if not enabled:
        return
    try:
        if hasattr(scene, "compositing_node_group"):  # Blender 5.x
            tree = bpy.data.node_groups.new("L2R_Compositor", "CompositorNodeTree")
            scene.compositing_node_group = tree
            rl = tree.nodes.new("CompositorNodeRLayers")
            glare = tree.nodes.new("CompositorNodeGlare")
            out = tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
            go = tree.nodes.new("NodeGroupOutput")
            tree.links.new(rl.outputs["Image"], glare.inputs[0])
            tree.links.new(glare.outputs[0], go.inputs[0])
            del out
        else:  # 4.x
            scene.use_nodes = True
            tree = scene.node_tree
            rl = next(n for n in tree.nodes if n.type == "R_LAYERS")
            comp = next(n for n in tree.nodes if n.type == "COMPOSITE")
            glare = tree.nodes.new("CompositorNodeGlare")
            tree.links.new(rl.outputs["Image"], glare.inputs[0])
            tree.links.new(glare.outputs[0], comp.inputs[0])
        if "Type" in glare.inputs:  # Blender 5.x: options are input sockets
            glare.inputs["Type"].default_value = "Bloom"
            glare.inputs["Threshold"].default_value = 0.8
            glare.inputs["Strength"].default_value = 0.8
        else:  # 4.x
            for val in ("BLOOM", "FOG_GLOW"):
                try:
                    glare.glare_type = val
                    break
                except TypeError:
                    continue
            glare.threshold = 0.8
    except Exception as exc:  # noqa: BLE001 - bloom is a nice-to-have
        print(f"l2r: bloom not added ({exc})")


def build(data: dict, aspect: str, curves: dict, out_path: Path) -> Path:
    clear_scene()
    scene = bpy.context.scene
    frames = int(data["frames"])
    set_fps(scene, data["fps"])
    scene.frame_start, scene.frame_end = 1, frames
    setup_render(scene, data, aspect)
    world = bpy.data.worlds.new("L2R_World")
    scene.world = world
    world.use_nodes = True
    bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
    hdri = load_image(data.get("hdri"))
    if hdri:
        env = world.node_tree.nodes.new("ShaderNodeTexEnvironment")
        env.image = hdri
        world.node_tree.links.new(env.outputs["Color"], bg.inputs["Color"])
        bg.inputs["Strength"].default_value = 0.15
    else:
        bg.inputs["Color"].default_value = hex_rgba(data.get("background", "#05060a"))
        bg.inputs["Strength"].default_value = 1.0

    bpy.ops.object.empty_add(location=(0, 0, -50))
    ctrl = bpy.context.active_object
    ctrl.name = "L2R_Controller"
    m = data["mapping"]
    palettes: dict[str, list] = {}
    starts = sorted(data.get("sections", []), key=lambda s: s["start"])
    for band in ("bass", "mids", "highs"):
        base_col = data["colors"][band]
        keys = [(0, hex_rgba(base_col))]
        for s in starts:
            col = (m.get("palettes", {}).get(str(s["label"]).lower(), {}) or {}).get(band, base_col)
            keys.append((int(s["start"] * data["fps"]), hex_rgba(col)))
        palettes[band] = keys
    apply_curves(ctrl, curves, data.get("section_curve", []), palettes, frames)

    def amount(band, target, default):
        for t in m.get(band, []):
            if t["target"] == target:
                return float(t.get("amount", default))
        return default

    tex = data.get("texture") or {}
    mats = {b: emissive_material(f"L2R_{b}", ctrl, b, data["colors"][b], amount(b, "emission_strength", 4.0),
                                 tex=tex) for b in ("bass", "mids", "highs")}
    mats["base"] = emissive_material("L2R_base", ctrl, "rms", data["colors"]["mids"], 0.12, tex=tex, palette_driven=False)

    def floor(z):
        p = mk(bpy.ops.mesh.primitive_plane_add, size=40, location=(0, 0, z))
        p.data.materials.append(mats["base"])

    def rotate(ob, band):
        add_driver(ob, "rotation_euler", ctrl, band, f"frame * 0.003 + v * {amount(band, 'rotation', 0.3):.3f}", 2)

    ctx = {"ctrl": ctrl, "mats": mats, "amount": amount, "floor": floor, "rotate": rotate,
           "colors": data["colors"], "count": data.get("count")}
    layout = TEMPLATES[data["template"]](ctx)

    (cx, cy, cz), rot = layout["camera"]
    bpy.ops.object.camera_add(location=(cx, cy, cz), rotation=rot)
    cam = bpy.context.active_object
    scene.camera = cam
    cam.data.lens = 35 if aspect == "16:9" else 24          # 9:16: wider lens keeps the subject in frame
    cam.data.sensor_fit = "HORIZONTAL" if aspect == "16:9" else "VERTICAL"
    if aspect == "9:16":
        cam.location.y -= 2.0
    shake = amount("beat", "camera_shake", 0.04)
    for i, axis in enumerate(("x", "z")):
        add_driver(cam, "location", ctrl, "beat", f"{(cx, cz)[i]:.3f} + v * {shake:.4f} * s * sin(frame * {1.7 + i:.2f})",
                   (0, 2)[i])
    if layout.get("fly"):
        add_driver(cam, "location", ctrl, "rms", f"{cy:.3f} + frame * {layout['fly']:.4f}", 1)
    bpy.ops.object.light_add(type="POINT", location=(0, -3, 4))
    light = bpy.context.active_object
    add_driver(light.data, "energy", ctrl, "rms", f"100 + v * {amount('rms', 'light_intensity', 800.0):.1f} * s")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(out_path.parent / "frames" / aspect.replace(":", "x") / "frame_")
    bpy.ops.wm.save_as_mainfile(filepath=str(out_path))
    if data.get("pack_textures", True):   # portable .blend: textures travel inside the file
        try:
            bpy.ops.file.pack_all()
        except RuntimeError as exc:
            print(f"l2r: could not pack textures ({exc})")
    else:
        bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_mainfile()
    return out_path


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    args = argv[argv.index("--") + 1:] if "--" in argv else argv[1:]
    data_path = Path(args[0])
    data = json.loads(data_path.read_text(encoding="utf-8"))
    curves = json.loads((data_path.parent / data["curves_file"]).read_text(encoding="utf-8"))["curves"]
    for aspect in data["aspects"]:
        out = data_path.parent / f"{data['name']}_{aspect.replace(':', 'x')}.blend"
        build(data, aspect, curves, out)
        print(f"l2r: saved {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
