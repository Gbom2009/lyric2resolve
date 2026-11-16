"""Phase 4: project model + transcription/alignment glue (engine mocked)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from lyric2resolve import project as proj
from lyric2resolve import transcription as tr
from lyric2resolve.transcription.engine import TranscriptWord, words_from_result


# ------------------------------------------------------------------ project model
def sample_project() -> proj.Project:
    words = proj.make_words([
        {"text": " Hello", "start": 1.0, "end": 1.4, "confidence": 0.9, "line": 0},
        {"text": "world ", "start": 1.5, "end": 1.9, "confidence": 0.8, "line": 0},
        {"text": "  ", "start": 2.0, "end": 2.0},
        {"text": "again", "start": 3.0, "end": 3.5, "line": 1},
    ])
    return proj.Project(name="t", words=words, blocks=proj.blocks_by_line(words),
                        gaps=[proj.Gap("g0001", 10.0, 20.0)])


def test_make_words_strips_and_ids():
    p = sample_project()
    assert [w.text for w in p.words] == ["Hello", "world", "again"]
    assert [w.id for w in p.words] == ["w00001", "w00002", "w00003"]
    assert [b.word_ids for b in p.blocks] == [["w00001", "w00002"], ["w00003"]]


def test_block_text_span_and_override():
    p = sample_project()
    b = p.blocks[0]
    assert p.block_text(b) == "Hello world" and p.block_span(b) == (1.0, 1.9)
    b.text_override = "HELLO, WORLD!"
    assert p.block_text(b) == "HELLO, WORLD!"


def test_validate_catches_bad_blocks():
    p = sample_project()
    assert p.validate() == []
    p.blocks.append(proj.Block("bx", ["w00001"]))
    assert any("reuses" in m or "out of order" in m for m in p.validate())
    p = sample_project()
    p.blocks = [proj.Block("b1", ["w00001", "w00003"])]
    assert any("not consecutive" in m for m in p.validate())
    p.blocks = [proj.Block("b1", ["nope"])]
    assert any("unknown" in m for m in p.validate())
    p.blocks = [proj.Block("b1", [])]
    assert any("empty" in m for m in p.validate())
    p = sample_project()
    p.gaps.append(proj.Gap("g2", 5, 5))
    assert any("no length" in m for m in p.validate())


def test_json_roundtrip(tmp_path):
    p = sample_project()
    p.settings.fps = 29.97
    p.sections.append(proj.Section("s0001", "chorus", 0.0, 30.0, preset="word"))
    path = proj.save(p, tmp_path / "x" / proj.PROJECT_FILE)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema_version"] == proj.SCHEMA_VERSION and data["words"][0]["text"] == "Hello"
    q = proj.load(path)
    assert q.words == p.words and q.blocks == p.blocks and q.sections == p.sections and q.gaps == p.gaps
    assert q.settings.fps == 29.97


def test_load_errors(tmp_path):
    bad = tmp_path / "p.json"
    bad.write_text("{", encoding="utf-8")
    with pytest.raises(proj.ProjectError):
        proj.load(bad)
    bad.write_text(json.dumps({"schema_version": 99}), encoding="utf-8")
    with pytest.raises(proj.ProjectError, match="newer"):
        proj.load(bad)


def test_unknown_keys_ignored(tmp_path):
    p = tmp_path / "p.json"
    p.write_text(json.dumps({"name": "x", "words": [{"id": "w1", "text": "a", "start": 0, "end": 1, "new": 1}],
                             "settings": {"fps": 24, "future": True}}), encoding="utf-8")
    q = proj.load(p)
    assert q.words[0].text == "a" and q.settings.fps == 24


def test_next_id_unique():
    p = sample_project()
    assert p.next_id("b") not in {b.id for b in p.blocks}


def test_autosave_debounce(tmp_path):
    now = [0.0]
    p = sample_project()
    a = proj.Autosaver(p, tmp_path / "p.json", delay_s=2.0, clock=lambda: now[0])
    assert not a.tick()
    a.touch()
    now[0] = 1.0
    assert not a.tick() and a.dirty
    a.touch()          # another edit restarts the window
    now[0] = 2.5
    assert not a.tick()
    now[0] = 3.1
    assert a.tick() and not a.dirty and (tmp_path / "p.json").exists()
    a.touch()
    assert a.tick(force=True) and a.saves == 2


# ------------------------------------------------------------------ transcription glue
def test_clean_lyrics_keeps_lines_drops_tags():
    text = "[Verse 1]\n  Hello   world \n\n(Chorus)\nWe sing  this song\n"
    assert tr.clean_lyrics(text) == ["Hello world", "We sing this song"]


def test_assign_lines_by_token_count_and_fallback():
    words = [TranscriptWord(t, i, i + 0.5, 1, 9) for i, t in enumerate("a b c d e".split())]
    assert tr.assign_lines(words, ["a b", "c d e"]) == [0, 0, 1, 1, 1]
    assert tr.assign_lines(words, ["a b c d"]) == [9] * 5  # mismatch -> engine segments


def test_run_transcribe_mode_blocks_per_segment():
    eng = tr.FakeEngine(text="hello world\nthis is a test")
    p = tr.run("vocals.wav", eng, "song")
    assert [p.block_text(b) for b in p.blocks] == ["hello world", "this is a test"]
    assert p.transcription["mode"] == "transcribe" and p.language == "en" and p.lyrics is None
    assert p.validate() == []


def test_run_align_mode_keeps_user_line_breaks():
    lyrics = "[Intro]\nHello world\nWe sing, this song\ntogether tonight\n"
    p = tr.run("vocals.wav", tr.FakeEngine(), "song", lyrics=lyrics)
    assert [p.block_text(b) for b in p.blocks] == ["Hello world", "We sing, this song", "together tonight"]
    assert p.transcription["mode"] == "align" and p.lyrics == lyrics
    starts = [w.start for w in p.words]
    assert starts == sorted(starts)


def test_empty_lyrics_falls_back_to_transcription():
    p = tr.run("v.wav", tr.FakeEngine(text="a b"), "s", lyrics="  \n[Chorus]\n")
    assert p.transcription["mode"] == "transcribe"


def test_no_words_is_an_error():
    with pytest.raises(RuntimeError, match="No words"):
        tr.run("v.wav", tr.FakeEngine(text=""), "s")


def test_words_from_stable_ts_result_shape():
    W = SimpleNamespace
    result = W(segments=[W(words=[W(word=" Hi", start=0.1, end=0.3, probability=0.7),
                                  W(word=" ", start=0.3, end=0.3, probability=0.1)]),
                         W(words=[W(word=" there", start=0.5, end=0.9, probability=None)])])
    words = words_from_result(result)
    assert [(w.text, w.segment, w.confidence) for w in words] == [("Hi", 0, 0.7), ("there", 1, 1.0)]


def test_stable_ts_engine_calls(monkeypatch):
    """The engine passes the spec'd options to stable-ts/faster-whisper (mocked module)."""
    import sys

    calls = {}
    W = SimpleNamespace
    res = W(segments=[W(words=[W(word="hi", start=0, end=1, probability=0.9)])], language="nl")

    class FakeModel:
        def transcribe(self, audio, **kw):
            calls["transcribe"] = kw
            return res

        def align(self, audio, text, **kw):
            calls["align"] = (text, kw)
            return res

    fake_mod = SimpleNamespace(load_faster_whisper=lambda name, **kw: calls.setdefault("load", (name, kw))
                               and FakeModel())
    monkeypatch.setitem(sys.modules, "stable_whisper", fake_mod)
    eng = tr.StableTsEngine(tr.EngineOptions(model="large-v3", language="nl", model_dir="/m"))
    t = eng.transcribe("a.wav")
    assert calls["load"] == ("large-v3", {"device": "cuda", "compute_type": "float16", "download_root": "/m"})
    kw = calls["transcribe"]
    assert kw["word_timestamps"] and kw["vad_filter"] and kw["condition_on_previous_text"] is False
    assert kw["language"] == "nl" and t.language == "nl"
    a = eng.align("a.wav", "line one\nline two")
    assert calls["align"][1]["original_split"] and calls["align"][1]["language"] == "nl" and a.mode == "align"


def test_tiny_clip_bundled():
    from lyric2resolve import paths

    clip = paths.code_dir() / "tests" / "data" / "tiny_vocal.wav"
    assert clip.exists() and clip.stat().st_size < 300_000


@pytest.mark.local
def test_real_whisper_tiny_clip():
    """Runs only on the PC: pytest -m local"""
    from lyric2resolve import paths

    eng = tr.engine_from_settings()
    t = eng.transcribe(str(paths.code_dir() / "tests" / "data" / "tiny_vocal.wav"))
    assert "hello" in " ".join(w.text.lower() for w in t.words)
