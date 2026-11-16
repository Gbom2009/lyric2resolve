"""Regression tests for bugs found in the code review of feature update A."""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

import pytest

from lyric2resolve import project as proj
from lyric2resolve.editor import ops, presets

REPO = Path(__file__).resolve().parents[1]


def words_project(spec, sections=()):
    words = proj.make_words([{"text": t, "start": s, "end": s + 0.4, "line": li} for t, s, li in spec])
    return proj.Project(words=words, blocks=proj.blocks_by_line(words), sections=list(sections))


def test_resolve_script_finds_store_python_data_folder(tmp_path, monkeypatch):
    sys.path.insert(0, str(REPO / "src" / "lyric2resolve" / "export" / "resolve_template"))
    import lyric2resolve_build_timeline as script

    monkeypatch.delenv("LYRIC2RESOLVE_DATA", raising=False)
    monkeypatch.setattr(script.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    job = tmp_path / "job.json"
    job.write_text('{"ok": 1}', encoding="utf-8")
    ptr = tmp_path / "home" / "lyric2resolve-data" / "exports" / "last_resolve_job.json"
    ptr.parent.mkdir(parents=True)
    ptr.write_text('{"job": "%s"}' % str(job).replace("\\", "\\\\"), encoding="utf-8")
    assert script.load_job() == {"ok": 1}


def test_install_script_for_store_python_uses_a_child_process(tmp_path):
    from lyric2resolve.export import resolve_job

    cmds = []

    class R:
        returncode = 0

    dst = resolve_job.install_script(tmp_path / "Utility", store_python=True, run=lambda c: cmds.append(c) or R())
    assert cmds[0][:3] == ["cmd", "/c", "mkdir"] and cmds[1][:4] == ["cmd", "/c", "copy", "/Y"]
    assert cmds[1][-1] == str(dst)


def test_self_check_command_survives_quotes_in_the_install_path(tmp_path):
    from lyric2resolve.updater import core

    repo = tmp_path / "O'Brien's apps" / "lyric2resolve"
    (repo / "src").mkdir(parents=True)
    import shutil

    shutil.copytree(REPO / "src" / "lyric2resolve", repo / "src" / "lyric2resolve")
    out = subprocess.run(core.self_check_command(repo, Path(sys.executable)), capture_output=True, text=True)
    assert out.returncode == 0 and out.stdout.startswith("ok"), out.stderr


def test_apply_preset_to_one_section_keeps_words_of_a_line_crossing_the_boundary():
    p = words_project([("a", 1, 0), ("b", 2, 0), ("c", 3, 0), ("d", 4, 0), ("e", 5, 1)],
                      [proj.Section("s1", "verse", 0, 2.5), proj.Section("s2", "chorus", 2.5, 10, preset="word")])
    presets.apply_presets(p, only_section="s2")
    shown = [w for b in p.blocks for w in b.word_ids]
    assert len(shown) == 5 and p.validate() == []  # 'a b' (verse part of the line) is not lost
    assert [p.block_text(b) for b in p.blocks][0] == "a b"


def test_retime_block_tolerates_rounded_times():
    p = words_project([("a", 1.0, 0), ("b", 12.344, 1), ("c", 12.75, 1), ("d", 14.0, 2)])
    p.words[0].end = 12.344  # touching words, common in Whisper output
    b = p.blocks[1]
    ops.retime_block(p, b.id, 12.34, 13.5)  # the browser sent the rounded start
    assert p.block_words(b)[0].start == 12.344


def test_batch_never_overwrites_an_existing_project(tmp_path):
    from lyric2resolve import batch
    from lyric2resolve.settings import AppSettings
    from lyric2resolve.transcription import FakeEngine
    from tests.test_end_to_end import make_inputs
    from tests.test_settings_batch import copy_ffmpeg

    song, aca, _ = make_inputs(tmp_path / "in")
    kw = dict(settings=AppSettings(layouts=["16:9"]), engine=FakeEngine(), ffmpeg=copy_ffmpeg(),
              cache_dir=tmp_path / "c", analyze=False, do_export=False, log=lambda m: None)
    job = batch.BatchJob(str(song), str(aca))
    assert batch.run_song(job, tmp_path / "out", **kw).ok
    again = batch.run_song(job, tmp_path / "out", **kw)
    assert not again.ok and "already exists" in again.error
    assert batch.run_song(job, tmp_path / "out", overwrite=True, **kw).ok


def test_batch_titles_with_voice_are_songs_when_unpaired(tmp_path):
    from lyric2resolve import batch

    for n in ("The Voice.mp3", "Hello.mp3", "Hello (Acapella).wav", "Vox Populi.wav"):
        (tmp_path / n).write_bytes(b"x")
    jobs = {j.title: j for j in batch.find_jobs(tmp_path)}
    assert set(jobs) == {"The Voice", "Hello", "Vox Populi"}
    assert Path(jobs["Hello"].acapella).name == "Hello (Acapella).wav" and jobs["The Voice"].acapella is None


def test_mcp_never_switches_the_users_project(tmp_path):
    from lyric2resolve.claude_link import mcp_server

    be = mcp_server.HttpBackend("http://127.0.0.1:9/", tmp_path / "a" / "project.json")
    be._call = lambda m, r, b=None: {"current": str(tmp_path / "b" / "project.json")} if r == "api/projects" else {}
    with pytest.raises(mcp_server.ToolError, match="another project open"):
        be.state()


def test_stop_removes_the_frame_that_was_being_written(tmp_path):
    from lyric2resolve.render import runner as rn

    out = tmp_path / "frames"
    out.mkdir()
    (out / "frame_0001.png").write_bytes(b"png")  # finished earlier

    def lines():
        yield "Fra:2 rendering\n"
        (out / "frame_0002.png").write_bytes(b"half")  # Stop kills Blender while it writes frame 2
        yield "Fra:2 ...\n"

    class Proc:
        def __init__(self):
            self.stdout = lines()

        def poll(self):
            return None

        def terminate(self):
            pass

        def wait(self, timeout=None):
            return 1

        def kill(self):
            pass

    cancel = threading.Event()
    cancel.set()
    r = rn.BlenderRunner(Path("blender"), popen=lambda *a, **k: Proc())
    res = r.render(Path("x.blend"), {"output": str(out / "frame_"), "width": 2, "height": 2, "fps": 25},
                   1, 3, cancel=cancel)
    assert res.cancelled
    assert (out / "frame_0001.png").exists() and not (out / "frame_0002.png").exists()
    assert rn.missing_frames(out, 1, 3) == [2, 3]  # a resume renders frame 2 again


def test_assistant_send_is_atomic(tmp_path, monkeypatch):
    from lyric2resolve.claude_link import Assistant

    a = Assistant(settings_dir=tmp_path)
    started = threading.Event()

    def slow_send(*args, **kw):
        started.set()
        threading.Event().wait(0.3)
        return {"turn": 1}

    monkeypatch.setattr(a, "_send", slow_send)
    results = []

    def go():
        try:
            results.append(a.send(tmp_path / "p.json", "hi"))
        except RuntimeError as exc:
            results.append(exc)

    t1 = threading.Thread(target=go)
    t1.start()
    started.wait(2)
    go()
    t1.join()
    assert sum(isinstance(r, RuntimeError) for r in results) == 1


def test_failed_op_with_odd_input_is_rolled_back(tmp_path):
    from lyric2resolve.editor.app import EditorSession

    path = proj.save(words_project([("a", 1, 0), ("b", 2, 1)]), tmp_path / "project.json")
    s = EditorSession(path)
    n = len(s.history.undo_stack) if hasattr(s.history, "undo_stack") else None
    with pytest.raises(ops.OpError):
        s.apply("set_block_text", {"block_id": "nope", "text": 123})
    if n is not None:
        assert len(s.history.undo_stack) == n
