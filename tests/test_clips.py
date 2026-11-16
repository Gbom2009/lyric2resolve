"""Feature update B: clips track (own files + rendered/Claude-made scenes), custom scenes, lyric-video look."""

from __future__ import annotations

import json
import shutil
import threading
import time
from pathlib import Path

import numpy as np
import pytest

from lyric2resolve import project as proj
from lyric2resolve.editor import ops
from lyric2resolve.export.timeline import build_plan, check_plan

REPO = Path(__file__).resolve().parents[1]


def make_project(tmp_path=None):
    raw, t = [], 1.0
    for li, line in enumerate([["we", "sing", "this"], ["all", "night", "long"], ["oh", "yeah"], ["acid"]]):
        for w in line:
            raw.append({"text": w, "start": t, "end": t + 0.3, "line": li})
            t += 0.4
        t += 1.0
    words = proj.make_words(raw)
    p = proj.Project(name="Clip Song", words=words, blocks=proj.blocks_by_line(words),
                     analysis={"downbeats": [0.0, 2.0, 4.0, 6.0, 8.0, 10.0], "beats": [x * 0.5 for x in range(24)],
                               "bpm": 120.0}, audio={"duration_s": 12.0})
    return p


# ------------------------------------------------------------------ model + ops
def test_clip_ops_snap_overlap_undo_roundtrip(tmp_path):
    p = make_project()
    c = ops.add_clip(p, "/v/acid.mp4", 6.3, 7.8, snap=True, hide_lyrics=True)
    assert (c.start, c.end) == (6.0, 8.0) and c.name == "acid" and c.id.startswith("c")
    with pytest.raises(ops.OpError, match="overlap"):
        ops.add_clip(p, "/v/b.mp4", 7.0, 9.0)
    ops.add_clip(p, "/v/b.mp4", 8.0, 9.0)
    with pytest.raises(ops.OpError, match="overlap"):
        ops.update_clip(p, c.id, end=8.5)
    assert c.end == 8.0  # refused change left it alone
    ops.update_clip(p, c.id, hide_lyrics=False, name="ACID")
    assert not c.hide_lyrics and c.name == "ACID"
    with pytest.raises(ops.OpError, match="end after"):
        ops.add_clip(p, "/v/x.mp4", 2.2, 2.6, snap=True)  # both snap to the bar at 2.0
    path = proj.save(p, tmp_path / "project.json")
    back = proj.load(path)
    assert [x.name for x in back.clips] == ["ACID", "b"] and back.validate() == []
    ops.remove_clip(back, back.clips[1].id)
    assert len(back.clips) == 1


def test_hide_lyrics_clip_replaces_titles_in_every_export(tmp_path):
    p = make_project()
    acid_word = next(w for w in p.words if w.text == "acid")
    ops.add_clip(p, str(tmp_path / "acid_16x9.mp4"), acid_word.start - 0.1, acid_word.end + 0.5, hide_lyrics=True,
                 info={"paths": {"9:16": str(tmp_path / "acid_9x16.mp4")}})
    plan = build_plan(p, "16:9")
    assert check_plan(plan) == []
    assert "acid" not in [c.text for c in plan.clips]       # the clip replaces the word
    assert len(plan.media) == 1 and plan.media[0].hide_lyrics
    assert plan.media[0].path.endswith("acid_16x9.mp4")
    assert build_plan(p, "9:16").media[0].path.endswith("acid_9x16.mp4")  # its own video per layout
    p.clips[0].hide_lyrics = False
    assert "acid" in [c.text for c in build_plan(p, "16:9").clips]  # shown over the clip instead


def test_fcpxml_has_clips_lane_under_titles(tmp_path):
    from lxml import etree

    from lyric2resolve.export import fcpxml

    p = make_project()
    vid = tmp_path / "acid.mp4"
    vid.write_bytes(b"x")
    ops.add_clip(p, str(vid), 6.0, 8.0)
    xml = etree.fromstring(fcpxml.to_string(build_plan(p, "16:9")).split("\n", 2)[2].encode())
    media = [a for a in xml.iter("asset") if a.get("hasVideo") == "1"]
    assert len(media) == 1 and media[0].find("media-rep").get("src").endswith("acid.mp4")
    clips = [c for c in xml.iter("asset-clip") if c.get("lane") == "1"]
    assert len(clips) == 1 and clips[0].get("ref") == media[0].get("id")
    assert {t.get("lane") for t in xml.iter("title")} == {"2"}  # lyrics above the clip
    no_clips = etree.fromstring(fcpxml.to_string(build_plan(make_project(), "16:9")).split("\n", 2)[2].encode())
    assert {t.get("lane") for t in no_clips.iter("title")} == {"1"}  # unchanged without clips


