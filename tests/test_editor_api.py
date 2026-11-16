"""Phase 6: editor ops, presets, undo/redo and the FastAPI endpoints."""

from __future__ import annotations

import pytest

from lyric2resolve import project as proj
from lyric2resolve.editor import ops, presets
from lyric2resolve.editor.app import EditorSession

LINES = [["We", "sing", "this", "song"], ["all", "night", "long"], ["oh", "yeah"]]


def make_project() -> proj.Project:
    raw, t = [], 1.0
    for li, line in enumerate(LINES):
        for w in line:
            raw.append({"text": w, "start": t, "end": t + 0.3, "confidence": 0.9, "line": li})
            t += 0.4
        t += 1.0
    words = proj.make_words(raw)
    return proj.Project(name="t", words=words, blocks=proj.blocks_by_line(words))


def texts(p):
    return [p.block_text(b) for b in p.blocks]


def wid(p, text):
    return next(w.id for w in p.words if w.text == text)


# ------------------------------------------------------------------ merge / split
def test_merge_words_across_blocks_keeps_timing():
    p = make_project()
    b = ops.merge_words(p, [wid(p, "song"), wid(p, "all"), wid(p, "night")])
    assert texts(p) == ["We sing this", "song all night", "long", "oh yeah"]
    s, e = p.block_span(b)
    assert s == p.words[3].start and e == p.words[5].end
    assert p.validate() == []


def test_merge_requires_consecutive_selection():
    p = make_project()
    with pytest.raises(ops.OpError, match="consecutive"):
        ops.merge_words(p, [wid(p, "We"), wid(p, "song")[:-1] + "9"])
    with pytest.raises(ops.OpError, match="consecutive"):
        ops.merge_words(p, [p.words[0].id, p.words[2].id])
    assert ops.merge_words(p, [p.words[2].id, p.words[0].id, p.words[1].id])  # order doesn't matter


def test_merge_blocks():
    p = make_project()
    ops.merge_blocks(p, [p.blocks[0].id, p.blocks[1].id])
    assert texts(p) == ["We sing this song all night long", "oh yeah"]


def test_split_block_and_word_timings_unchanged():
    p = make_project()
    before = [(w.start, w.end) for w in p.words]
    a, b = ops.split_block(p, p.blocks[0].id, wid(p, "this"))
    assert texts(p) == ["We sing", "this song", "all night long", "oh yeah"]
    assert [(w.start, w.end) for w in p.words] == before
    with pytest.raises(ops.OpError, match="first word"):
        ops.split_block(p, a.id, wid(p, "We"))
    with pytest.raises(ops.OpError, match="not in block"):
        ops.split_block(p, a.id, wid(p, "oh"))


def test_split_block_words():
    p = make_project()
    ops.split_block_words(p, p.blocks[1].id)
    assert texts(p) == ["We sing this song", "all", "night", "long", "oh yeah"]


def test_move_word_between_neighbours():
    p = make_project()
    ops.move_word(p, wid(p, "song"), "next")
    assert texts(p) == ["We sing this", "song all night long", "oh yeah"]
    ops.move_word(p, wid(p, "song"), "prev")
    assert texts(p) == ["We sing this song", "all night long", "oh yeah"]
    with pytest.raises(ops.OpError, match="last word"):
        ops.move_word(p, wid(p, "sing"), "next")
    ops.remove_block(p, p.blocks[1].id)
    with pytest.raises(ops.OpError, match="adjacent"):
        ops.move_word(p, wid(p, "song"), "next")


def test_moving_last_word_removes_empty_block():
    p = make_project()
    ops.move_word(p, wid(p, "oh"), "prev")
    ops.move_word(p, wid(p, "yeah"), "prev")
    assert texts(p)[-1] == "all night long oh yeah" and len(p.blocks) == 2


