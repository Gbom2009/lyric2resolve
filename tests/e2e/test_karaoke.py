"""Phase 12: karaoke page in a real browser (timing logic, highlight, countdown, queue)."""


def open_karaoke(page):
    url = page.url.split("#")[0].rstrip("/")
    path = str(page.session.path)
    page.goto(f"{url}/karaoke?path={path}")
    page.wait_for_function("window.K && K.S.data && K.S.bufs.music")
    return path


def at(page, t):
    page.evaluate(f"K.S.offset = {t}; K.S.playing = false;")
    page.wait_for_timeout(80)  # one animation frame renders the state
    return page.evaluate("K.last")


def test_word_highlight_countdown_and_next_line(page):
    open_karaoke(page)
    st = at(page, 0.3)
    assert st["countdown"] and st["countdown"]["label"] == "Get ready"
    st = at(page, 1.5)  # "sing" (1.4-1.7)
    assert st["current"] == 0 and st["word"] == 1
    assert not page.locator("#countdown").is_visible()  # no countdown while singing (regression)
    assert page.locator("#line-current .w.sung").count() == 1
    assert page.locator("#line-current .w.now").inner_text().strip() == "sing"
    assert page.locator("#line-next").inner_text() == "all night long"
    st = at(page, 8.5)  # inside the instrumental gap (7-11)
    assert st["inGap"] and st["countdown"]["label"] == "Instrumental"
    assert page.locator("#countdown").is_visible()


def test_vocal_slider_and_shortcuts(page):
    open_karaoke(page)
    assert page.evaluate("K.S.musicIsSong") is False  # instrumental + acapella loaded
    page.keyboard.press("ArrowUp")
    page.keyboard.press("ArrowUp")
    assert page.locator("#k-vocals-val").inner_text() == "20%"
    page.keyboard.press("q")
    assert page.locator("#queue").is_visible()


def test_queue_add_reorder_persist(page):
    path = open_karaoke(page)
    page.keyboard.press("q")
    assert page.locator("#q-items li").count() == 1
    page.fill("#q-search", "e2e")
    page.locator("#q-projects button").first.click()
    page.wait_for_function("document.querySelectorAll('#q-items li').length === 2")
    page.evaluate("K.move(1, -1)")
    page.wait_for_function("K.S.index === 1")
    from lyric2resolve import karaoke

    assert karaoke.load_playlists().playlists["Karaoke night"] == [path, path]
