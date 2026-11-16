"""Phase 17: Assistant card with a fake `claude` CLI; Claude's tool calls update the editor live."""

import json

import pytest

from lyric2resolve import paths
from lyric2resolve.settings import AppSettings, save_settings
from tests.test_claude_link import make_fake_claude


@pytest.fixture
def fake_claude(tmp_path):
    save_settings(AppSettings(claude_cli_path=str(make_fake_claude(tmp_path / "bin"))), paths.settings_dir())


@pytest.fixture
def no_claude(monkeypatch):
    save_settings(AppSettings(claude_cli_path=""), paths.settings_dir())
    monkeypatch.setattr("lyric2resolve.claude_link.cli.shutil.which", lambda name: None)
    monkeypatch.setattr("lyric2resolve.claude_link.cli.claude_candidates", lambda env: [])


def test_assistant_chat_and_live_edit(fake_claude, page):
    page.wait_for_function("document.querySelector('#asst-status').textContent.includes('2.1.325')")
    page.fill("#asst-input", "hello")
    page.click("#asst-send")
    page.wait_for_selector(".asst-assistant:has-text('echo: hello')")
    assert page.locator(".asst-user").first.inner_text() == "hello"
    page.wait_for_function("!document.querySelector('#asst-send').disabled")
    blocks_before = page.locator(".block[data-block-id]").count()
    ids = page.evaluate("[L2R.words()[0].id, L2R.words()[1].id]")
    page.fill("#asst-input", "TOOL merge_words " + json.dumps({"word_ids": ids}))
    page.press("#asst-input", "Control+Enter")
    page.wait_for_selector(".asst-tool:has-text('merge_words')")
    page.wait_for_function(f"L2R.state.blocks.length === {blocks_before + 1}")  # 'We sing' + 'this song'
    assert page.evaluate("L2R.state.blocks[0].word_ids") == ids
    assert page.evaluate("L2R.state.history.can_undo")


def test_assistant_without_cli_shows_instructions(no_claude, page):
    page.wait_for_function("document.querySelector('#asst-status').textContent.includes('not found')")
    assert page.locator("#asst-send").is_disabled()
    assert page.locator("#asst-input").is_disabled()
