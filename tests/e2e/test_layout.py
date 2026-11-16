"""Fixes from testing: a long song at normal zoom made the whole page resize in a loop."""

import threading
import time

import numpy as np
import pytest

from lyric2resolve import project as proj
from tests.e2e.conftest import free_port


@pytest.fixture
def long_song_page(tmp_path, browser):
    uvicorn = pytest.importorskip("uvicorn")
    from lyric2resolve.audio import wavio
    from lyric2resolve.editor.app import EditorSession, create_app

    sr, dur = 8000, 200  # wide waveform at the default zoom (60 px/s -> 12000 px)
    t = np.arange(dur * sr) / sr
    y = (0.3 * np.sin(2 * np.pi * 110 * t)).astype(np.float32)
    wav = wavio.write(tmp_path / "song.wav", np.stack([y, y], 1), sr)
    words = proj.make_words([{"text": f"w{i}", "start": 2 + i, "end": 2.5 + i, "line": i // 5} for i in range(60)])
    path = proj.save(proj.Project(name="Long", words=words, blocks=proj.blocks_by_line(words),
                                  audio={"song_wav": str(wav), "vocals_wav": str(wav), "instrumental_wav": str(wav)}),
                     tmp_path / "projects" / "long" / proj.PROJECT_FILE)
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(create_app(EditorSession(path), path.parents[1]), host="127.0.0.1",
                                           port=port, log_level="warning"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    while not server.started:
        time.sleep(0.05)
    pg = browser.new_page(viewport={"width": 1366, "height": 768})
    pg.goto(f"http://127.0.0.1:{port}/")
    pg.wait_for_function("window.L2R && L2R.audioReady", timeout=60000)
    yield pg
    pg.close()
    server.should_exit = True
    th.join(timeout=5)


def test_long_waveform_does_not_resize_the_page_in_a_loop(long_song_page):
    pg = long_song_page
    pg.evaluate("""() => { window._n = 0; window._w = new Set();
        const ro = new ResizeObserver(() => { window._n++; window._w.add(document.querySelector('.workspace').offsetWidth); });
        ro.observe(document.querySelector('.workspace')); }""")
    time.sleep(2.0)
    assert pg.evaluate("window._n") <= 2, "page keeps resizing"
    assert pg.evaluate("[...window._w]") == [pg.evaluate("innerWidth")]
    assert pg.evaluate("document.documentElement.scrollWidth") <= pg.evaluate("innerWidth")
