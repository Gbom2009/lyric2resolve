"""Headless-browser tests for the editor (Playwright + Chromium). Skipped when unavailable."""

from __future__ import annotations

import os
import socket
import threading
import time

import numpy as np
import pytest

from lyric2resolve import project as proj

LINES = [["We", "sing", "this", "song"], ["all", "night", "long"], ["oh", "yeah"]]


def make_project(tmp_path):
    from lyric2resolve.audio import wavio

    raw, t = [], 1.0
    for li, line in enumerate(LINES):
        for w in line:
            raw.append({"text": w, "start": t, "end": t + 0.3, "confidence": 0.9 if w != "oh" else 0.2, "line": li})
            t += 0.4
        t += 1.0
    words = proj.make_words(raw)
    sr = 22050
    tt = np.arange(int(12 * sr)) / sr
    y = (0.2 * np.sin(2 * np.pi * 220 * tt)).astype(np.float32)
    wav = wavio.write(tmp_path / "song.wav", np.stack([y, y], axis=1), sr)
    p = proj.Project(name="E2E song", words=words, blocks=proj.blocks_by_line(words),
                     audio={"song_wav": str(wav), "vocals_wav": str(wav), "instrumental_wav": str(wav)},
                     gaps=[proj.Gap("g0100", 7.0, 11.0, "auto")])
    return proj.save(p, tmp_path / "projects" / "e2e" / proj.PROJECT_FILE)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def editor_url(tmp_path):
    uvicorn = pytest.importorskip("uvicorn")
    from lyric2resolve.editor.app import EditorSession, create_app

    path = make_project(tmp_path)
    session = EditorSession(path)
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(create_app(session, tmp_path / "projects"), host="127.0.0.1",
                                           port=port, log_level="warning"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/", session
    server.should_exit = True
    th.join(timeout=5)


@pytest.fixture(scope="session")
def browser():
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:  # browser not installed (or another Playwright version's browser)
            exe = os.environ.get("L2R_CHROMIUM")  # e.g. a preinstalled chromium binary
            if not exe:
                pytest.skip(f"chromium not available: {exc}")
            b = p.chromium.launch(executable_path=exe)
        yield b
        b.close()


@pytest.fixture
def page(browser, editor_url):
    url, session = editor_url
    pg = browser.new_page(viewport={"width": 1300, "height": 850})
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(url)
    pg.wait_for_selector(".word")
    pg.session = session
    yield pg
    assert not errors, errors
    pg.close()
