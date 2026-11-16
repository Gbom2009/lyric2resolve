"""Phase 18: settings page saves immediately; the branding toggle restyles every page."""


def test_settings_page_branding_and_defaults(page):
    base = page.url
    page.goto(base + "settings")
    page.wait_for_selector("#tools .tool")
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") != "rgb(4, 4, 4)"
    page.check("[data-key=funqtion_branding]")
    page.wait_for_function("getComputedStyle(document.body).backgroundColor === 'rgb(4, 4, 4)'")
    page.select_option("#fps", "29.97")
    page.wait_for_function("document.querySelector('#saved').textContent.includes('Saved')")
    page.uncheck("[data-layout='9:16']")
    page.wait_for_function("document.querySelector('#saved').textContent.includes('Saved')")
    from lyric2resolve.settings import load_settings

    s, _ = load_settings()
    assert s.funqtion_branding and s.default_fps == 29.97 and s.layouts == ["16:9"]
    page.goto(base)
    page.wait_for_selector(".word")
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(4, 4, 4)"
    assert "funqtion-logo" in page.evaluate("getComputedStyle(document.querySelector('.brand .logo')).backgroundImage")
    assert page.locator("#update-banner").is_hidden()  # update check disabled in tests


def test_brand_text_style_button(page):
    base = page.url
    page.goto(base + "settings")
    page.click("#brand-style")
    page.wait_for_function("document.querySelector('#brand-msg').textContent.includes('added')")
    assert "Team Funqtion" in [s for s in page.session.project.styles.get("presets", {})]
