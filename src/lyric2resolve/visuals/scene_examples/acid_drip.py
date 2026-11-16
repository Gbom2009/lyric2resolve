"""Example custom scene: 3D "ACID" text with glowing green liquid dripping down it, pulsing on the bass.

A custom scene is a Python file that defines build_scene(ctx). lyric2resolve calls it inside Blender after it has
set up the world, the audio controller (bass/mids/highs/rms/onset/beat/section curves) and the render settings;
afterwards it adds the camera rig (beat shake), the light, optional 3D lyrics, bloom, and saves + renders.
See lyric2resolve.visuals.custom.GUIDE for the full ctx reference.
"""

import math
import random


def build_scene(ctx):
    bpy = ctx["bpy"]
    hex_rgba, add_driver, ctrl = ctx["hex_rgba"], ctx["add_driver"], ctx["ctrl"]
    t0, t1 = ctx["time_range"] or (0.0, 4.0)
    f0, f1 = ctx["frame_of"](t0), ctx["frame_of"](t1)
    word = ctx["data"].get("params", {}).get("text", "ACID")
    green = ctx["data"].get("params", {}).get("color", "#39ff14")

    # --- glowing liquid material: flowing bands (Wave texture) moving down over time, emission driven by the bass
    liquid = bpy.data.materials.new("acid_liquid")
    liquid.use_nodes = True
    nt = liquid.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = hex_rgba("#0b3d0b")
    bsdf.inputs["Roughness"].default_value = 0.15
    for name in ("Emission Color", "Emission"):
        if name in bsdf.inputs:
            bsdf.inputs[name].default_value = hex_rgba(green)
            break
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.bands_direction = "Z"
    wave.inputs["Scale"].default_value = 3.0
    wave.inputs["Distortion"].default_value = 6.0
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    nt.links.new(coord.outputs["Object"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], wave.inputs["Vector"])
    # the liquid flows down: animate the texture location over the clip
    mapping.inputs["Location"].default_value[2] = 0.0
    mapping.inputs["Location"].keyframe_insert("default_value", index=2, frame=f0)
    mapping.inputs["Location"].default_value[2] = 2.5
    mapping.inputs["Location"].keyframe_insert("default_value", index=2, frame=f1)
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    nt.links.new(wave.outputs["Fac"], mul.inputs[0])
    nt.links.new(mul.outputs[0], bsdf.inputs["Emission Strength"])
    add_driver(mul.inputs[1], "default_value", ctrl, "bass", "3.0 + v * 12.0")

    # --- the word: extruded, bevelled 3D text, standing up, facing the camera
    bpy.ops.object.text_add(location=(0, 0, 0.6), rotation=(math.radians(90), 0, 0))
    txt = bpy.context.active_object
    txt.data.body = word
    txt.data.align_x, txt.data.align_y = "CENTER", "CENTER"
    txt.data.size = 2.2
    txt.data.extrude = 0.25
    txt.data.bevel_depth = 0.04
    txt.data.materials.append(liquid)
    add_driver(txt, "scale", ctrl, "bass", "1.0 + v * 0.08", 2)  # bass "breathes" the letters
    # hits in on the first beat of the clip
    for f, sc in ((f0, 0.2), (f0 + 4, 1.1), (f0 + 8, 1.0)):
        txt.scale = (sc, sc, sc)
        txt.keyframe_insert("scale", frame=f)

    # --- drips: small glowing drops that run down from the letters and stretch while falling
    rnd = random.Random(7)
    width = 1.4 * len(word)
    for i in range(18):
        x = rnd.uniform(-width / 2, width / 2)
        start = f0 + rnd.randint(4, max(5, (f1 - f0) // 2))
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.07, location=(x, -0.15, 0.0), segments=12, ring_count=8)
        drop = bpy.context.active_object
        drop.data.materials.append(liquid)
        for f, z, sz in ((start, -0.2, 1.0), (start + 18, -2.6, 2.4), (start + 24, -3.4, 0.2)):
            drop.location.z = z
            drop.scale = (1.0, 1.0, sz)
            drop.keyframe_insert("location", index=2, frame=f)
            drop.keyframe_insert("scale", frame=f)

    # --- dark wet floor that reflects the glow
    ctx["floor"](-3.5)
    return {"camera": ((0.0, -11.0, 0.4), (math.radians(90), 0.0, 0.0))}