def test_fcpxml_with_clips_is_valid_against_the_dtd(tmp_path):
    from lyric2resolve.export import fcpxml

    dtd = tmp_path / "fcpxml.dtd"
    try:
        import urllib.request

        with urllib.request.urlopen(fcpxml.DTD_URL, timeout=15) as r:
            dtd.write_bytes(r.read())
    except Exception:
        pytest.skip("DTD not downloadable (offline)")
    p = make_project()
    ops.add_clip(p, str(tmp_path / "a.mp4"), 6.0, 8.0, hide_lyrics=True)
    assert fcpxml.validate(fcpxml.to_string(build_plan(p, "16:9")), dtd) == []


def test_resolve_script_puts_clips_on_v1_and_titles_on_v2(tmp_path):
    from lyric2resolve.export import resolve_job
    from tests import test_exports_resolve as T

    class TL(T.FakeTimeline):
        tracks = 1

        def AddTrack(self, kind):  # noqa: N802
            TL.tracks += 1
            return True

    p = make_project()
    ops.add_clip(p, str(tmp_path / "acid.mp4"), 6.0, 8.0)
    plans = [build_plan(p, "16:9")]
    job = resolve_job.job_dict(plans, {"16:9": "/x/a.fcpxml"})
    mod = T.load_script()
    mp = T.FakeMediaPool([])
    mp.CreateEmptyTimeline = lambda name: (mp.timelines.append(TL([], name)) or mp.timelines[-1])
    reps = mod.run(T.FakeResolve(T.FakeProject(mp)), job, log=lambda m: None)
    assert reps[0]["media"] == 1 and TL.tracks == 2
    vids = [a for a in mp.appended if a.get("mediaType") == 1]
    assert vids[0]["trackIndex"] == 1 and vids[0]["recordFrame"] == 90000 + plans[0].media[0].start_frame
    assert all(a["trackIndex"] == 2 for a in vids[1:]) and len(vids) == 1 + len(plans[0].clips)


# ------------------------------------------------------------------ custom scenes
def test_custom_scene_guide_and_paths(tmp_path):
    from lyric2resolve.visuals import custom

    g = custom.guide()
    assert "def build_scene(ctx)" in g and "ACID" in g and "add_driver" in g
    assert custom.safe_name("Acid drop!") == "Acid_drop" and custom.scene_path(tmp_path, "acid").name == "scene.py"
    sp = custom.scene_path(tmp_path, "acid")
    sp.parent.mkdir(parents=True)
    sp.write_text("def build_scene(ctx): return {}")
    assert custom.resolve_script(tmp_path, "scenes/acid/scene.py") == sp.resolve()
    with pytest.raises(FileNotFoundError):
        custom.resolve_script(tmp_path, "../outside.py")


def test_generate_custom_scene_data(tmp_path):
    from lyric2resolve.visuals import blender_gen, custom

    p = make_project()
    sr = 22050
    y = np.zeros((sr * 12, 2), dtype=np.float32)
    dp = blender_gen.generate(p, tmp_path, "custom", ["16:9"], audio=(y, sr), textures_root=tmp_path / "none",
                              custom_script=custom.EXAMPLES_DIR / "acid_drip.py", time_range=(6.0, 8.0),
                              name="acid", params={"text": "ACID"})
    d = json.loads(dp.read_text())
    assert d["template"] == "custom" and d["custom_script"] == "custom_scene.py" and d["name"] == "Clip_Song_acid"
    assert d["time_range"] == [6.0, 8.0] and d["params"] == {"text": "ACID"} and d["downbeats"][:2] == [0.0, 2.0]
    assert [b["text"] for b in d["lyrics"]][:1] == ["we sing this"] and (tmp_path / "custom_scene.py").exists()
    with pytest.raises(FileNotFoundError):
        blender_gen.generate(p, tmp_path, "custom", audio=(y, sr), custom_script=tmp_path / "nope.py")


