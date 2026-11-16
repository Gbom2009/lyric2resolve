"""Phase 11: SRT/CSV/EDL + Resolve script (job JSON, install path, script against a mocked Resolve API)."""

from __future__ import annotations

import csv
import importlib.util
import io
import json
from pathlib import Path

import pytest

from lyric2resolve.export import export, resolve_job, textformats
from lyric2resolve.export.timeline import build_plan
from tests.test_fcpxml import make_project

SCRIPT = resolve_job.TEMPLATE


def load_script():
    spec = importlib.util.spec_from_file_location("l2r_resolve_script", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------ SRT / CSV / EDL
def test_srt_lines_and_words():
    plan = build_plan(make_project(), "16:9")
    srt = textformats.to_srt(plan)
    blocks = srt.strip().split("\n\n")
    assert len(blocks) == len(plan.clips)
    assert blocks[0].splitlines()[1] == "00:00:01,000 --> 00:00:02,720"
    assert "We sing this song" in blocks[0]
    words = textformats.to_srt(plan, words=True).strip().split("\n\n")
    assert len(words) == sum(len(c.words) for c in plan.clips)
    assert words[1].splitlines()[2] == "sing"
    assert textformats.srt_time(3723.5) == "01:02:03,500"


def test_csv():
    plan = build_plan(make_project(), "9:16")
    rows = list(csv.reader(io.StringIO(textformats.to_csv(plan))))
    assert rows[0][:3] == ["index", "start_s", "end_s"] and len(rows) == len(plan.clips) + 1
    assert rows[1][3] == "01:00:01:00" and rows[1][-1] == "We sing this song"


def test_edl_markers():
    plan = build_plan(make_project(), "16:9")
    edl = textformats.to_edl(plan)
    lines = edl.splitlines()
    assert lines[0].startswith("TITLE: TEST SONG") and lines[1] == "FCM: NON-DROP FRAME"
    assert lines[3].startswith("001  AX       A     C        00:00:00:00 00:00:20:00 01:00:00:00 01:00:20:00")
    locs = [l for l in lines if l.startswith("* LOC:")]
    assert any("BLUE" in l and "Verse" in l for l in locs)
    assert any("YELLOW" in l and "We sing this song" in l for l in locs)
    tcs = [l.split()[2] for l in locs]
    assert tcs == sorted(tcs)


# ------------------------------------------------------------------ job + install
def test_export_resolve_writes_job_script_and_fcpxml(tmp_path):
    res = export(make_project(), tmp_path / "out", ["resolve"], data_root=tmp_path / "data")
    names = sorted(Path(f).name for f in res["files"])
    assert "Test_Song_resolve_job.json" in names and "lyric2resolve_build_timeline.py" in names
    assert "Test_Song_16x9.fcpxml" in names and "Test_Song_9x16.fcpxml" in names
    pointer = json.loads((tmp_path / "data" / "exports" / "last_resolve_job.json").read_text())
    job = json.loads(Path(pointer["job"]).read_text())
    assert job["fps"] == 25.0 and job["start_timecode"] == "01:00:00:00"
    assert [t["layout"] for t in job["timelines"]] == ["16:9", "9:16"]
    assert job["timelines"][1]["width"] == 1080 and job["timelines"][0]["fcpxml"].endswith("_16x9.fcpxml")
    clip = job["timelines"][0]["clips"][0]
    assert clip["start"] == 25 and clip["style"]["font_family"] and clip["words"][0][0] == "We"


def test_all_text_formats_written(tmp_path):
    res = export(make_project(), tmp_path, ["srt_csv_edl"], layouts=["16:9"])
    assert sorted(Path(f).name for f in res["files"]) == [
        "Test_Song_16x9.csv", "Test_Song_16x9_lines.srt", "Test_Song_16x9_markers.edl", "Test_Song_16x9_words.srt"]


def test_resolve_scripts_dir_and_install(tmp_path):
    win = resolve_job.resolve_scripts_dir({"APPDATA": r"C:\Users\x\AppData\Roaming"}, "win32")
    assert str(win).replace("\\", "/").endswith("Blackmagic Design/DaVinci Resolve/Support/Fusion/Scripts/Utility")
    dst = resolve_job.install_script(tmp_path / "Utility")
    assert dst.read_text() == SCRIPT.read_text()


def test_script_is_self_contained():
    src = SCRIPT.read_text()
    assert "import lyric2resolve" not in src and "from lyric2resolve" not in src
    compile(src, str(SCRIPT), "exec")


# ------------------------------------------------------------------ mocked Resolve API
class Rec:
    """Records calls; behaves like a Resolve API object."""

    def __init__(self, log, name):
        self._log, self._name = log, name

    def _call(self, method, *args):
        self._log.append((self._name, method, args))


class FakeTool(Rec):
    def __init__(self, log):
        super().__init__(log, "tool")
        self.inputs = {}
        self.keys = {}

    def SetInput(self, name, value, time=None):  # noqa: N802 - Resolve API naming
        if time is None:
            self.inputs[name] = value
        else:
            self.keys.setdefault(name, []).append((time, value))

    def AddModifier(self, name, kind):  # noqa: N802
        self._call("AddModifier", name, kind)

    def ConnectInput(self, name, tool):  # noqa: N802
        self._call("ConnectInput", name)


class FakeComp(Rec):
    def __init__(self, log):
        super().__init__(log, "comp")
        self.tools = []
        self.out = FakeTool(log)

    def GetToolList(self, selected, kind):  # noqa: N802
        return {}

    def AddTool(self, kind, x, y):  # noqa: N802
        t = FakeTool(self._log)
        t.kind = kind
        self.tools.append(t)
        return t

    def FindTool(self, name):  # noqa: N802
        return self.out

    def GetAttrs(self):  # noqa: N802
        return {"COMPN_RenderStart": 0}


class FakeItem(Rec):
    def __init__(self, log, info):
        super().__init__(log, "item")
        self.info = info
        self.comp = FakeComp(log)

    def SetName(self, n):  # noqa: N802
        self.name = n

    def GetFusionCompByIndex(self, i):  # noqa: N802
        return self.comp


class FakeClip:
    def __init__(self, name):
        self.name = name

    def GetName(self):  # noqa: N802
        return self.name


class FakeFolder:
    def __init__(self, name, clips=(), subs=()):
        self.name, self.clips, self.subs = name, list(clips), list(subs)

    def GetName(self):  # noqa: N802
        return self.name

    def GetClipList(self):  # noqa: N802
        return self.clips

    def GetSubFolderList(self):  # noqa: N802
        return self.subs


class FakeTimeline(Rec):
    def __init__(self, log, name):
        super().__init__(log, "timeline")
        self.name, self.settings, self.markers = name, {}, []

    def SetSetting(self, k, v):  # noqa: N802
        self.settings[k] = v
        return True

    def SetStartTimecode(self, tc):  # noqa: N802
        self.tc = tc
        return True

    def GetStartFrame(self):  # noqa: N802
        return 90000

    def AddMarker(self, frame, color, name, note, duration, custom):  # noqa: N802
        self.markers.append((frame, color, name))
        return True


class FakeMediaPool(Rec):
    def __init__(self, log, with_template=True):
        super().__init__(log, "mediapool")
        clips = [FakeClip("song.wav")] + ([FakeClip("l2r_textplus")] if with_template else [])
        self.root = FakeFolder("Master", subs=[FakeFolder("Titles", clips)])
        self.appended, self.timelines, self.imported_timelines = [], [], []

    def GetRootFolder(self):  # noqa: N802
        return self.root

    def AddSubFolder(self, parent, name):  # noqa: N802
        f = FakeFolder(name)
        parent.subs.append(f)
        return f

    def SetCurrentFolder(self, f):  # noqa: N802
        return True

    def ImportMedia(self, paths):  # noqa: N802
        self._call("ImportMedia", paths)
        return [FakeClip(Path(paths[0]).name)]

    def CreateEmptyTimeline(self, name):  # noqa: N802
        tl = FakeTimeline(self._log, name)
        self.timelines.append(tl)
        return tl

    def AppendToTimeline(self, infos):  # noqa: N802
        self.appended.append(infos[0])
        return [FakeItem(self._log, infos[0])]

    def ImportTimelineFromFile(self, path, opts):  # noqa: N802
        self.imported_timelines.append((path, opts))
        return object()


class FakeProject:
    def __init__(self, mp, fps="25", settable=True):
        self.mp, self.fps, self.settable = mp, fps, settable
        self.current = None

    def GetSetting(self, k):  # noqa: N802
        return self.fps

    def SetSetting(self, k, v):  # noqa: N802
        if self.settable:
            self.fps = v
        return self.settable

    def GetMediaPool(self):  # noqa: N802
        return self.mp

    def SetCurrentTimeline(self, tl):  # noqa: N802
        self.current = tl
        return True


class FakeResolve:
    def __init__(self, project):
        self.project = project

    def GetProjectManager(self):  # noqa: N802
        outer = self

        class PM:
            def GetCurrentProject(self):  # noqa: N802
                return outer.project

        return PM()


def job_for(level="styled", tmp=None):
    p = make_project()
    p.settings.styling_level = level
    p.styles = {"default": "Neon"}
    plans = [build_plan(p, "16:9"), build_plan(p, "9:16")]
    return resolve_job.job_dict(plans, {"16:9": "/x/a_16x9.fcpxml", "9:16": "/x/a_9x16.fcpxml"}), plans


def test_script_builds_textplus_timelines_with_exact_frames():
    mod = load_script()
    job, plans = job_for("styled")
    log = []
    mp = FakeMediaPool(log)
    project = FakeProject(mp)
    reps = mod.run(FakeResolve(project), job, log=lambda m: None)
    assert [r["timeline"] for r in reps] == [t["name"] for t in job["timelines"]]
    assert all(r["mode"] == "textplus" for r in reps)
    tl16, tl916 = mp.timelines
    assert tl916.settings["timelineResolutionWidth"] == "1080" and tl916.settings["timelineResolutionHeight"] == "1920"
    assert tl16.tc == "01:00:00:00"
    audio = mp.appended[0]
    assert audio["mediaType"] == 2 and audio["recordFrame"] == 90000 and audio["trackIndex"] == 1
    titles = [a for a in mp.appended if a.get("mediaType") == 1]
    assert len(titles) == 2 * len(plans[0].clips)
    first = titles[0]
    c0 = plans[0].clips[0]
    assert first["recordFrame"] == 90000 + c0.start_frame and first["endFrame"] == c0.duration - 1
    # no title placed inside the gap (frames 200-350 at 25 fps)
    for t in titles:
        s = t["recordFrame"] - 90000
        e = s + t["endFrame"] + 1
        assert e <= 200 or s >= 350
    assert reps[0]["markers"] == len(plans[0].markers) and tl16.markers[0][1] == "Blue"


def test_script_styles_text_and_glow():
    mod = load_script()
    job, plans = job_for("styled")
    mp = FakeMediaPool([])
    mod.run(FakeResolve(FakeProject(mp)), job, log=lambda m: None)
    # inspect the styling of one clip directly
    comp = FakeComp([])
    tool = mod.text_tool(comp)
    clip = job["timelines"][0]["clips"][0]
    mod.style_text(comp, tool, clip, {**job["timelines"][0], "fps": 25.0}, "styled", lambda m: None)
    assert tool.inputs["StyledText"] == "We sing this song" and tool.inputs["Font"] == "Arial"
    assert abs(tool.inputs["Center"][2] - (0.5 + clip["y"] / 1080)) < 1e-9
    assert any(getattr(t, "kind", "") == "SoftGlow" for t in comp.tools)       # Neon has glow
    assert not tool.keys                                                         # STYLED: no animation


def test_script_full_level_adds_keyframes_basic_does_not():
    mod = load_script()
    job, _ = job_for("full")
    clip = job["timelines"][0]["clips"][0]
    comp = FakeComp([])
    tool = mod.text_tool(comp)
    mod.style_text(comp, tool, clip, {**job["timelines"][0], "fps": 25.0}, "full", lambda m: None)
    assert "Size" in tool.keys  # Neon animates in with "pop"
    comp2 = FakeComp([])
    tool2 = mod.text_tool(comp2)
    mod.style_text(comp2, tool2, clip, {**job["timelines"][0], "fps": 25.0}, "basic", lambda m: None)
    assert not tool2.keys and "Enabled2" not in tool2.inputs


def test_script_falls_back_to_fcpxml_without_template():
    mod = load_script()
    job, _ = job_for()
    mp = FakeMediaPool([], with_template=False)
    reps = mod.run(FakeResolve(FakeProject(mp)), job, log=lambda m: None)
    assert [r["mode"] for r in reps] == ["fcpxml", "fcpxml"]
    assert mp.imported_timelines[0][0] == "/x/a_16x9.fcpxml" and not mp.timelines


def test_script_frame_rate_mismatch_message():
    mod = load_script()
    job, _ = job_for()
    project = FakeProject(FakeMediaPool([]), fps="29.97", settable=False)
    with pytest.raises(mod.BuildError, match="Create a new project"):
        mod.run(FakeResolve(project), job, log=lambda m: None)
    project = FakeProject(FakeMediaPool([]), fps="24", settable=True)
    mod.run(FakeResolve(project), job, log=lambda m: None)
    assert project.fps == "25"


def test_script_load_job_via_pointer(tmp_path, monkeypatch):
    mod = load_script()
    job_path = tmp_path / "job.json"
    job_path.write_text(json.dumps({"x": 1}))
    (tmp_path / "data" / "exports").mkdir(parents=True)
    (tmp_path / "data" / "exports" / "last_resolve_job.json").write_text(json.dumps({"job": str(job_path)}))
    monkeypatch.setenv("LYRIC2RESOLVE_DATA", str(tmp_path / "data"))
    monkeypatch.delenv("L2R_JOB", raising=False)
    assert mod.load_job() == {"x": 1}
    monkeypatch.setenv("LYRIC2RESOLVE_DATA", str(tmp_path / "nothing"))
    with pytest.raises(RuntimeError, match="No lyric2resolve export"):
        mod.load_job()
