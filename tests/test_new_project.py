"""Fixes from testing: create a new project from the browser (upload -> pipeline -> open)."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest

from lyric2resolve import project as proj
from lyric2resolve.audio import wavio
from lyric2resolve.editor import newproject
from lyric2resolve.transcription import FakeEngine
from tests.test_settings_batch import copy_ffmpeg


def wav_bytes(tmp_path: Path, name: str, freq: float, seconds: float = 8.0) -> bytes:
    sr = 44100
    t = np.arange(int(seconds * sr)) / sr
    y = (0.3 * np.sin(2 * np.pi * freq * t) * ((t > 1) & (t < 6))).astype(np.float32)
    return wavio.write(tmp_path / name, np.stack([y, y], axis=1), sr).read_bytes()


@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient

    from lyric2resolve.editor.app import create_app

    jobs = newproject.NewProjectJobs(tmp_path / "projects", engine_factory=lambda m, l: FakeEngine(),
                                     ffmpeg_factory=copy_ffmpeg, settings_dir=tmp_path / "settings")
    c = TestClient(create_app(None, tmp_path / "projects", settings_dir=tmp_path / "settings", new_projects=jobs))
    c.jobs = jobs
    return c


def test_unique_folder(tmp_path):
    t, f = newproject.unique_folder(tmp_path, "My Song")
    assert t == "My Song" and f.name == "My_Song"
    f.mkdir()
    t2, f2 = newproject.unique_folder(tmp_path, "My Song")
    assert t2 == "My Song (2)" and f2 != f
    assert newproject.unique_folder(tmp_path, "  ")[0] == "Untitled"


def test_new_project_upload_runs_pipeline_and_opens(client, tmp_path):
    assert client.get("/api/state").status_code == 409  # nothing open yet
    files = {"song": ("Song.wav", wav_bytes(tmp_path, "s.wav", 220), "audio/wav"),
             "acapella": ("Song acapella.wav", wav_bytes(tmp_path, "a.wav", 330), "audio/wav")}
    r = client.post("/api/projects/new", files=files,
                    data={"name": "First", "lyrics": "we sing this song\nall night long", "granularity": "word"})
    assert r.status_code == 200, r.text
    assert client.jobs.wait(60)
    st = client.get("/api/projects/new/status").json()
    assert st["ok"] and st["done"] and not st["running"], st
    assert any("done" in line for line in st["log"])
    opened = client.post("/api/projects/new/open").json()
    assert opened["project"]["name"] == "First" and len(opened["blocks"]) == 7  # word preset
    assert client.get("/api/state").status_code == 200
    folder = tmp_path / "projects" / "First"
    assert (folder / proj.PROJECT_FILE).is_file() and (folder / "input" / "Song.wav").is_file()
    assert (folder / "input" / "lyrics.txt").read_text(encoding="utf-8").startswith("we sing")
    assert not (folder / "export").exists()  # export only when the user presses Export
    names = [p["name"] for p in client.get("/api/projects").json()["projects"]]
    assert names == ["First"]


def test_new_project_errors(client, tmp_path):
    r = client.post("/api/projects/new", files={"song": ("notes.pdf", b"x", "application/pdf")})
    assert r.status_code == 400
    assert client.post("/api/projects/new/open").status_code == 409  # nothing made yet
    # pipeline failure (e.g. Whisper not installed) is reported, not crashed
    client.jobs.engine_factory = lambda m, l: (_ for _ in ()).throw(RuntimeError(newproject.DEPS_HELP))
    r = client.post("/api/projects/new", files={"song": ("S.wav", wav_bytes(tmp_path, "s.wav", 220), "audio/wav")})
    assert r.status_code == 200
    client.jobs.wait(30)
    st = client.get("/api/projects/new/status").json()
    assert not st["ok"] and "Run setup" in st["error"]
    assert not (tmp_path / "projects" / "S").exists()  # failed attempt cleaned up, name free again


def test_default_engine_explains_missing_whisper(monkeypatch):
    import builtins

    real = builtins.__import__
    monkeypatch.setattr(builtins, "__import__", lambda n, *a, **k: (_ for _ in ()).throw(ImportError(n, name=n))
                        if n in ("faster_whisper", "stable_whisper") else real(n, *a, **k))
    with pytest.raises(RuntimeError, match="Run setup"):
        newproject.default_engine("", "")


def test_default_engine_explains_broken_torch(monkeypatch):
    """The user's error (2026-11-16): torchaudio's DLL fails to load -> explain + how the update repairs it."""
    import builtins

    real = builtins.__import__
    err = OSError(r"Could not load this library: D:\app\.venv\Lib\site-packages\torchaudio\lib\libtorchaudio.pyd")
    monkeypatch.setattr(builtins, "__import__", lambda n, *a, **k: (_ for _ in ()).throw(err)
                        if n == "stable_whisper" else real(n, *a, **k))
    monkeypatch.setitem(__import__("sys").modules, "faster_whisper", object())
    with pytest.raises(RuntimeError, match="Update now") as ei:
        newproject.default_engine("", "")
    assert "libtorchaudio.pyd" in str(ei.value)
