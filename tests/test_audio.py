"""Phase 3: conversion, A/B offset detection, instrumental, separation fallback (mocked)."""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest

from lyric2resolve.audio import PreparedAudio, prepare_inputs
from lyric2resolve.audio import align, stems, wavio
from lyric2resolve.audio.convert import AudioError, Ffmpeg, cached_wav

SR = 44100
RNG = np.random.default_rng(1234)


def vocal_like(seconds: float, sr: int = SR) -> np.ndarray:
    """Bursts of band-limited noise with pitch-like harmonics: 'sung phrases' separated by gaps."""
    from scipy.signal import butter, lfilter

    n = int(seconds * sr)
    t = np.arange(n) / sr
    b, a = butter(4, [200 / (sr / 2), 3000 / (sr / 2)], btype="band")
    noise = lfilter(b, a, RNG.standard_normal(n))
    f0 = 220 * (1 + 0.3 * np.sin(2 * np.pi * 0.37 * t))
    tone = sum(np.sin(2 * np.pi * k * np.cumsum(f0) / sr) / k for k in (1, 2, 3))
    env = (np.sin(2 * np.pi * 0.25 * t) > -0.2).astype(float)  # phrases + pauses
    x = (0.3 * noise / np.abs(noise).max() + 0.2 * tone) * env
    return np.stack([x, 0.9 * x], axis=1).astype(np.float32)


def instrumental_like(seconds: float, sr: int = SR) -> np.ndarray:
    n = int(seconds * sr)
    t = np.arange(n) / sr
    kick = np.sin(2 * np.pi * 55 * t) * (np.mod(t, 0.5) < 0.08)
    pad = 0.2 * (np.sin(2 * np.pi * 110 * t) + np.sin(2 * np.pi * 164.8 * t))
    hats = 0.05 * RNG.standard_normal(n) * (np.mod(t, 0.25) < 0.02)
    x = 0.4 * kick + pad + hats
    return np.stack([x, x], axis=1).astype(np.float32)


def delayed(x: np.ndarray, ms: float, sr: int = SR) -> np.ndarray:
    return align.compensate(x, sr, -ms, length=len(x) + int(abs(ms) / 1000 * sr))


# ------------------------------------------------------------------ offset
@pytest.mark.parametrize("ms", [0.0, 12.5, 250.0, 1873.3, -40.0, -731.7])
def test_offset_detection(ms):
    v = vocal_like(20)
    song = v + instrumental_like(20)
    aca = delayed(v, ms) if ms >= 0 else v[int(-ms / 1000 * SR):]
    res = align.estimate_offset(song, aca, SR)
    assert abs(res.offset_ms - ms) < 0.5, res
    assert res.reliable


def test_offset_messages_and_thresholds():
    assert "aligned" in align.OffsetResult(1.0, 0.8, 1e4).message()
    assert "later" in align.OffsetResult(40.0, 0.8, 1e4).message()
    assert "earlier" in align.OffsetResult(-40.0, 0.8, 1e4).message()
    assert "reliably" in align.OffsetResult(40.0, 0.05, 1e4).message()


def test_unrelated_acapella_is_unreliable():
    song = vocal_like(15) + instrumental_like(15)
    other = np.stack([RNG.standard_normal(15 * SR)] * 2, axis=1).astype(np.float32) * 0.1
    assert not align.estimate_offset(song, other, SR).reliable


def test_silent_acapella():
    res = align.estimate_offset(instrumental_like(5), np.zeros((5 * SR, 2), np.float32), SR)
    assert res.confidence == 0.0 and not res.reliable


def test_compensate_round_trip():
    v = vocal_like(5)
    late = delayed(v, 100.0)
    fixed = align.compensate(late, SR, 100.0, length=len(v))
    assert fixed.shape == v.shape and np.allclose(fixed, v, atol=1e-6)
    early = align.compensate(v, SR, -100.0, length=len(v))
    assert np.allclose(early[: int(0.1 * SR)], 0) and np.allclose(early[int(0.1 * SR):], v[: len(v) - int(0.1 * SR)])


# ------------------------------------------------------------------ instrumental
def test_subtract_vocals_recovers_instrumental():
    v, inst = vocal_like(10), instrumental_like(10)
    res = stems.subtract_vocals(v + inst, v * 0.5)  # acapella exported at half level
    assert np.allclose(res.gain, [2.0, 2.0], atol=1e-3)
    assert np.max(np.abs(res.instrumental - inst)) < 1e-3
    assert res.residual_ratio < 1.0


def test_subtract_keeps_song_tail_and_handles_mono_acapella():
    v, inst = vocal_like(4), instrumental_like(6)
    song = inst.copy()
    song[: len(v)] += v
    res = stems.subtract_vocals(song, v.mean(axis=1, keepdims=True))
    assert len(res.instrumental) == len(song)


# ------------------------------------------------------------------ ffmpeg wrapper
def test_ffmpeg_command_and_errors(tmp_path):
    src = tmp_path / "a.mp3"
    src.write_bytes(b"x")
    cmd = Ffmpeg("ffmpeg").wav_command(src, tmp_path / "o.wav")
    assert cmd[cmd.index("-ar") + 1] == "44100" and cmd[cmd.index("-ac") + 1] == "2" and "pcm_s16le" in cmd
    with pytest.raises(AudioError, match="not found"):
        Ffmpeg().to_wav(tmp_path / "missing.wav", tmp_path / "o.wav")
    (tmp_path / "a.txt").write_text("x")
    with pytest.raises(AudioError, match="Unsupported"):
        Ffmpeg().to_wav(tmp_path / "a.txt", tmp_path / "o.wav")
    with pytest.raises(AudioError, match="could not convert"):
        Ffmpeg(runner=lambda c: (1, "Invalid data found")).to_wav(src, tmp_path / "o.wav")