def test_text_edits():
    p = make_project()
    ops.set_word_text(p, wid(p, "sing"), "sang")
    assert texts(p)[0] == "We sang this song"
    ops.set_block_text(p, p.blocks[0].id, "WE SANG THIS SONG!")
    assert texts(p)[0] == "WE SANG THIS SONG!"
    ops.set_block_text(p, p.blocks[0].id, None)
    assert texts(p)[0] == "We sang this song"
    with pytest.raises(ops.OpError):
        ops.set_word_text(p, wid(p, "sang"), "  ")


def test_timing_nudges():
    p = make_project()
    w = p.words[0]
    ops.nudge_words(p, [w.id], 0.1)
    assert (w.start, w.end) == (1.1, 1.4)
    ops.nudge_words(p, [w.id], -5)
    assert w.start == 0.0 and w.end == pytest.approx(0.3)
    ops.nudge_words(p, [w.id], 0.05, edge="end")
    assert w.end == pytest.approx(0.35)
    with pytest.raises(ops.OpError):
        ops.nudge_words(p, [w.id], -1, edge="end")
    ops.set_word_timing(p, w.id, 1.0, 1.3)
    with pytest.raises(ops.OpError):
        ops.set_word_timing(p, w.id, 3.0, 2.0)
    # words may not pass their neighbours (the export silently dropped such blocks); refused ops change nothing
    with pytest.raises(ops.OpError, match="cannot pass"):
        ops.set_word_timing(p, w.id, 2.0, 2.5)
    assert (w.start, w.end) == (1.0, 1.3)
    b2 = p.blocks[1]
    before = [(x.start, x.end) for x in p.block_words(b2)]
    with pytest.raises(ops.OpError, match="cannot pass"):
        ops.nudge_block(p, b2.id, 2.5)
    assert [(x.start, x.end) for x in p.block_words(b2)] == before
    ops.nudge_block(p, p.blocks[1].id, 0.5)
    assert p.block_span(p.blocks[1])[0] == pytest.approx(make_project().block_span(make_project().blocks[1])[0] + 0.5)


def test_gap_ops():
    p = make_project()
    g = ops.add_gap(p, 10, 15)
    assert g.source == "manual"
    ops.update_gap(p, g.id, end=18)
    assert p.gaps[0].end == 18
    with pytest.raises(ops.OpError):
        ops.update_gap(p, g.id, start=20)
    ops.remove_gap(p, g.id)
    assert p.gaps == []
    with pytest.raises(ops.OpError):
        ops.remove_gap(p, "nope")


# ------------------------------------------------------------------ presets
def test_presets_word_line_phrase_auto():
    p = make_project()
    presets.apply_presets(p, "word")
    assert len(p.blocks) == 9
    presets.apply_presets(p, "line")
    assert texts(p) == ["We sing this song", "all night long", "oh yeah"]
    p.settings.phrase_words = 2
    presets.apply_presets(p, "phrase")
    assert texts(p) == ["We sing", "this song", "all night", "long", "oh yeah"]
    p.settings.auto_pause_s = 0.5
    presets.apply_presets(p, "auto")
    assert texts(p) == ["We sing this song", "all night long", "oh yeah"]
    assert p.validate() == []


def test_presets_per_section_and_gaps():
    p = make_project()
    # chorus covers the second line; a gap swallows the last line
    p.sections = [proj.Section("s1", "verse", 0, 3.2), proj.Section("s2", "chorus", 3.2, 6.0, preset="word")]
    p.gaps = [proj.Gap("g1", 5.7, 20.0)]
    presets.apply_presets(p, "line")
    assert texts(p) == ["We sing this song", "all", "night", "long"]


def test_preset_only_one_section():
    p = make_project()
    p.sections = [proj.Section("s1", "verse", 0, 3.2), proj.Section("s2", "chorus", 3.2, 100, preset="word")]
    ops.merge_words(p, [w.id for w in p.words[:2]])  # manual edit in the verse
    presets.apply_presets(p, "line", only_section="s2")
    assert texts(p)[:2] == ["We sing", "this song"] and texts(p)[2:] == ["all", "night", "long", "oh", "yeah"]


