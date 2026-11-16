"""Phase 15: presets, Blender commands, runner (fake Blender), estimate, resume, cancel, ffmpeg mux, instructions."""

from __future__ import annotations

import shutil
import sys
import threading
from pathlib import Path

import numpy as np
import pytest

from lyric2resolve import project as proj
from lyric2resolve.render import blender as bl
from lyric2resolve.render import instructions, mux, presets, render_project
from lyric2resolve.render.runner import BlenderRunner, frame_ranges, missing_frames

FAKE = Path(__file__).parent / "data" / "fake_blender.py"
SR = 22050


def runner():
    return BlenderRunner(Path("blender"), prefix=[sys.executable, str(FAKE)])


# ------------------------------------------------------------------ presets
def test_presets():
    pv = presets.get("preview")
    assert pv.size("16:9") == (960, 540) and pv.size("9:16") == (540, 960) and pv.fps == 15 and pv.max_seconds == 25
    assert presets.get("standard").size("16:9") == (1920, 1080) and presets.get("ultra").engine == "CYCLES"
    c = presets.get("custom", height=1440, engine="cycles", samples=200)
    assert c.size("16:9") == (2560, 1440) and c.engine == "CYCLES" and c.samples == 200
    with pytest.raises(ValueError):
        presets.get("insane")
    with pytest.raises(ValueError):
        presets.get("custom", engine="unreal")
    with pytest.raises(ValueError):
        presets.get("custom", turbo=True)


# ------------------------------------------------------------------ blender helpers
def test_commands_order_and_versions():
    cmd = bl.render_command(Path("blender"), Path("x.blend"), Path("setup.py"), Path("job.json"), 5, 10)
    assert cmd.index("x.blend") < cmd.index("-P") < cmd.index("-s") < cmd.index("-a") < cmd.index("--")
    assert cmd[-1] == "job.json"   # only the job file after "--" (Blender ignores what comes after it)
    assert bl.parse_version("Blender 4.2.3 LTS") == (4, 2, 3) and bl.parse_version("nope") is None


def test_gpu_choice():
    assert bl.choose_device({"backends": {"CUDA": ["RTX 3060"], "OPTIX": ["RTX 3060"]}})[0] == "OPTIX"
    assert bl.choose_device({"backends": {"CUDA": ["GTX 1080"]}})[0] == "CUDA"
    dev, msg = bl.choose_device({"backends": {}})
    assert dev == "CPU" and "WARNING" in msg
    assert bl.parse_gpu_probe('noise\nL2R_GPU{"backends": {"CUDA": ["X"]}}\n') == {"backends": {"CUDA": ["X"]}}


def test_frame_ranges_and_missing(tmp_path):
    assert frame_ranges([1, 2, 3, 7, 8, 10]) == [(1, 3), (7, 8), (10, 10)]
    for f in (1, 2, 5):
        (tmp_path / f"frame_{f:04d}.png").write_bytes(b"x")
    (tmp_path / "frame_0003.png").write_bytes(b"")  # empty placeholder = not done
    assert missing_frames(tmp_path, 1, 6) == [3, 4, 6]


# ------------------------------------------------------------------ runner with fake Blender
def job(tmp_path):
    return {"width": 64, "height": 36, "fps": 25, "engine": "EEVEE", "samples": 8, "denoise": False,
            "device": "EEVEE", "output": str(tmp_path / "frames" / "16x9" / "frame_")}


