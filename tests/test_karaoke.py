"""Phase 12: karaoke timing data, playlists, endpoints (path safety)."""

from __future__ import annotations

import pytest

from lyric2resolve import karaoke
from lyric2resolve import project as proj
from tests.test_fcpxml import make_project


def test_karaoke_data_lines_words_offset_and_gaps():
    p = make_project()
    p.settings.sync_offset_ms = 100
    d = karaoke.karaoke_data(p)
    assert d["name"] == "Test Song" and d["duration"] == 20.0
    first = d["lines"][0]
    assert first["text"] == "We sing this song" and first["start"] == 1.1
    assert [w["text"] for w in first["words"]] == ["We", "sing", "this", "song"]
    assert first["words"][1]["start"] == pytest.approx(1.55)
    assert d["gaps"] == [{"start": 8.0, "end": 14.0}]
    assert d["audio"] == {"song": False, "vocals": False, "instrumental": False}
    starts = [ln["start"] for ln in d["lines"]]
    assert starts == sorted(starts)


def test_karaoke_text_options_and_override():
    p = make_project()
    p.settings.case = "upper"
    d = karaoke.karaoke_data(p)
    assert d["lines"][0]["words"][0]["text"] == "WE"
    p.blocks[0].text_override = "Totally different"
    d = karaoke.karaoke_data(p)
    assert len(d["lines"][0]["words"]) == 1 and d["lines"][0]["words"][0]["text"] == "TOTALLY DIFFERENT"


def test_line_at():
    lines = [{"start": 1, "end": 2}, {"start": 5, "end": 6}]
    assert karaoke.line_at(lines, 0.5) == (-1, 0)
    assert karaoke.line_at(lines, 1.5) == (0, 1)
    assert karaoke.line_at(lines, 3.0) == (-1, 1)
    assert karaoke.line_at(lines, 9.0) == (-1, -1)


def test_playlists_persist_and_validate(tmp_path):
    pl = karaoke.load_playlists(tmp_path)
    assert pl.current == "Karaoke night" and pl.playlists == {"Karaoke night": []}
    pl.playlists["Friday"] = ["a/project.json", "b/project.json"]
    pl.current = "Friday"
    karaoke.save_playlists(pl, tmp_path)
    again = karaoke.load_playlists(tmp_path)
    assert again.current == "Friday" and again.playlists["Friday"] == ["a/project.json", "b/project.json"]
    with pytest.raises(ValueError):
        karaoke.save_playlists(karaoke.Playlists({"x": []}, "nope"), tmp_path)
    (tmp_path / karaoke.PLAYLIST_FILE).write_text("{broken")
    assert karaoke.load_playlists(tmp_path).current == "Karaoke night"


def test_karaoke_endpoints(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from lyric2resolve.editor.app import create_app

    path = proj.save(make_project(), tmp_path / "projects" / "song" / "project.json")
    c = TestClient(create_app(None, tmp_path / "projects", settings_dir=tmp_path / "settings"))
    d = c.get("/api/karaoke/data", params={"path": str(path)}).json()
    assert d["lines"][0]["text"] == "We sing this song"
    outside = proj.save(make_project(), tmp_path / "elsewhere" / "project.json")
    assert c.get("/api/karaoke/data", params={"path": str(outside)}).status_code == 403
    assert c.get("/api/karaoke/audio/instrumental", params={"path": str(path)}).status_code == 404
    pls = c.get("/api/karaoke/playlists").json()
    pls["playlists"]["Karaoke night"].append(str(path))
    assert c.put("/api/karaoke/playlists", json=pls).status_code == 200
    assert c.get("/api/karaoke/playlists").json()["playlists"]["Karaoke night"] == [str(path)]
    assert c.put("/api/karaoke/playlists", json={"playlists": {}, "current": "x"}).status_code == 400
    assert c.get("/karaoke").status_code == 200
