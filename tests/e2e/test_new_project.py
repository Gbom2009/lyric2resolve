"""Fixes from testing: an empty editor explains itself, and a project can be created from the browser."""

import threading
import time

import pytest

from tests.e2e.conftest import free_port


@pytest.fixture
def empty_editor(tmp_path, browser):
    uvicorn = pytest.importorskip("uvicorn")
    from lyric2resolve.editor import newproject
    from lyric2resolve.editor.app import create_app
    from lyric2resolve.transcription import FakeEngine
    from tests.test_settings_batch import copy_ffmpeg

    jobs = newproject.NewProjectJobs(tmp_path / "projects", engine_factory=lambda m, l: FakeEngine(),
                                     ffmpeg_factory=copy_ffmpeg)
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(create_app(None, tmp_path / "projects", new_projects=jobs),
                                           host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    while not server.started:
        time.sleep(0.05)
    pg = browser.new_page(viewport={"width": 1300, "height": 850})
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/")
    yield pg, tmp_path
    assert not errors, errors
    pg.close()
    server.should_exit = True
    th.join(timeout=5)


def test_empty_editor_guides_to_new_project(empty_editor):
    pg, _ = empty_editor
    pg.wait_for_selector("#project-dialog[open]")
    assert "New project" in pg.inner_text("#project-list")
    pg.click("#project-dialog form button")  # Close
    assert "No project open" in pg.evaluate(
        "getComputedStyle(document.querySelector('#card-selection .card-body'), '::after').content")
    pg.click("#btn-play")  # explains + reopens the projects dialog instead of doing nothing
    pg.wait_for_selector("#project-dialog[open]")
    assert "No project open" in pg.inner_text("#status")


def test_create_project_in_browser(empty_editor):
    pg, tmp = empty_editor
    from tests.test_new_project import wav_bytes

    song = tmp / "My Song.wav"
    song.write_bytes(wav_bytes(tmp, "s.wav", 220))
    aca = tmp / "My Song acapella.wav"
    aca.write_bytes(wav_bytes(tmp, "a.wav", 330))
    pg.wait_for_selector("#project-dialog[open]")
    pg.click("#btn-new-project")
    pg.wait_for_selector("#new-dialog[open]")
    pg.set_input_files("#new-form input[name=song]", str(song))
    pg.set_input_files("#new-form input[name=acapella]", str(aca))
    pg.fill("#new-form textarea[name=lyrics]", "we sing this song\nall night long")
    pg.click("#new-go")
    pg.wait_for_function("L2R.state && L2R.state.project.name === 'My Song'", timeout=60000)
    assert not pg.evaluate("document.querySelector('#new-dialog').open")
    assert pg.locator(".word").count() == 7 and pg.locator(".block[data-block-id]").count() == 2
    assert "ready" in pg.inner_text("#status")
    assert pg.inner_text("#card-selection .card-body").strip()  # side cards are live now
    assert not pg.evaluate("document.body.classList.contains('no-project')")
