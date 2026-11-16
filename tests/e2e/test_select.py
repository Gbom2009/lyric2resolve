"""Phase 7: waveform loads, words render, mouse/keyboard selection works."""


def sel(page):
    return page.evaluate("L2R.selectedWordIds().map(id => L2R.state.project.words.find(w => w.id === id).text)")


def word(page, text):
    return page.locator(".word", has_text=text).first


def test_renders_blocks_gaps_and_audio(page):
    assert page.locator(".block").count() == 3
    assert page.locator(".word").count() == 9
    assert "instrumental gap" in page.locator(".gap-row").first.inner_text()
    assert "E2E song" in page.locator("#project-name").inner_text()
    page.wait_for_function("L2R.audioReady === true", timeout=10000)
    assert page.locator("#time-total").inner_text() != "0:00.00"
    assert page.locator(".word.lowconf").count() == 1


def test_click_drag_and_shift_click_selection(page):
    page.wait_for_function("L2R.audioReady === true", timeout=10000)  # no layout shift during the drag
    a, b = word(page, "sing").bounding_box(), word(page, "night").bounding_box()
    page.mouse.move(a["x"] + 5, a["y"] + 5)
    page.mouse.down()
    page.mouse.move(b["x"] + 5, b["y"] + 5, steps=8)
    page.mouse.up()
    assert sel(page) == ["sing", "this", "song", "all", "night"]
    assert page.locator(".word.selected").count() == 5
    word(page, "We").click()
    word(page, "this").click(modifiers=["Shift"])
    assert sel(page) == ["We", "sing", "this"]
    page.keyboard.press("Escape")
    assert sel(page) == []


def test_keyboard_selection(page):
    word(page, "song").click()
    page.keyboard.press("ArrowRight")
    assert sel(page) == ["all"]
    page.keyboard.press("Shift+ArrowRight")
    page.keyboard.press("Shift+ArrowRight")
    assert sel(page) == ["all", "night", "long"]
    page.keyboard.press("ArrowLeft")
    assert sel(page) == ["song"]


def test_selection_region_on_waveform(page):
    page.wait_for_function("L2R.audioReady === true", timeout=10000)
    word(page, "We").click()
    word(page, "song").click(modifiers=["Shift"])
    region = page.evaluate("(() => { const r = L2R.regions.getRegions().find(x => x.id === 'selection'); "
                           "return r ? [r.start, r.end] : null })()")
    assert region and abs(region[0] - 1.0) < 0.01 and abs(region[1] - 2.5) < 0.01


def test_projects_dialog_lists_project(page):
    page.click("#btn-projects")
    page.wait_for_selector("#project-list button")
    assert "E2E song" in page.locator("#project-list").inner_text()
