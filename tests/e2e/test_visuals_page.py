"""Visuals page: render audio-reactive visuals from the browser (no terminal). Blender is simulated."""

import threading
import time
from pathlib import Path

import pytest

from tests.e2e.conftest import free_port, make_project


def fake_render(project_path, template, preset_name, aspects, sections, estimate_only, on_progress, log, cancel,
                **extra):
    from lyric2resolve.render import RenderReport
    from lyric2resolve.render.runner import Progress

    folder = Path(project_path).parent / "visuals" / template / preset_name
    folder.mkdir(parents=True, exist_ok=True)
    log("Building the Blender scene…")
    rep = RenderReport(str(folder), estimates={a: "30 frames x 0.1 s = about 0 h 00 min" for a in aspects})
    if estimate_only:
        return rep
    for i in range(1, 4):
        if cancel.is_set():
            rep.ok, rep.cancelled = False, True
            return rep
        on_progress(aspects[0], Progress(i, 3, i, 0.1 * i, 0.1 * (3 - i)))
        time.sleep(0.15)
    out = folder / f"song_{aspects[0].replace(':', 'x')}.mp4"
    out.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    rep.videos = [str(out)]
    rep.messages = ["Eevee renders on the GPU automatically."]
    return rep


@pytest.fixture
def visuals_page(tmp_path, browser):
    uvicorn = pytest.importorskip("uvicorn")
    from lyric2resolve.editor.app import EditorSession, create_app
    from lyric2resolve.render.jobs import RenderJobs

    path = make_project(tmp_path)
    calls = []

    def render(*a, **k):
        calls.append(k)
        return fake_render(a[0], **k)

    app = create_app(EditorSession(path), tmp_path / "projects", jobs=RenderJobs(render))
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    while not server.started:
        time.sleep(0.05)
    pg = browser.new_page(viewport={"width": 1300, "height": 900})
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/visuals?template=tunnel")
    pg.wait_for_selector(".tpl")
    yield pg, calls, path
    assert not errors, errors
    pg.close()
    server.should_exit = True
    th.join(timeout=5)


def test_visuals_page_render_flow(visuals_page):
    pg, calls, path = visuals_page
    assert pg.locator(".tpl").count() == 5
    assert pg.locator(".tpl.on").get_attribute("data-template") == "tunnel"  # from the Ideas page link
    pg.click(".tpl[data-template=floor_grid]")
    pg.select_option("#preset", "draft")
    pg.check("input[name=aspect][value='9:16']")
    pg.click("#estimate")
    pg.wait_for_function("document.querySelector('#progress-text').textContent.includes('Estimate')")
    assert calls[-1]["estimate_only"] is True and calls[-1]["template"] == "floor_grid"
    pg.click("#render")
    pg.wait_for_function("document.querySelector('#progress-text').textContent.includes('Done')", timeout=15000)
    k = calls[-1]
    assert k["preset_name"] == "draft" and k["aspects"] == ["16:9", "9:16"] and not k["estimate_only"]
    assert k["lyrics_3d"] is True  # "Lyrics inside the scene" is on by default
    pg.wait_for_selector(".video video")
    assert "song_16x9.mp4" in pg.inner_text("#videos")
    src = pg.get_attribute(".video video", "src")
    assert src.startswith("/api/visuals/file/visuals/floor_grid/draft/")


def test_editor_has_visuals_button(page):
    assert page.get_attribute("#btn-visuals", "href") == "/visuals"
