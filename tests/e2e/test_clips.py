"""Clips card: add your own video at the playhead, and 'Make a clip with Claude' (fake claude CLI)."""

import shutil
import subprocess

import pytest

from tests.e2e.test_assistant import fake_claude  # noqa: F401  (fixture)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_add_own_video_clip(page, tmp_path):
    vid = tmp_path / "loop.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                    "color=c=blue:s=64x36:d=1.2", "-r", "25", str(vid)], check=True)
    page.wait_for_selector("#card-clips button")
    page.evaluate("L2R.ws.setTime(7.5)")
    page.uncheck("#clip-snap-default")
    page.check("#clip-hide-default")
    page.set_input_files("#clip-file", str(vid))
    page.wait_for_function("L2R.state.project.clips.length === 1")
    c = page.evaluate("L2R.state.project.clips[0]")
    assert abs(c["start"] - 7.5) < 0.05 and abs(c["end"] - 8.7) < 0.1 and c["hide_lyrics"]
    page.wait_for_selector(".clip-item video")
    assert page.evaluate("L2R.regions.getRegions().some(r => String(r.id).startsWith('clip-'))")


def test_make_a_clip_with_claude_sends_a_complete_request(fake_claude, page):  # noqa: F811
    page.wait_for_selector("#btn-claude-clip")
    page.wait_for_function("document.querySelector('#asst-status').textContent.includes('2.1.325')")
    page.click("#btn-claude-clip")
    page.wait_for_selector("#cc-dialog[open]")
    page.fill("#cc-name", "acid")
    page.fill("#cc-desc", "3D ACID text with glowing green liquid dripping down")
    page.uncheck("#cc-snap")
    page.fill("#cc-start", "0:06.00")
    page.fill("#cc-end", "0:07.00")
    page.click("#cc-go")
    page.wait_for_selector(".asst-assistant")  # the fake claude echoes the prompt it got
    text = page.locator(".asst-assistant").last.inner_text()
    assert "Make a custom Blender clip called \"acid\"" in text and "custom_scene_guide" in text
    assert "render_clip" in text and "start 6.000, end 7.000" in text and "hide_lyrics true" in text
    assert "glowing green liquid" in text
