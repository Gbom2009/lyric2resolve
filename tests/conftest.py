"""Every test gets its own empty data folder: tests never touch the real user data."""

import pytest


@pytest.fixture(autouse=True)
def _isolated_data_dir(monkeypatch, tmp_path_factory):
    monkeypatch.setenv("LYRIC2RESOLVE_DATA", str(tmp_path_factory.mktemp("l2r-data")))
    monkeypatch.setenv("L2R_NO_UPDATE_CHECK", "1")  # the editor's update banner never runs git fetch in tests
    monkeypatch.delenv("L2R_LAUNCHER", raising=False)