def test_cached_wav_converts_once(tmp_path):
    src = tmp_path / "song.flac"
    src.write_bytes(b"flacdata")
    calls = []

    def runner(cmd):
        calls.append(cmd)
        Path(cmd[-1]).write_bytes(b"RIFF")
        return 0, ""

    ff = Ffmpeg(runner=runner)
    a = cached_wav(src, tmp_path / "cache", ff)
    b = cached_wav(src, tmp_path / "cache", ff)
    assert a == b and a.exists() and len(calls) == 1
    src.write_bytes(b"other content")
    assert cached_wav(src, tmp_path / "cache", ff) != a  # content hash changes the key


# ------------------------------------------------------------------ separation fallback
class FakeSeparator:
    def __init__(self, name="fake", fail=False):
        self.name, self.fail, self.calls = name, fail, 0

    def separate(self, song_wav, out_dir):
        self.calls += 1
        if self.fail:
            raise RuntimeError("no model")
        out_dir.mkdir(parents=True, exist_ok=True)
        v, i = out_dir / "song_(Vocals).wav", out_dir / "song_(Instrumental).wav"
        v.write_bytes(b"v")
        i.write_bytes(b"i")
        return v, i


def test_separate_cached_fallback_and_cache(tmp_path):
    bad, good = FakeSeparator("bad", fail=True), FakeSeparator("good")
    v, i, name = stems.separate_cached(tmp_path / "s.wav", "abc", tmp_path, [bad, good])
    assert name == "good" and v.name.endswith("(Vocals).wav") and i.exists()
    again = stems.separate_cached(tmp_path / "s.wav", "abc", tmp_path, [bad, good])
    assert again == (v, i, "good") and good.calls == 1
    with pytest.raises(RuntimeError, match="no model"):
        stems.separate_cached(tmp_path / "s.wav", "zzz", tmp_path, [FakeSeparator("x", fail=True)])


def test_pick_stems_names():
    files = [Path("x_(Instrumental)_model.wav"), Path("x_(Vocals)_model.wav")]
    assert stems.pick_stems(files) == (files[1], files[0])
    demucs = [Path("htdemucs_ft/x/no_vocals.wav"), Path("htdemucs_ft/x/vocals.wav")]
    assert stems.pick_stems(demucs) == (demucs[1], demucs[0])


# ------------------------------------------------------------------ full prepare (real ffmpeg when present)
needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


@needs_ffmpeg
def test_prepare_inputs_end_to_end(tmp_path):
    v, inst = vocal_like(12), instrumental_like(12)
    song_p = wavio.write(tmp_path / "in" / "song.wav", (v + inst) * 0.5, SR)
    aca_p = wavio.write(tmp_path / "in" / "aca.wav", delayed(v, 80.0) * 0.5, SR)
    res = prepare_inputs(song_p, aca_p, tmp_path / "cache", Ffmpeg(shutil.which("ffmpeg")), auto_compensate=True)
    assert isinstance(res, PreparedAudio)
    assert abs(res.offset_ms - 80.0) < 1.0 and res.compensated
    assert any("later" in m for m in res.messages)
    inst_out, sr = wavio.read(Path(res.instrumental_wav))
    assert sr == SR and abs(len(inst_out) - len(inst)) <= 1
    # instrumental should be much closer to the true instrumental than the song is (16-bit rounding)
    err = np.mean((inst_out[: len(inst)] - inst * 0.5) ** 2)
    assert err < 0.05 * np.mean((v * 0.5) ** 2)


@needs_ffmpeg
def test_prepare_inputs_without_acapella_uses_separator(tmp_path):
    song_p = wavio.write(tmp_path / "song.wav", instrumental_like(2), SR)
    res = prepare_inputs(song_p, None, tmp_path / "cache", Ffmpeg(shutil.which("ffmpeg")),
                         separators=[FakeSeparator("fake")])
    assert res.vocals_source == "separation:fake" and Path(res.vocals_wav).exists()


def test_cli_audio_check_reports_missing_ffmpeg(monkeypatch, capsys, tmp_path):
    from lyric2resolve import __main__ as cli
    from lyric2resolve import setup_tools

    monkeypatch.setattr(setup_tools, "find_tool", lambda *a, **k: None)
    monkeypatch.setenv("LYRIC2RESOLVE_DATA", str(tmp_path))
    assert cli.main(["audio-check", "--song", "x.wav"]) == 1
    assert "ffmpeg not found" in capsys.readouterr().out


def test_demucs_backend_skips_cleanly_when_not_installed(tmp_path, monkeypatch):
    """Fixes from testing (4): Demucs is not installable next to current torch; no confusing subprocess error."""
    import importlib.util

    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda n, *a: None if n == "demucs" else real(n, *a))
    with pytest.raises(RuntimeError, match="not installed"):
        stems.DemucsBackend().separate(tmp_path / "s.wav", tmp_path / "out")
    with pytest.raises(RuntimeError, match="upload the acapella"):
        stems.separate_cached(tmp_path / "s.wav", "q", tmp_path, [stems.DemucsBackend()])


def test_separation_requirements_include_audioread():
    from pathlib import Path

    req = (Path(__file__).resolve().parents[1] / "requirements" / "separation.txt").read_text()
    assert "audioread" in req  # audio-separator imports it without declaring it (librosa 1.0 dropped it)


def test_audio_separator_imports_when_installed():
    """If audio-separator is installed, its import must work (it failed with 'No module named audioread')."""
    import importlib.util

    if importlib.util.find_spec("audio_separator") is None:
        pytest.skip("audio-separator not installed (PC only)")
    from audio_separator.separator import Separator  # noqa: F401
