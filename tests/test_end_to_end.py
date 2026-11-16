"""Phase 19: end-to-end CLI (`lyric2resolve --song ... --acapella ... --out ...`) with a fake Whisper,
real analysis + exports, and a fake Blender render."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from lxml import etree

from lyric2resolve import project as proj
from lyric2resolve.audio import wavio
from lyric2resolve.transcription import FakeEngine
from tests.test_settings_batch import copy_ffmpeg


def make_inputs(folder: Path) -> tuple[Path, Path, Path]:
    sr = 44100
    t = np.arange(int(16 * sr)) / sr
    kick = (np.sin(2 * np.pi * 60 * t) * (np.mod(t, 0.5) < 0.1)).astype(np.float32) * 0.6
    vocal = (np.sin(2 * np.pi * 300 * t) * (((t > 1) & (t < 5)) | ((t > 11) & (t < 14)))).astype(np.float32) * 0.3
    song = wavio.write(folder / "My Song.wav", np.stack([kick + vocal] * 2, axis=1), sr)
    aca = wavio.write(folder / "My Song acapella.wav", np.stack([vocal] * 2, axis=1), sr)
    lyr = folder / "lyrics.txt"
    lyr.write_text("[Verse]\nwe sing this song\nall night long\n\n[Chorus]\noh yeah\n", encoding="utf-8")
    return song, aca, lyr


def test_cli_routing():
    from lyric2resolve import cli

    assert cli.wants_pipeline(["--song", "a.wav"]) and not cli.wants_pipeline(["editor", "--song"])
    assert not cli.wants_pipeline(["check-update"]) and not cli.wants_pipeline([])


def test_end_to_end_cli(tmp_path, capsys, monkeypatch):
    from lyric2resolve import cli

    monkeypatch.setattr("lyric2resolve.export.resolve_job.resolve_scripts_dir", lambda *a, **k: tmp_path / "rs")

    song, aca, lyr = make_inputs(tmp_path / "in")
    rendered = {}

    class Rep:
        ok, videos, messages = True, ["v.mp4"], ["Eevee renders on the GPU automatically."]

    def fake_render(path, template, preset_name):
        rendered.update(path=path, template=template, preset=preset_name)
        return Rep()

    out = tmp_path / "out"
    code = cli.main(["--song", str(song), "--acapella", str(aca), "--lyrics", str(lyr), "--granularity", "line",
                     "--fps", "29.97", "--render-preset", "standard", "--template", "tunnel", "--out", str(out)],
                    engine=FakeEngine(), ffmpeg=copy_ffmpeg(), render=fake_render)
    text = capsys.readouterr().out
    assert code == 0, text
    path = out / "My_Song" / proj.PROJECT_FILE
    p = proj.load(path)
    assert p.settings.fps == 29.97 and [len(p.block_words(b)) for b in p.blocks] == [4, 3, 2]  # lyric lines kept
    assert p.analysis.get("bpm") and p.lyrics
    exp = out / "My_Song" / "export"
    for layout in ("16x9", "9x16"):
        xml = etree.parse(str(exp / f"My_Song_{layout}.fcpxml"))
        titles = xml.findall(".//title")
        assert len(titles) == 3 and xml.getroot().get("version") == "1.9"
    for name in ("My_Song_16x9_lines.srt", "My_Song_16x9_words.srt", "My_Song_9x16.csv", "My_Song_16x9_markers.edl",
                 "My_Song_resolve_job.json", "lyric2resolve_build_timeline.py"):
        assert (exp / name).is_file(), name
    assert rendered == {"path": path, "template": "tunnel", "preset": "standard"}
    assert "video: v.mp4" in text and "Project:" in text
    assert (tmp_path / "rs" / "lyric2resolve_build_timeline.py").is_file() and "Resolve script installed" in text


def test_end_to_end_missing_acapella_file_and_render_failure(tmp_path, capsys, monkeypatch):
    from lyric2resolve import cli

    monkeypatch.setattr("lyric2resolve.export.resolve_job.resolve_scripts_dir", lambda *a, **k: tmp_path / "rs")

    song, aca, _ = make_inputs(tmp_path / "in")
    code = cli.main(["--song", str(song), "--acapella", str(tmp_path / "nope.wav"), "--out", str(tmp_path / "o")],
                    engine=FakeEngine(), ffmpeg=copy_ffmpeg())
    assert code == 1 and "acapella file not found" in capsys.readouterr().out

    def broken_render(path, template, preset_name):
        raise RuntimeError("Blender was not found")

    code = cli.main(["--song", str(song), "--acapella", str(aca), "--render-preset", "preview", "--no-analyze",
                     "--formats", "fcpxml", "--out", str(tmp_path / "o2")],
                    engine=FakeEngine(), ffmpeg=copy_ffmpeg(), render=broken_render)
    text = capsys.readouterr().out
    assert code == 3 and "Visuals not rendered" in text and "fcpxml" in text


def test_module_entry_point_help():
    import subprocess

    src = str(Path(__file__).resolve().parents[1] / "src")
    out = subprocess.run([sys.executable, "-m", "lyric2resolve", "--song", "x.wav", "--help"], capture_output=True,
                         text=True, env={"PYTHONPATH": src, "PATH": "", "SYSTEMROOT": __import__("os").environ.get(
                             "SYSTEMROOT", "")}, timeout=60)
    assert out.returncode == 0 and "--acapella" in out.stdout
