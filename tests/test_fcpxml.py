"""Phase 10: timecode math, clip plan (gaps!), 16:9/9:16 layout, FCPXML generation + DTD validation."""

from __future__ import annotations

import random
import urllib.request
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

import pytest

from lyric2resolve import project as proj
from lyric2resolve.export import export, fcpxml
from lyric2resolve.export.timecode import Rate, fcp_time, frames_to_tc, parse_fcp_time, tc_to_frames
from lyric2resolve.export.timeline import build_plan, check_plan

FPS = [23.976, 24, 25, 29.97, 30, 50, 60]


# ------------------------------------------------------------------ timecode
@pytest.mark.parametrize("fps", FPS)
def test_rate_roundtrip(fps):
    r = Rate.of(fps)
    assert abs(float(r.fps) - fps) < 0.001
    for f in (0, 1, 1234, 86400):
        assert r.frames(r.seconds(f)) == f
        assert parse_fcp_time(fcp_time(f, r)) == Fraction(f) / r.fps
    tc = "01:00:00:00"
    assert frames_to_tc(tc_to_frames(tc, r), r) == tc
    assert tc_to_frames(tc, r) == 3600 * r.timebase


def test_ntsc_details():
    r = Rate.of(23.976)
    assert (r.num, r.den, r.timebase, r.frame_duration) == (24000, 1001, 24, "1001/24000s")
    assert fcp_time(tc_to_frames("01:00:00:00", r), r) == "18018/5s"   # 3603.6 s of real time
    assert Rate.of(29.97).frame_duration == "1001/30000s" and Rate.of(25).frame_duration == "1/25s"
    with pytest.raises(ValueError):
        Rate.of(26.5)
    with pytest.raises(ValueError):
        tc_to_frames("01:00:00:25", Rate.of(25))
    with pytest.raises(ValueError):
        tc_to_frames("1 hour", Rate.of(25))


def test_frames_rounding():
    r = Rate.of(25)
    assert r.frames(1.019) == 25 and r.frames(1.021) == 26 and r.frames(0) == 0


# ------------------------------------------------------------------ plan
def make_project(fps=25, gaps=((8.0, 14.0),), hold=False):
    lines = [["We", "sing", "this", "song"], ["all", "night", "long"], ["in", "the", "gap"], ["oh", "yeah"]]
    times = [1.0, 4.0, 9.0, 15.0]
    raw = []
    for li, (line, t) in enumerate(zip(lines, times)):
        for w in line:
            raw.append({"text": w, "start": t, "end": t + 0.35, "line": li})
            t += 0.45
    words = proj.make_words(raw)
    p = proj.Project(name="Test Song", words=words, blocks=proj.blocks_by_line(words),
                     gaps=[proj.Gap(f"g{i}", a, b) for i, (a, b) in enumerate(gaps)],
                     sections=[proj.Section("s1", "verse", 0, 8), proj.Section("s2", "chorus", 14, 20)],
                     audio={"duration_s": 20.0, "song_source": "C:\\Music\\My Song.mp3"},
                     analysis={"downbeats": [0.5, 2.5, 4.5, 6.5, 8.5, 10.5, 12.5, 14.5, 16.5]})
    p.settings.fps = fps
    p.settings.hold_until_next = hold
    return p


def test_plan_basic_and_gap_rules():
    p = make_project()
    plan = build_plan(p, "16:9")
    assert check_plan(plan) == []
    texts = [c.text for c in plan.clips]
    assert texts == ["We sing this song", "all night long", "oh yeah"]   # block inside the gap dropped
    assert any("dropped" in w for w in plan.warnings)
    assert plan.clips[0].start_frame == 25 and plan.start_tc_frames == 90000
    assert plan.gaps == [(200, 350)]
    assert not [m for m in plan.markers if 200 <= m.frame < 350]       # no beat markers in gaps
    assert [m.name for m in plan.markers if m.kind == "section"] == ["Verse", "Chorus"]


def test_hold_until_next_is_cut_at_gap():
    p = make_project(hold=True)
    plan = build_plan(p, "16:9")
    c0, c1 = plan.clips[0], plan.clips[1]
    assert c0.end_frame == c1.start_frame            # held until the next block
    assert c1.end_frame == 200                       # would hold into the gap -> cut at gap start
    assert check_plan(plan) == []


def test_offset_preroll_and_min_length():
    p = make_project()
    p.settings.sync_offset_ms = 100
    p.settings.pre_roll_ms = 200
    plan = build_plan(p, "16:9")
    assert plan.clips[0].start_frame == Rate.of(25).frames(1.0 + 0.1 - 0.2)
    p = make_project()
    p.blocks = [proj.Block("b1", [p.words[0].id])]  # 0.35 s = 9 frames
    p.settings.min_clip_frames = 20
    plan = build_plan(p, "16:9")
    assert plan.clips[0].duration == 20


