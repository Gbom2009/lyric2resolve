"""Phase 9: style editor + live preview in the browser."""


def test_style_card_preview_and_save(page):
    page.wait_for_selector("#style-edit")
    assert page.locator(".style-preview .pv-text").first.inner_text() == "We sing this song"
    page.select_option("#style-edit", "Neon")
    shadow = page.evaluate("getComputedStyle(document.querySelector('.p169 .pv-text')).textShadow")
    assert shadow and shadow != "none"
    page.once("dialog", lambda d: d.accept("My Neon"))
    page.click("#style-save-as")
    page.wait_for_function("'My Neon' in L2R.state.styles.presets")
    page.select_option("#style-level", "full")
    page.wait_for_function("L2R.state.project.settings.styling_level === 'full'")
    page.locator(".word", has_text="all").first.click()
    page.select_option("#style-block", "My Neon")
    page.wait_for_function("L2R.state.blocks[1].style === 'My Neon'")