def test_render_jobs_on_done_puts_rendered_clip_on_the_track(tmp_path):
    from lyric2resolve.claude_link import mcp_server
    from lyric2resolve.render.jobs import RenderJobs

    path = proj.save(make_project(), tmp_path / "song" / "project.json")
    sp = path.parent / "scenes" / "acid" / "scene.py"
    sp.parent.mkdir(parents=True)
    sp.write_text("def build_scene(ctx):\n    return {}\n")
    calls = []

    def fake_render(project_path, **kw):
        calls.append(kw)
        out = Path(project_path).parent / "visuals" / kw["name"] / "preview"
        out.mkdir(parents=True, exist_ok=True)
        vids = [out / f"x_{a.replace(':', 'x')}.mp4" for a in kw["aspects"]]
        for v in vids:
            v.write_bytes(b"v")
        return {"ok": True, "videos": [str(v) for v in vids]}

    be = mcp_server.FileBackend(path, jobs=RenderJobs(fake_render))
    srv = mcp_server.McpServer(be)
    res = srv.call_tool("render_clip", {"name": "acid", "start": 6.2, "end": 7.9, "script": "scenes/acid/scene.py",
                                        "snap": True, "hide_lyrics": True, "params": {"text": "ACID"}})
    assert not res["isError"], res
    be.jobs.wait(5)
    time.sleep(0.1)
    kw = calls[0]
    assert kw["time_range"] == (6.0, 8.0) and kw["video_only"] and kw["custom_script"] == sp.resolve()
    clips = json.loads(srv.call_tool("list_clips", {})["content"][0]["text"])
    assert clips["clips"][0]["name"] == "acid" and clips["clips"][0]["hide_lyrics"] and clips["bars"][:2] == [0.0, 2.0]
    p = proj.load(path)
    assert p.clips[0].info["paths"]["9:16"].endswith("x_9x16.mp4")
    guide = json.loads(srv.call_tool("custom_scene_guide", {})["content"][0]["text"])["guide"]
    assert "build_scene" in guide
    bad = srv.call_tool("render_clip", {"name": "x", "start": 1, "end": 2, "script": "../evil.py"})
    assert bad["isError"]


# ------------------------------------------------------------------ clips API (uploads)
needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient

    from lyric2resolve.editor.app import EditorSession, create_app

    path = proj.save(make_project(), tmp_path / "projects" / "song" / "project.json")
    return TestClient(create_app(EditorSession(path), tmp_path / "projects"))


@needs_ffmpeg
def test_upload_video_and_image_clips(client, tmp_path):
    import subprocess

    vid = tmp_path / "loop.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=red:s=64x36:d=1.5",
                    "-r", "25", str(vid)], check=True)
    r = client.post("/api/clips/upload", files={"file": ("loop.mp4", vid.read_bytes(), "video/mp4")},
                    data={"start": "2.0", "end": "0", "hide_lyrics": "true"})
    assert r.status_code == 200, r.text
    c = r.json()["project"]["clips"][0]
    assert c["start"] == 2.0 and abs(c["end"] - 3.5) < 0.05 and c["hide_lyrics"]  # length = the file's length
    from PIL import Image

    img = tmp_path / "logo.png"
    Image.new("RGB", (40, 20), (0, 255, 0)).save(img)
    r = client.post("/api/clips/upload", files={"file": ("logo.png", img.read_bytes(), "image/png")},
                    data={"start": "8.0", "end": "10.0"})
    assert r.status_code == 200, r.text
    c2 = r.json()["project"]["clips"][1]
    assert c2["path"].endswith(".mp4") and c2["end"] == 10.0
    assert client.get(f"/api/clips/file/{c2['id']}").status_code == 200
    assert client.post("/api/clips/upload", files={"file": ("a.txt", b"x", "text/plain")},
                       data={"start": "1"}).status_code == 400
    assert client.post("/api/clips/upload", files={"file": ("l.mp4", vid.read_bytes(), "video/mp4")},
                       data={"start": "2.5"}).status_code == 400  # overlaps the first clip


def test_render_clip_endpoint_validates(client):
    assert client.post("/api/clips/render", json={"name": "acid", "start": 3, "end": 2}).status_code == 400
    assert client.post("/api/clips/render", json={"name": "acid", "start": 1, "end": 2}).status_code == 404  # no script
    assert "build_scene" in client.get("/api/clips/guide").json()["guide"]


# ------------------------------------------------------------------ lyric-video look
def test_lyric_video_look(tmp_path):
    from lyric2resolve import styling
    from lyric2resolve.editor.newproject import apply_lyric_look

    for name in ("Lyric Video", "Lyric Video Neon", "Lyric Video Punch"):
        s = styling.BUILTIN[name]
        s.validate()
        assert s.position_y_16x9 == pytest.approx(0.5, abs=0.03) and s.size_px >= 110 and s.animation_in != "none"
    path = proj.save(make_project(), tmp_path / "project.json")
    apply_lyric_look(path)
    p = proj.load(path)
    assert styling.StyleBook.from_project(p.styles).default == "Lyric Video" and p.settings.styling_level == "full"
    plan = build_plan(p, "16:9")
    assert plan.clips[0].font_px == 124 and abs(plan.clips[0].y) < 60  # big and centred, not a bottom caption
