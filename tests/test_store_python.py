"""Fixes from testing (3): Microsoft Store Python hides files it writes in AppData from ffmpeg & co."""

import os

from lyric2resolve import paths

STORE = r"C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2032.0_x64__qbz5n2kfra8p0"
NORMAL = r"C:\Users\me\AppData\Local\Programs\Python\Python312"


def test_store_python_detection():
    assert paths.store_python(STORE)
    assert not paths.store_python(NORMAL) and not paths.store_python("/usr/local")


def test_data_dir_moves_out_of_appdata_for_store_python():
    env = {"LOCALAPPDATA": r"C:\Users\me\AppData\Local", "USERPROFILE": r"C:\Users\me"}
    assert str(paths.data_dir(env, "win32", prefix=NORMAL)).endswith("lyric2resolve")
    store = paths.data_dir(env, "win32", prefix=STORE)
    assert "AppData" not in str(store) and str(store).endswith(paths.STORE_DATA_NAME)
    assert paths.data_dir({**env, paths.DATA_ENV: r"D:\data"}, "win32", prefix=STORE) == paths.Path(r"D:\data")


def test_migrate_store_data_once(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    (old / "settings").mkdir(parents=True)
    (old / "settings" / "app.json").write_text("{}", encoding="utf-8")
    (old / "projects" / "song").mkdir(parents=True)
    (old / "projects" / "song" / "project.json").write_text("{}", encoding="utf-8")
    (old / "models" / "whisper").mkdir(parents=True)
    new.mkdir()
    assert paths.migrate_store_data(old, new) == ["settings", "projects"]
    assert (new / "settings" / "app.json").exists() and (new / "projects" / "song" / "project.json").exists()
    assert not (new / "models").exists()  # big; downloaded again when needed
    (old / "settings" / "app.json").write_text('{"x": 1}', encoding="utf-8")
    assert paths.migrate_store_data(old, new) == []  # only once
    assert paths.migrate_store_data(tmp_path / "missing", tmp_path / "n2") == []


def test_use_real_temp(tmp_path, monkeypatch):
    import tempfile

    monkeypatch.setattr(tempfile, "tempdir", tempfile.tempdir)
    monkeypatch.setenv("TMP", os.environ.get("TMP", ""))
    monkeypatch.setenv("TEMP", os.environ.get("TEMP", ""))
    t = paths.use_real_temp(tmp_path)
    assert tempfile.gettempdir() == str(t) and os.environ["TEMP"] == str(t)


def test_ffmpeg_missing_file_hint(tmp_path, monkeypatch):
    import pytest

    from lyric2resolve.audio.convert import AudioError, Ffmpeg

    src = tmp_path / "Youre Not Alone (feat. A Little Sound) [1518013873].wav"
    src.write_bytes(b"RIFF")
    err = f"Error opening input file {src}.\nError opening input files: No such file or directory"
    ff = Ffmpeg(runner=lambda cmd: (1, err))
    monkeypatch.setattr(paths, "store_python", lambda prefix=None: True)
    with pytest.raises(AudioError, match="Microsoft Store"):
        ff.to_wav(src, tmp_path / "o.wav")
    monkeypatch.setattr(paths, "store_python", lambda prefix=None: False)
    with pytest.raises(AudioError, match="Python can see this file but ffmpeg cannot"):
        ff.to_wav(src, tmp_path / "o.wav")


def test_brackets_and_spaces_in_filenames_convert(tmp_path):
    """The user's real file name, through the real ffmpeg (when installed)."""
    import shutil

    import numpy as np
    import pytest

    from lyric2resolve.audio import wavio
    from lyric2resolve.audio.convert import Ffmpeg, cached_wav

    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    src = wavio.write(tmp_path / "in" / "Youre Not Alone (feat. A Little Sound) [1518013873].wav",
                      np.zeros((4410, 2), dtype=np.float32), 44100)
    out = cached_wav(src, tmp_path / "cache", Ffmpeg(shutil.which("ffmpeg")))
    assert out.exists() and out.stat().st_size > 1000
