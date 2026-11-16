"""Phase 14: band curves, mapping, scene generation; real Blender (bpy module) tests when available."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from lyric2resolve import project as proj
from lyric2resolve.visuals import bands, blender_gen, mapping

SR = 22050


def song(seconds=8.0):
    """Bass kicks in the first half, hi-hats in the second half."""
    t = np.arange(int(seconds * SR)) / SR
    half = t < seconds / 2
    kick = np.sin(2 * np.pi * 55 * t) * (np.mod(t, 0.5) < 0.12) * half
    hats = np.random.default_rng(1).standard_normal(len(t)) * (np.mod(t, 0.25) < 0.03) * ~half
    from scipy.signal import butter, lfilter

    b, a = butter(4, 4000 / (SR / 2), btype="high")
    y = 0.8 * kick + 0.4 * lfilter(b, a, hats)
    return np.stack([y, y], axis=1).astype(np.float32)


@pytest.fixture(scope="module")
def curves():
    return bands.compute(song(), SR, bands.CurveConfig(fps=25), beats_s=[0.5, 1.0, 1.5])


def test_curve_shapes_and_bands(curves):
    assert curves.frames == 200 and set(curves.data) >= {"bass", "mids", "highs", "rms", "onset", "beat"}
    bass, highs = np.array(curves.data["bass"]), np.array(curves.data["highs"])
    assert bass[:100].mean() > 3 * bass[100:].mean()      # kicks only in the first half
    assert highs[100:].mean() > 3 * highs[:100].mean()    # hats only in the second half
    for v in curves.data.values():
        assert min(v) >= 0 and max(v) <= 1.0
    beat = np.array(curves.data["beat"])
    assert beat[int(0.5 * 25)] == pytest.approx(1.0) and beat[int(0.5 * 25) + 3] < 1.0


def test_envelope_attack_release():
    x = np.zeros(100)
    x[10:20] = 1.0
    fast = bands.envelope(x, 25, 0, 2000)
    assert fast[10] == pytest.approx(1.0) and fast[30] > 0.8      # instant attack, slow release
    slow = bands.envelope(x, 25, 1000, 0)
    assert slow[10] < 0.1 and slow[20] == 0.0                     # slow attack, instant release


def test_frames_follow_fps():
    y = song(4.0)
    assert bands.compute(y, SR, bands.CurveConfig(fps=30)).frames == 120
    assert bands.compute(y, SR, bands.CurveConfig(fps=23.976)).frames == int(4.0 * 23.976)


def test_curves_save_load_csv(tmp_path, curves):
    js, cs = curves.save(tmp_path)
    again = bands.Curves.load(js)
    assert again.frames == curves.frames and again.data["bass"][:5] == pytest.approx(curves.data["bass"][:5], abs=1e-4)
    lines = cs.read_text().splitlines()
    assert lines[0].startswith("frame,time_s,bass") and len(lines) == curves.frames + 1


def test_config_roundtrip_and_custom_bands():
    cfg = bands.CurveConfig.from_dict({"fps": 50, "bands": [{"name": "sub", "low_hz": 20, "high_hz": 60, "gain": 2}]})
    assert cfg.fps == 50 and cfg.bands[0].name == "sub"
    c = bands.compute(song(2), SR, cfg)
    assert "sub" in c.data and "bass" not in c.data


def test_section_intensity():
    s = bands.section_intensity([{"label": "verse", "start": 0, "end": 4}, {"label": "chorus", "start": 4, "end": 8}],
                                200, 25, fade_s=0.2)
    assert s[10] == pytest.approx(0.7) and s[190] == pytest.approx(1.0)


def test_mapping_defaults_and_validation(tmp_path):
    m = mapping.validate({})
    assert mapping.band_color(m, "bass") == "#ff7a1a" and mapping.band_color(m, "mids") == "#2f7bff"
    assert mapping.band_color(m, "highs") == "#33ff88"
    assert mapping.amount(m, "highs", "sparkles") == 1.0 and mapping.amount(m, "bass", "scale") == 0.25
    with pytest.raises(mapping.MappingError, match="unknown target"):
        mapping.validate({"bass": [{"target": "explode"}]})
    with pytest.raises(mapping.MappingError, match="colour"):
        mapping.validate({"bass": [{"target": "emission_color", "color": "orange"}]})
    with pytest.raises(mapping.MappingError, match="unknown key"):
        mapping.validate({"treble": []})
    f = tmp_path / "m.yaml"
    f.write_text("bass:\n  - {target: emission_color, color: '#ff0000'}\npalettes:\n  chorus: {mids: '#ffffff'}\n")
    m2 = mapping.load(f)
    assert mapping.band_color(m2, "bass") == "#ff0000" and m2["palettes"]["chorus"]["mids"] == "#ffffff"
    assert mapping.validate(mapping.load(None)) == mapping.validate({})


def demo_project():
    p = proj.Project(name="Demo Song", sections=[proj.Section("s1", "verse", 0, 4), proj.Section("s2", "chorus", 4, 8)],
                     analysis={"beats": [0.5, 1.0]})
    p.settings.fps = 25
    return p


def test_generate_scene_folder(tmp_path):
    with pytest.raises(ValueError):
        blender_gen.generate(demo_project(), tmp_path, "rainbow", audio=(song(), SR))
    data_path = blender_gen.generate(demo_project(), tmp_path, "tunnel", ["9:16"], audio=(song(), SR),
                                     textures_root=tmp_path / "none")
    data = json.loads(data_path.read_text())
    assert data["template"] == "tunnel" and data["frames"] == 200 and data["aspects"] == ["9:16"]
    assert data["colors"] == {"bass": "#ff7a1a", "mids": "#2f7bff", "highs": "#33ff88"}
    assert len(data["section_curve"]) == 200 and data["texture"] == {}
    for f in ("curves.json", "curves.csv", "mapping.yaml", "l2r_scene.py"):
        assert (tmp_path / f).exists()


def test_scene_script_is_self_contained():
    src = blender_gen.SCRIPT.read_text()
    assert "lyric2resolve" not in src.split('"""', 2)[2].split("import bpy")[0]
    compile(src, str(blender_gen.SCRIPT), "exec")


