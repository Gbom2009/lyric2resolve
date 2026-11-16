"""Phase 8: merge/split/move/edit UI, gaps, review list, warnings - in a real browser."""

from lyric2resolve import project as proj


def word(page, text):
    return page.locator(".word", has_text=text).first


def blocks(page):
    return page.evaluate("L2R.state.blocks.map(b => b.text)")


def select(page, a, b=None):
    word(page, a).click()
    if b:
        word(page, b).click(modifiers=["Shift"])


def wait_blocks(page, n):
    page.wait_for_function(f"L2R.state.blocks.length === {n}")


def test_merge_with_button_then_undo_redo(page):
    select(page, "song", "night")
    page.click("#btn-merge")
    wait_blocks(page, 4)
    assert blocks(page) == ["We sing this", "song all night", "long", "oh yeah"]
    assert len(proj.load(page.session.path).blocks) == 4  # autosaved
    page.click("#btn-undo")
    wait_blocks(page, 3)
    page.keyboard.press("Control+y")
    wait_blocks(page, 4)


def test_split_with_shortcut_keeps_word_timings(page):
    before = page.evaluate("L2R.state.project.words.map(w => [w.start, w.end])")
    select(page, "this")
    page.keyboard.press("s")
    wait_blocks(page, 4)
    assert blocks(page) == ["We sing", "this song", "all night long", "oh yeah"]
    assert page.evaluate("L2R.state.project.words.map(w => [w.start, w.end])") == before
    select(page, "night")
    page.keyboard.press("w")
    wait_blocks(page, 6)


def test_move_word_between_blocks(page):
    select(page, "song")
    page.keyboard.press("Alt+ArrowRight")
    page.wait_for_function("L2R.state.blocks[1].text.startsWith('song')")
    assert blocks(page)[:2] == ["We sing this", "song all night long"]
    select(page, "song")
    page.click("#btn-move-prev")
    page.wait_for_function("L2R.state.blocks[0].text === 'We sing this song'")


def test_edit_word_and_block_text_in_inspector(page):
    select(page, "sing")
    page.keyboard.press("e")
    page.fill("#insp-word-text", "sang")
    page.keyboard.press("Enter")
    page.wait_for_function("L2R.state.blocks[0].text === 'We sang this song'")
    select(page, "sang")
    page.fill("#insp-block-text", "WE SANG!")
    page.keyboard.press("Enter")
    page.wait_for_function("L2R.state.blocks[0].text === 'WE SANG!'")
    assert "shown as" in page.locator(".block").first.inner_text()


def test_nudge_and_remove_block(page):
    select(page, "We")
    page.keyboard.press("]")
    page.wait_for_function("Math.abs(L2R.state.project.words[0].start - 1.02) < 1e-6")
    select(page, "oh", "yeah")
    page.keyboard.press("Delete")
    wait_blocks(page, 2)
    assert page.locator(".block.hidden-words").count() == 1


def test_gaps_add_remove_and_regions(page):
    page.wait_for_function("L2R.audioReady === true", timeout=10000)
    page.wait_for_function("L2R.regions.getRegions().some(r => r.id === 'gap-g0100')")
    select(page, "all", "long")
    page.keyboard.press("g")
    page.wait_for_function("L2R.state.project.gaps.length === 2")
    assert page.locator(".gap-row").count() == 2
    page.locator("#gap-list li button.small").first.click()
    page.wait_for_function("L2R.state.project.gaps.length === 1")


def test_review_list_jumps_to_flagged_word(page):
    page.wait_for_selector("#review-list button[data-word-id]")
    page.locator("#review-list button[data-word-id]").first.click()
    sel = page.evaluate("L2R.selectedWordIds()")
    assert sel == [page.locator("#review-list button[data-word-id]").first.get_attribute("data-word-id")]


def test_layout_warning_for_long_block(page):
    select(page, "We", "yeah")
    page.click("#btn-merge")
    wait_blocks(page, 1)
    page.fill("#opt-font_size_px", "200")
    page.press("#opt-font_size_px", "Enter")
    page.wait_for_function("L2R.state.project.settings.font_size_px === 200")
    warns = page.evaluate("L2R.state.layout_warnings.map(w => w.layout)")
    assert "16:9" in warns and "9:16" in warns
    assert page.locator(".block.too-long").count() == 1
    assert page.locator("#review-list button[data-block-id]").count() >= 1


def test_section_preset_and_text_options(page):
    s = page.session
    s.project.sections = [proj.Section("s0001", "verse", 0, 3.2), proj.Section("s0002", "chorus", 3.2, 30)]
    s.save()
    page.reload()
    page.wait_for_selector("table.sections tbody tr")
    page.locator("table.sections select").nth(1).select_option("word")
    page.wait_for_function("L2R.state.project.sections[1].preset === 'word'")
    page.locator("table.sections button").nth(1).click()
    page.wait_for_function("L2R.state.blocks.length === 6")
    page.locator("#card-options select").first.select_option("upper")
    page.wait_for_function("L2R.state.blocks[0].display === 'WE SING THIS SONG'")


def test_add_your_own_text_dialog(page):
    """Fixes from testing: add words Whisper missed, at a chosen time (inside the instrumental gap 7-11 s)."""
    n = page.evaluate("L2R.words().length")
    page.click("#lyrics")
    page.keyboard.press("Escape")
    page.click("#btn-add-text")
    page.wait_for_selector("#addtext-dialog[open]")
    page.fill("#addtext-text", "Acid")
    page.fill("#addtext-start", "0:08.00")
    page.fill("#addtext-end", "0:09.00")
    page.click("#addtext-go")
    page.wait_for_function(f"L2R.words().length === {n + 1}")
    assert not page.evaluate("document.querySelector('#addtext-dialog').open")
    w = page.evaluate("L2R.words().find(w => w.text === 'Acid')")
    assert 8.0 <= w["start"] < w["end"] <= 9.0
    assert page.evaluate("L2R.state.project.gaps.length") == 2  # gap split around the new word
    # overlap with an existing word -> explained in the dialog, nothing added
    page.keyboard.press("t")
    page.wait_for_selector("#addtext-dialog[open]")
    page.fill("#addtext-text", "clash")
    page.fill("#addtext-start", "0:01.00")
    page.fill("#addtext-end", "0:01.20")
    page.click("#addtext-go")
    page.wait_for_function("document.querySelector('#addtext-msg').textContent.includes('existing word')")
    page.click("#addtext-close")
    assert page.evaluate("L2R.words().length") == n + 1


def test_block_start_end_editing(page):
    page.locator(".word", has_text="all").first.click()
    page.wait_for_selector("#insp-bstart")
    page.fill("#insp-bstart", "0:03.70")
    page.fill("#insp-bend", "0:04.60")
    page.press("#insp-bend", "Enter")
    page.wait_for_function("L2R.state.blocks[1].start === 3.7 && L2R.state.blocks[1].end === 4.6")