def test_max_chars_split():
    p = make_project()
    p.settings.max_chars = 10
    presets.apply_presets(p, "line")
    assert all(len(t) <= 10 or " " not in t for t in texts(p))
    assert "We sing this song" not in texts(p)


def test_merge_short_blocks():
    p = make_project()
    presets.apply_presets(p, "word")
    p.settings.fps = 25
    merged = presets.merge_short_blocks(p, min_frames=10)  # 0.4 s; every word lasts 0.3 s
    assert merged > 0 and all(p.block_span(b)[1] - p.block_span(b)[0] >= 0.4 for b in p.blocks)
    assert p.validate() == []


def test_merge_short_never_crosses_gap():
    p = make_project()
    presets.apply_presets(p, "word")
    p.gaps = [proj.Gap("g", p.words[3].end, p.words[4].start)]
    presets.merge_short_blocks(p, min_frames=100)
    for b in p.blocks:
        ws = p.block_words(b)
        assert not (ws[0].start < p.gaps[0].start and ws[-1].end > p.gaps[0].end)


def test_format_text():
    assert presets.format_text("hello, World!", "upper") == "HELLO, WORLD!"
    assert presets.format_text("hello, World!", "title", True) == "Hello World"
    assert presets.format_text("don't STOP…", "lower", True) == "don't stop"


def test_sections_yaml(tmp_path):
    f = tmp_path / "sections.yaml"
    f.write_text("default: phrase\nphrase_words: 3\nsections:\n  chorus: word\n  s1: line\n", encoding="utf-8")
    data = presets.load_sections_yaml(f)
    p = make_project()
    p.sections = [proj.Section("s1", "verse", 0, 3), proj.Section("s2", "chorus", 3, 9)]
    presets.apply_sections_config(p, data)
    assert p.settings.granularity == "phrase" and p.settings.phrase_words == 3
    assert [s.preset for s in p.sections] == ["line", "word"]
    f.write_text("sections:\n  chorus: banana\n", encoding="utf-8")
    with pytest.raises(ValueError, match="banana"):
        presets.load_sections_yaml(f)


# ------------------------------------------------------------------ session: undo/redo/autosave
@pytest.fixture
def session(tmp_path):
    path = proj.save(make_project(), tmp_path / "project.json")
    return EditorSession(path)


def test_session_apply_undo_redo_autosave(session):
    p = session.project
    st = session.apply("merge_words", {"word_ids": [w.id for w in p.words[3:5]]})
    assert [b["text"] for b in st["blocks"]][1] == "song all"
    assert st["history"]["can_undo"] and st["history"]["undo_label"] == "merge_words"
    assert len(proj.load(session.path).blocks) == 4  # saved
    st = session.undo()
    assert [b["text"] for b in st["blocks"]] == ["We sing this song", "all night long", "oh yeah"]
    assert len(proj.load(session.path).blocks) == 3
    st = session.redo()
    assert len(st["blocks"]) == 4 and not st["history"]["can_redo"]


def test_session_failed_op_changes_nothing(session):
    before = session.project.to_dict()
    with pytest.raises(ops.OpError):
        session.apply("split_block", {"block_id": session.project.blocks[0].id, "before_word_id": "zzz"})
    assert session.project.to_dict() == before and not session.history.state()["can_undo"]
    with pytest.raises(ops.OpError, match="unknown operation"):
        session.apply("os_system", {})
    with pytest.raises(ops.OpError, match="unexpected"):
        session.apply("remove_gap", {"gap_id": "x", "evil": 1})


def test_set_settings_op(session):
    session.apply("set_settings", {"case": "upper", "max_chars": "30"})
    assert session.project.settings.max_chars == 30
    assert session.state()["blocks"][0]["display"] == "WE SING THIS SONG"
    with pytest.raises(ops.OpError):
        session.apply("set_settings", {"nope": 1})