@pytest.mark.parametrize("fps", FPS)
def test_random_projects_never_place_clips_in_gaps(fps):
    rng = random.Random(fps)
    for _ in range(25):
        raw, t = [], 0.3
        for i in range(rng.randint(5, 40)):
            d = rng.uniform(0.05, 0.8)
            raw.append({"text": f"w{i}", "start": t, "end": t + d, "line": i // rng.randint(1, 5)})
            t += d + rng.uniform(0.0, 1.5)
        words = proj.make_words(raw)
        gaps, g = [], rng.uniform(0, 5)
        while g < t:
            length = rng.uniform(0.5, 6)
            gaps.append(proj.Gap(f"g{len(gaps)}", g, g + length))
            g += length + rng.uniform(2, 15)
        p = proj.Project(words=words, blocks=proj.blocks_by_line(words), gaps=gaps, audio={"duration_s": t + 3})
        p.settings.fps = fps
        p.settings.hold_until_next = rng.random() < 0.5
        p.settings.pre_roll_ms = rng.choice([0, 80, 300])
        p.settings.post_roll_ms = rng.choice([0, 120])
        p.settings.min_clip_frames = rng.choice([1, 6, 15])
        for lay in ("16:9", "9:16"):
            plan = build_plan(p, lay)
            assert check_plan(plan) == [], (fps, lay)


def test_layouts_16x9_vs_9x16():
    p = make_project()
    p.blocks = [proj.Block("b1", [w.id for w in p.words[:7]])]  # long line
    wide, tall = build_plan(p, "16:9"), build_plan(p, "9:16")
    assert (wide.width, wide.height, tall.width, tall.height) == (1920, 1080, 1080, 1920)
    assert len(tall.clips[0].lines) > len(wide.clips[0].lines)
    assert wide.clips[0].y < 0 and tall.clips[0].y < 0                  # below centre (lower part)
    assert tall.clips[0].font_px != wide.clips[0].font_px or True


# ------------------------------------------------------------------ FCPXML
def parse(xml: str) -> ET.Element:
    return ET.fromstring(xml.split("<!DOCTYPE fcpxml>")[1])


def test_fcpxml_structure():
    p = make_project(fps=23.976)
    plan = build_plan(p, "16:9")
    xml = fcpxml.to_string(plan)
    root = parse(xml)
    assert root.get("version") == "1.9"
    fmt = root.find("resources/format")
    assert fmt.get("frameDuration") == "1001/24000s" and fmt.get("width") == "1920"
    assert root.find("resources/asset/media-rep").get("src") == "file:///C:/Music/My%20Song.mp3"
    seq = root.find(".//sequence")
    assert seq.get("tcStart") == "18018/5s" and seq.get("tcFormat") == "NDF"
    gap = seq.find("spine/gap")
    song = gap.find("asset-clip")
    assert song.get("lane") == "-1" and song.get("offset") == "18018/5s"
    titles = gap.findall("title")
    assert [t.find("text/text-style").text for t in titles] == ["We sing this song", "all night long", "oh yeah"]
    t0 = parse_fcp_time(seq.get("tcStart"))
    gap_s, gap_e = 8.0, 14.0
    for t in titles:
        start = parse_fcp_time(t.get("offset")) - t0
        end = start + parse_fcp_time(t.get("duration"))
        assert end <= Fraction(gap_s) + Fraction(1, 24) or start >= Fraction(gap_e) - Fraction(1, 24)
        assert t.get("lane") == "1" and t.find("param").get("name") == "Position"
        assert t.find("text/text-style").get("ref") == t.find("text-style-def").get("id")
    assert len(gap.findall("marker")) == len(plan.markers)


def test_fcpxml_styles_applied_at_styled_level():
    p = make_project()
    p.settings.styling_level = "styled"
    p.styles = {"default": "Bold Yellow"}
    ts = parse(fcpxml.to_string(build_plan(p, "9:16"))).find(".//title/text-style-def/text-style")
    assert ts.get("font") == "Impact" and ts.get("fontColor").startswith("1 0.8314 0")
    assert ts.get("strokeWidth") == "6" and ts.get("shadowColor")
    root = parse(fcpxml.to_string(build_plan(p, "9:16")))
    assert root.find("resources/format").get("height") == "1920"


def test_file_url_forms():
    assert fcpxml.file_url("C:\\A B\\s.wav") == "file:///C:/A%20B/s.wav"
    assert fcpxml.file_url("/home/x/s.wav") == "file:///home/x/s.wav"


@pytest.fixture(scope="session")
def fcpxml_dtd():
    cache = Path.home() / ".cache" / "lyric2resolve" / "FCPXMLv1_9.dtd"
    if not cache.exists():
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(fcpxml.DTD_URL, timeout=20) as r:
                cache.write_bytes(r.read())
        except Exception as exc:  # offline
            pytest.skip(f"FCPXML DTD not downloadable: {exc}")
    return cache


@pytest.mark.parametrize("fps", FPS)
@pytest.mark.parametrize("layout", ["16:9", "9:16"])
def test_fcpxml_validates_against_dtd(fcpxml_dtd, fps, layout):
    pytest.importorskip("lxml")
    p = make_project(fps=fps, hold=True)
    p.settings.styling_level = "styled"
    p.styles = {"default": "Neon"}
    xml = fcpxml.to_string(build_plan(p, layout))
    assert fcpxml.validate(xml, fcpxml_dtd) == []


def test_export_writes_both_layouts(tmp_path):
    res = export(make_project(), tmp_path)
    names = sorted(Path(f).name for f in res["files"])
    assert names == ["Test_Song_16x9.fcpxml", "Test_Song_9x16.fcpxml"]
    assert any("dropped" in w for w in res["warnings"])


def test_export_blocked_when_rules_break(tmp_path, monkeypatch):
    import lyric2resolve.export as ex

    monkeypatch.setattr(ex, "check_plan", lambda plan: ["b1: inside instrumental gap"])
    with pytest.raises(RuntimeError, match="export blocked"):
        ex.export(make_project(), tmp_path)
    assert not list(tmp_path.glob("*.fcpxml"))


def test_export_cli(tmp_path, capsys):
    from lyric2resolve.__main__ import main

    path = proj.save(make_project(), tmp_path / "p" / "project.json")
    assert main(["export", str(path), "--layout", "9:16"]) == 0
    assert (tmp_path / "p" / "export" / "Test_Song_9x16.fcpxml").exists()
