"""Phase 16: style brief, Claude Code prompts, project templates (save/load/apply, editor op + endpoints)."""

from __future__ import annotations

import pytest

from lyric2resolve import project as proj
from lyric2resolve import styling, templates
from lyric2resolve.visuals import brief, prompts


def song_project():
    text = "dance tonight under neon city lights we feel alive dance dance fire in the night"
    words = proj.make_words([{"text": w, "start": i * 0.5, "end": i * 0.5 + 0.4, "line": i // 5}
                             for i, w in enumerate(text.split())])
    energy = [0.3] * 300 + [0.95] * 300   # 10 Hz: quiet first 30 s, loud next 30 s
    p = proj.Project(name="Neon Nights", words=words, blocks=proj.blocks_by_line(words),
                     sections=[proj.Section("s1", "verse", 0, 30), proj.Section("s2", "drop", 30, 60)],
                     analysis={"bpm": 128.0, "key": "A minor", "energy": energy, "energy_rate": 10.0},
                     audio={"duration_s": 60.0})
    return p


def test_lyric_themes():
    themes, kw = brief.lyric_themes("Dance with me tonight, my love, under the stars. Love love!")
    assert themes[0] == "romantic" and "euphoric" in themes and "dreamy" in themes
    assert "love" in kw
    assert brief.lyric_themes("")[0] == []


def test_brief_sections_energy_and_concepts():
    b = brief.build_brief(song_project())
    assert b.bpm == 128.0 and b.tempo_feel == "fast / club energy" and b.mood in ("euphoric", "urban")
    verse, drop = b.sections
    assert verse.level == "low" and drop.level == "high"
    assert len(drop.concepts) == 3 and drop.concepts[0]["template"] in ("tunnel", "floor_grid", "spectrum_bars")
    assert any("beat" in t for t in drop.text_animation)
    assert len(b.palette) == 3 and all(c.startswith("#") for c in b.palette)


def test_brief_without_analysis():
    p = proj.Project(name="Plain", words=proj.make_words([{"text": "hello", "start": 0, "end": 1}]))
    b = brief.build_brief(p)
    assert b.bpm is None and b.sections[0].label == "song" and b.sections[0].concepts


def test_prompts_contain_everything_needed():
    b = brief.build_brief(song_project())
    tex = [{"name": "Lava 004", "category": "lava", "kind": "texture", "license": "CC0 1.0",
            "path": "ambientcg/Lava004_1k", "maps": {"color": "x", "emission": "y"}}]
    bp = prompts.blender_prompt(b, 25, ["16:9", "9:16"], tex)
    for needle in ("BPM 128", "A minor", "| drop | 30.00 | 60.00 |", "1920x1080 and 1080x1920", "25 fps",
                   "Lava 004", "CC0", "blender -b", "RENDER_INSTRUCTIONS.md", "AAC 320", "Rekordbox", "bass (20-150 Hz)"):
        assert needle in bp, needle
    tp = prompts.threejs_prompt(b, 25, ["9:16"], [])
    assert "frame index" in tp and "1080x1920" in tp and "UnrealBloomPass" in tp
    md = prompts.brief_markdown(b)
    assert "## Drop" in md and "--template" in md


def test_template_save_load_apply(tmp_path):
    src = song_project()
    src.settings.case = "upper"
    src.settings.styling_level = "full"
    src.settings.fps = 30
    src.sections[1].preset = "word"
    styling.op_save_style(src, "Club", {"fill": "#00ffcc"})
    styling.op_set_section_style(src, "drop", "Club")
    path = templates.save(src, "Neon club", tmp_path, mapping={"bass": [{"target": "scale", "amount": 0.5}]},
                          render_preset="high", visual_template="tunnel")
    assert path.name == "Neon club.json" and templates.list_templates(tmp_path) == ["Neon club"]
    t = templates.load("Neon club", tmp_path)
    new = proj.Project(name="Other", sections=[proj.Section("x1", "drop", 0, 10), proj.Section("x2", "verse", 10, 20)])
    templates.apply(new, t)
    assert new.settings.case == "upper" and new.settings.styling_level == "full" and new.settings.fps == 30
    assert new.sections[0].preset == "word" and new.sections[1].preset is None
    assert styling.StyleBook.from_project(new.styles).by_section["drop"] == "Club"
    assert new.extra["render_preset"] == "high" and new.extra["visual_template"] == "tunnel"
    assert new.extra["visual_mapping"]["bass"][0]["amount"] == 0.5
    with pytest.raises(templates.TemplateError):
        templates.load("missing", tmp_path)
    with pytest.raises(templates.TemplateError):
        templates.save(src, "///", tmp_path)


def test_editor_ideas_and_template_endpoints(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from lyric2resolve.editor.app import EditorSession, create_app

    s = EditorSession(proj.save(song_project(), tmp_path / "p" / "project.json"))
    c = TestClient(create_app(s, tmp_path))
    d = c.get("/api/ideas").json()
    assert d["brief"]["bpm"] == 128.0 and "Claude" not in d["markdown"] and "blender -b" in d["blender_prompt"]
    assert c.post("/api/templates/save", json={"name": "Mine"}).json()["templates"] == ["Mine"]
    s.project.settings.case = "lower"
    st = c.post("/api/op/apply_template", json={"name": "Mine"}).json()
    assert st["project"]["settings"]["case"] == "keep" and st["history"]["undo_label"] == "apply_template"
    assert c.post("/api/op/apply_template", json={"name": "Nope"}).status_code == 400
    assert c.get("/ideas").status_code == 200