def test_render_progress_resume_and_errors(tmp_path, monkeypatch):
    r = runner()
    seen = []
    res = r.render(Path("scene.blend"), job(tmp_path), 1, 10, seen.append)
    assert res.ok and res.rendered == 10 and seen[-1].done == 10 and seen[-1].fraction == 1.0
    assert seen[3].frame is not None and seen[3].eta_s is not None
    # resume: delete 3 frames -> only those are rendered again
    for f in (2, 3, 9):
        (tmp_path / "frames" / "16x9" / f"frame_{f:04d}.png").unlink()
    res = r.render(Path("scene.blend"), job(tmp_path), 1, 10)
    assert res.ok and res.rendered == 3 and res.skipped == 7
    # Blender crash -> error with the log tail
    monkeypatch.setenv("FAKE_FAIL_AT", "15")
    res = r.render(Path("scene.blend"), job(tmp_path), 11, 20)
    assert not res.ok and "fake crash at frame 15" in res.error


def test_cancel(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SLEEP", "0.05")
    cancel = threading.Event()
    progress = []

    def on(p):
        progress.append(p)
        if p.done >= 3:
            cancel.set()

    res = runner().render(Path("scene.blend"), job(tmp_path), 1, 200, on, cancel)
    assert res.cancelled and not res.ok and res.rendered < 200


def test_estimate(tmp_path):
    clock = iter(range(0, 1000, 2))  # every clock() call advances 2 s
    r = BlenderRunner(Path("blender"), prefix=[sys.executable, str(FAKE)], clock=lambda: next(clock))
    est = r.estimate(Path("scene.blend"), job(tmp_path), 1, 3000)
    assert est.frames == 3000 and est.seconds_per_frame > 0 and est.bytes_per_frame > 0
    assert est.total_bytes == est.bytes_per_frame * 3000 and "frames" in est.summary()
    assert not list((tmp_path / "frames" / "16x9").glob("*.png"))  # test frames go to a scratch folder


def test_gpu_detect_and_build(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_GPU", '{"backends": {"OPTIX": ["RTX 4070"]}}')
    assert runner().detect_gpu(tmp_path)[0] == "OPTIX"
    data = tmp_path / "scene_data.json"
    data.write_text('{"name": "S", "aspects": ["16:9", "9:16"]}')
    blends = runner().build(tmp_path / "l2r_scene.py", data)
    assert [b.name for b in blends] == ["S_16x9.blend", "S_9x16.blend"]


# ------------------------------------------------------------------ mux
def test_mux_command_dj_settings():
    s = mux.MuxSettings(fps=29.97)
    cmd = mux.mux_command("ffmpeg", "frames/frame_%04d.png", 1, Path("song.wav"), Path("o.mp4"), s, (1920, 1080))
    j = " ".join(cmd)
    assert "-framerate 30000/1001" in j and "-r 30000/1001" in j and "-fps_mode cfr" in j
    assert "-g 25" in j and "-c:a aac -b:a 320k" in j and "+faststart" in j and "format=yuv420p" in j
    assert "scale=" not in j and "-ss" not in j
    vert = mux.mux_command("ffmpeg", "f_%04d.png", 101, Path("s.wav"), Path("o.mp4"),
                           mux.MuxSettings(fps=25, fit_box=(1920, 1080), start_seconds=4.0), (1080, 1920))
    v = " ".join(vert)
    assert "scale=1920:1080:force_original_aspect_ratio=decrease" in v and "-ss 4.000" in v and "-start_number 101" in v
    assert mux.gop(60) == 25 and mux.gop(15) == 15


def test_check_dj_file():
    good = {"streams": [{"codec_type": "video", "codec_name": "h264", "pix_fmt": "yuv420p", "width": 1920,
                         "height": 1080, "r_frame_rate": "25/1", "avg_frame_rate": "25/1"},
                        {"codec_type": "audio", "codec_name": "aac", "bit_rate": "320000"}]}
    assert mux.check_dj_file(good, 25) == []
    bad = {"streams": [{"codec_type": "video", "codec_name": "hevc", "pix_fmt": "yuv444p", "width": 3840,
                        "height": 2160, "r_frame_rate": "25/1", "avg_frame_rate": "24/1"}]}
    probs = " ".join(mux.check_dj_file(bad, 25))
    assert "H.264" in probs and "AAC" in probs and "yuv420p" in probs and "1920" in probs and "constant" in probs


needs_ffmpeg = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg missing")


@needs_ffmpeg
def test_real_mux_produces_dj_ready_mp4(tmp_path):
    from lyric2resolve.audio import wavio
    from lyric2resolve.visuals.procedural import write_png

    frames = tmp_path / "frames"
    for f in range(1, 51):
        write_png(frames / f"frame_{f:04d}.png", np.full((72, 128, 3), f / 50.0))
    t = np.arange(SR * 2) / SR
    song = wavio.write(tmp_path / "song.wav", np.stack([np.sin(2 * np.pi * 440 * t)] * 2, axis=1) * 0.3, SR)
    out = tmp_path / "v.mp4"
    mux.run(mux.mux_command("ffmpeg", str(frames / "frame_%04d.png"), 1, song, out, mux.MuxSettings(fps=25, preset="ultrafast")))
    info = mux.probe("ffprobe", out)
    assert mux.check_dj_file(info, 25) == []
    assert abs(float(info["format"]["duration"]) - 2.0) < 0.1


# ------------------------------------------------------------------ instructions + full pipeline
def test_instructions_content():
    md = instructions.blender_markdown("Song", "tunnel", 25, 6000, 240, presets.get("standard"), ["16:9", "9:16"],
                                      {"16:9": "S_16x9.blend", "9:16": "S_9x16.blend"},
                                      {"16:9": "frames/16x9", "9:16": "frames/9x16"}, 0.5)
    for needle in ("Blender 4.2", "OptiX", "Eevee", "Cycles", "-a", "resume", "V1", "Bake Sound to F-Curves",
                   "Troubleshooting", "1920x1080", "50 minutes", "Rekordbox"):
        assert needle in md, needle
    assert "fixed time step" in instructions.threejs_markdown("Song", 25, ["16:9"])


def make_project(tmp_path):
    from lyric2resolve.audio import wavio

    t = np.arange(SR * 3) / SR
    y = (0.5 * np.sin(2 * np.pi * 60 * t) * (np.mod(t, 0.5) < 0.1)).astype(np.float32)
    wav = wavio.write(tmp_path / "song.wav", np.stack([y, y], axis=1), SR)
    p = proj.Project(name="Render Test", audio={"song_wav": str(wav), "duration_s": 3.0},
                     sections=[proj.Section("s1", "verse", 0, 1.5), proj.Section("s2", "chorus", 1.5, 3)])
    p.settings.fps = 25
    return proj.save(p, tmp_path / "p" / "project.json")


def test_render_project_pipeline_with_fake_blender(tmp_path):
    path = make_project(tmp_path)
    logs = []
    rep = render_project(path, "tunnel", "preview", ["16:9"], runner=runner(), log=logs.append,
                         ffmpeg=shutil.which("ffmpeg") or "", textures_root=tmp_path / "tex")
    assert rep.ok and len(rep.blends) == 1 and "16:9" in rep.estimates
    folder = Path(rep.folder)
    assert (folder / "RENDER_INSTRUCTIONS.md").exists() and (folder / "curves.json").exists()
    assert len(list((folder / "frames" / "16x9").glob("*.png"))) == 45   # 3 s at the preview's 15 fps
    if shutil.which("ffmpeg"):
        assert rep.videos and Path(rep.videos[0]).exists()


def test_render_sections_only(tmp_path):
    path = make_project(tmp_path)
    rep = render_project(path, "spectrum_bars", "draft", ["16:9"], sections=["chorus"], runner=runner(),
                         log=lambda m: None, do_mux=False, textures_root=tmp_path / "tex")
    frames = sorted((Path(rep.folder) / "frames" / "16x9").glob("*.png"))
    assert frames[0].name == "frame_0038.png" and frames[-1].name == "frame_0075.png"
    with pytest.raises(RuntimeError, match="no sections"):
        render_project(path, "spectrum_bars", "draft", ["16:9"], sections=["bridge"], runner=runner(),
                       log=lambda m: None, do_mux=False, textures_root=tmp_path / "tex")


def test_render_estimate_only_and_missing_blender(tmp_path, monkeypatch):
    path = make_project(tmp_path)
    rep = render_project(path, "floor_grid", "standard", ["9:16"], estimate_only=True, runner=runner(),
                         log=lambda m: None, textures_root=tmp_path / "tex")
    assert "9:16" in rep.estimates and not list((Path(rep.folder) / "frames").rglob("*.png"))
    monkeypatch.setattr(bl, "find_blender", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="Blender was not found"):
        render_project(path, "floor_grid", "standard", ["9:16"], log=lambda m: None, textures_root=tmp_path / "tex")


def test_verify_blender_3_frame_render_with_fake_blender():
    from lyric2resolve import verify

    ctx = verify.Context(repo=Path(__file__).resolve().parents[1], blender_runner=runner())
    (res,) = verify.run_checks(ctx, only={"blender_3_frame_render"})
    assert res.status == verify.OK, res.detail
    (res,) = verify.run_checks(verify.Context(repo=ctx.repo, quick=True), only={"blender_3_frame_render"})
    assert res.status == verify.SKIP


def test_visuals_api_options_videos_and_files(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from lyric2resolve.editor import visuals_api
    from lyric2resolve.editor.app import EditorSession, create_app

    path = make_project(tmp_path)
    opened = []
    monkeypatch.setattr(visuals_api, "open_in_explorer", lambda target, opener=None: opened.append([str(target)]))
    app = create_app(EditorSession(path))
    c = TestClient(app)
    o = c.get("/api/visuals/options").json()
    assert {t["id"] for t in o["templates"]} >= {"tunnel", "spectrum_bars"} and all(t["description"] for t in o["templates"])
    assert "preview" in [p["name"] for p in o["presets"]] and "blender" in o["tools"]
    assert c.get("/api/visuals/videos").json()["videos"] == []
    vid = path.parent / "visuals" / "tunnel" / "preview" / "x_16x9.mp4"
    vid.parent.mkdir(parents=True)
    vid.write_bytes(b"mp4")
    (path.parent / "visuals" / "_estimate").mkdir()
    (path.parent / "visuals" / "_estimate" / "e.mp4").write_bytes(b"x")
    vids = c.get("/api/visuals/videos").json()["videos"]
    assert [v["name"] for v in vids] == ["x_16x9.mp4"] and vids[0]["folder"] == "visuals/tunnel/preview"
    assert c.get("/api/visuals/file/visuals/tunnel/preview/x_16x9.mp4").content == b"mp4"
    assert c.get("/api/visuals/file/project.json").status_code == 404  # only files inside visuals/
    assert c.get("/api/visuals/file/visuals/../project.json").status_code == 404
    assert c.post("/api/visuals/open-folder", json={"folder": "visuals/tunnel/preview"}).status_code == 200
    assert opened and opened[-1][-1].endswith("preview")
    assert c.post("/api/visuals/open-folder", json={"folder": ".."}).status_code == 403
    assert c.get("/visuals").status_code == 200


def test_old_blender_is_named_in_the_build_error(tmp_path):
    path = make_project(tmp_path)

    class OldBlender:
        def version(self):
            return (3, 3, 1)

        def build(self, script, data, log=None):
            raise RuntimeError("Building the Blender scene failed:\nKeyError: 'Emission Color'")

    logs = []
    with pytest.raises(RuntimeError, match=r"Your Blender is 3\.3\.1; the scenes need Blender 4\.2"):
        render_project(path, "particle_field", "preview", ["16:9"], runner=OldBlender(), log=logs.append,
                       do_mux=False, textures_root=tmp_path / "tex")
    assert any("Blender 3.3.1 - older than 3.6" in m for m in logs)