# ------------------------------------------------------------------ HTTP API
def test_http_api(session, tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from lyric2resolve.editor.app import create_app

    client = TestClient(create_app(session))
    st = client.get("/api/state").json()
    assert len(st["blocks"]) == 3 and "flags" in st
    b0 = st["blocks"][0]
    r = client.post("/api/op/split_block", json={"block_id": b0["id"], "before_word_id": b0["word_ids"][2]})
    assert r.status_code == 200 and len(r.json()["blocks"]) == 4
    r = client.post("/api/op/split_block", json={"block_id": "nope", "before_word_id": "x"})
    assert r.status_code == 400 and "unknown block" in r.json()["detail"]
    assert len(client.post("/api/undo").json()["blocks"]) == 3
    assert len(client.post("/api/redo").json()["blocks"]) == 4
    assert client.get("/api/audio/song").status_code == 404
    wav = tmp_path / "s.wav"
    wav.write_bytes(b"RIFF....")
    session.project.audio["song_wav"] = str(wav)
    assert client.get("/api/audio/song").status_code == 200
    assert client.get("/").status_code == 200


# ------------------------------------------------------------------ your own text (add_text / retime_block)
def test_add_text_lines_blocks_and_words():
    p = make_project()
    first = p.words[0].start
    blocks = ops.add_text(p, "missed first line\nand a second", 0.0, first - 0.1)
    assert [p.block_text(b) for b in blocks] == ["missed first line", "and a second"]
    assert p.words[0].text == "missed" and p.validate() == []
    assert all(0.0 <= w.start < w.end <= first for w in p.words[:5])
    assert [w.start for w in p.words] == sorted(w.start for w in p.words)  # still in time order
    n = len(p.blocks)
    last = p.words[-1].end
    ops.add_text(p, "one two three", last + 1, last + 2, mode="words")
    assert len(p.blocks) == n + 3
    ops.add_text(p, "all in one", last + 3, last + 4, mode="block")
    assert p.block_text(p.blocks[-1]) == "all in one" and p.validate() == []


def test_add_text_refuses_overlaps_and_makes_room_in_gaps():
    p = make_project()
    w = p.words[2]
    with pytest.raises(ops.OpError, match="existing word"):
        ops.add_text(p, "x", w.start - 0.05, w.end)
    with pytest.raises(ops.OpError, match="end time"):
        ops.add_text(p, "x", 5.0, 5.0)
    with pytest.raises(ops.OpError, match="type some text"):
        ops.add_text(p, "  \n ", 0.0, 0.5)
    last = p.words[-1].end
    p.gaps = [proj.Gap("g0100", last + 1, last + 6, "auto")]
    ops.add_text(p, "acid", last + 3, last + 4)
    assert [(round(g.start, 2), round(g.end, 2)) for g in p.gaps] == [(round(last + 1, 2), round(last + 3, 2)),
                                                                     (round(last + 4, 2), round(last + 6, 2))]
    from lyric2resolve.export.timeline import build_plan, check_plan

    assert check_plan(build_plan(p, "16:9")) == []  # the new text is exportable (not inside a gap)


def test_retime_block_stretches_words_and_respects_neighbours():
    p = make_project()
    b = p.blocks[1]
    ws = p.block_words(b)
    s0, e0 = ws[0].start, ws[-1].end
    ops.retime_block(p, b.id, s0 + 0.1, e0 - 0.1)
    ws = p.block_words(b)
    assert ws[0].start == round(s0 + 0.1, 3) and ws[-1].end == round(e0 - 0.1, 3)
    assert all(a.end <= c.start + 1e-6 for a, c in zip(ws, ws[1:]))
    with pytest.raises(ops.OpError, match="overlap"):
        ops.retime_block(p, b.id, p.blocks[0].word_ids and p.block_words(p.blocks[0])[0].start, e0)


def test_add_text_via_session_is_undoable(session):
    n = len(session.project.words)
    session.apply("add_text", {"text": "hello", "start": 0.0, "end": 0.5})
    assert len(session.project.words) == n + 1
    session.undo()
    assert len(session.project.words) == n