# ------------------------------------------------------------------ real Blender via the bpy module
def bpy_available() -> bool:
    try:
        import bpy  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


needs_bpy = pytest.mark.skipif(not bpy_available(), reason="bpy module not installed (CI 'blender' job installs it)")

CHECK = r'''
import sys, json, bpy
bpy.ops.wm.open_mainfile(filepath=sys.argv[1])
sc = bpy.context.scene
driven = [o for o in bpy.data.objects if o.animation_data and o.animation_data.drivers]
mats = [m for m in bpy.data.materials if m.node_tree and m.node_tree.animation_data and m.node_tree.animation_data.drivers]
meshes = [o for o in driven if o.type == "MESH"] or driven
bars = meshes
out = {"fps": sc.render.fps, "fps_base": sc.render.fps_base, "res": [sc.render.resolution_x, sc.render.resolution_y],
       "end": sc.frame_end, "drivers": len(driven) + len(mats), "scales": []}
for f in (5, 150):
    sc.frame_set(f)
    dg = bpy.context.evaluated_depsgraph_get()
    out["scales"].append(bars[0].evaluated_get(dg).scale[2])
print("RESULT" + json.dumps(out))
'''


@needs_bpy
@pytest.mark.parametrize("template", sorted(mapping.TEMPLATES))
def test_bpy_builds_blend_with_working_drivers(tmp_path, template):
    p = demo_project()
    p.settings.fps = 23.976
    data_path = blender_gen.generate(p, tmp_path, template, ["16:9", "9:16"], audio=(song(), SR),
                                     textures_root=tmp_path / "none", count=30)
    env = dict(os.environ, PYTHONPATH="")
    run = subprocess.run([sys.executable, str(tmp_path / "l2r_scene.py"), str(data_path)], capture_output=True,
                         text=True, timeout=600, env=env)
    assert run.returncode == 0, run.stdout[-2000:] + run.stderr[-2000:]
    blends = sorted(tmp_path.glob("*.blend"))
    assert [b.name for b in blends] == [f"Demo_Song_{template}_16x9.blend", f"Demo_Song_{template}_9x16.blend"]
    (tmp_path / "check.py").write_text(CHECK)
    res = subprocess.run([sys.executable, str(tmp_path / "check.py"), str(blends[1])], capture_output=True,
                         text=True, timeout=300)
    info = json.loads(next(line for line in res.stdout.splitlines() if line.startswith("RESULT"))[6:])
    assert info["fps"] == 24 and abs(info["fps_base"] - 1.001) < 1e-6 and info["res"] == [1080, 1920]
    assert info["end"] == int(8 * 23.976) and info["drivers"] > 0
    if template in ("spectrum_bars",):
        assert info["scales"][0] != info["scales"][1]  # bass-driven bar height changes with the music


def test_procedural_textures_tile_and_png(tmp_path):
    import zlib

    from lyric2resolve.visuals import procedural

    for name in procedural.PATTERNS:
        img = procedural.GENERATORS[name](size=128)
        assert img.shape == (128, 128) and 0 <= img.min() and img.max() <= 1.0
        if name in ("noise", "cracks"):  # seamless: the wrap-around step looks like any neighbouring step
            typical = np.abs(np.diff(img, axis=1)).mean()
            assert np.abs(img[:, 0] - img[:, -1]).mean() < 3 * typical + 0.01
            assert np.abs(img[0] - img[-1]).mean() < 3 * np.abs(np.diff(img, axis=0)).mean() + 0.01
    path = procedural.generate("cracks", tmp_path / "procedural", size=64)
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and b"IHDR" in data
    idat = data[data.index(b"IDAT") + 4:data.index(b"IEND") - 8]
    assert len(zlib.decompress(idat)) == 64 * (64 + 1)
    from lyric2resolve.assets import textures

    listed = textures.list_textures(tmp_path)
    assert listed[0]["source"] == "procedural" and listed[0]["maps"]["emission"] == "procedural/cracks_64.png"
    with pytest.raises(ValueError):
        procedural.generate("plaid", tmp_path)
