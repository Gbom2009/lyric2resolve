"""Mac (Apple Silicon) foundation: chip detection, torch from PyPI (MPS), tool lookups, PATH, defaults."""

import sys
from pathlib import Path

import pytest

from lyric2resolve import paths, setup_tools

REPO = Path(__file__).resolve().parents[1]


def apple_probe(cmd):
    return {"machdep.cpu.brand_string": "Apple M2\n", "hw.memsize": str(8 * 1024 ** 3)}.get(cmd[-1])


def test_detect_apple_silicon():
    gpu = setup_tools.detect_gpu(apple_probe, platform="darwin")
    assert gpu.apple and gpu.available and gpu.name == "Apple M2" and gpu.memory_mb == 8192
    assert gpu.describe() == "Apple M2 GPU (Metal / MPS), 8 GB unified memory"
    intel = setup_tools.detect_gpu(lambda c: "Intel(R) Core(TM) i7" if "brand" in c[-1] else "0", platform="darwin")
    assert not intel.available and not intel.apple


def test_mac_plan_uses_pypi_torch_and_no_cuda_steps(tmp_path):
    gpu = setup_tools.detect_gpu(apple_probe, platform="darwin")
    assert setup_tools.torch_index_tag(gpu) == "pypi" and setup_tools.torch_index_args(gpu) == []
    plan = setup_tools.plan_setup(REPO, Path("py"), gpu, pins=tmp_path / "p.txt", platform="darwin")
    flat = [" ".join(c) for c in plan.commands]
    torch_cmd = next(c for c in flat if "torch.txt" in c)
    assert "--index-url" not in torch_cmd
    assert not any("--ensure-cuda12-libs" in c for c in flat)
    assert not any("CPU-only" in n for n in plan.notes)


def test_torch_health_on_mac_checks_mps():
    gpu = setup_tools.detect_gpu(apple_probe, platform="darwin")
    ok = {"versions": {"torch": "2.11.0", "torchaudio": "2.11.0", "torchvision": "0.26.0"}, "errors": {}, "mps": True}
    assert setup_tools.torch_problems(ok, gpu) == []  # no "+cu" tags on Mac, and that is fine
    bad = dict(ok, mps=False)
    assert any("Apple GPU" in p for p in setup_tools.torch_problems(bad, gpu))


def test_find_tools_in_mac_locations(tmp_path):
    home = tmp_path / "home"
    blender = home / "Applications" / "Blender.app" / "Contents" / "MacOS" / "Blender"
    blender.parent.mkdir(parents=True)
    blender.write_text("x")
    found = setup_tools.find_tool("blender", "", env={"HOME": str(home)}, which=lambda n: None, platform="darwin")
    assert found == blender
    assert Path("/opt/homebrew/bin/ffmpeg") in setup_tools.mac_candidates({}, "ffmpeg")


def test_fix_mac_path_adds_tool_folders(tmp_path):
    home = tmp_path / "home"
    (home / ".local" / "bin").mkdir(parents=True)
    env = {"PATH": "/usr/bin:/bin", "HOME": str(home)}
    added = paths.fix_mac_path(env, platform="darwin")
    assert Path(home / ".local" / "bin") in [Path(a) for a in added] and env["PATH"].startswith(added[0])
    assert paths.fix_mac_path(env, platform="darwin") == []  # idempotent
    assert paths.fix_mac_path({"PATH": "/usr/bin"}, platform="win32") == []


def test_mac_defaults(monkeypatch):
    from lyric2resolve.settings import AppSettings
    from lyric2resolve.updater.config import UpdaterConfig

    monkeypatch.setattr(sys, "platform", "darwin")
    s = AppSettings()
    assert s.whisper_model == "large-v3-turbo" and s.device == "mps" and s.validate() == []
    assert UpdaterConfig().branch == "mac-release"
    assert paths.data_dir({"HOME": "/Users/me"}, "darwin").as_posix().endswith(
        "Library/Application Support/lyric2resolve")
    monkeypatch.setattr(sys, "platform", "win32")
    assert AppSettings().device == "cuda" and UpdaterConfig().branch == "main"


def test_requirements_pick_the_right_packages_per_platform():
    packaging = pytest.importorskip("packaging.requirements")
    mac = {"sys_platform": "darwin", "platform_machine": "arm64"}
    win = {"sys_platform": "win32", "platform_machine": "AMD64"}

    def active(file, env):
        out = []
        for line in (REPO / "requirements" / file).read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            req = packaging.Requirement(line)
            if req.marker is None or req.marker.evaluate(env):
                out.append(str(req.name) + (f"[{','.join(sorted(req.extras))}]" if req.extras else ""))
        return out

    assert "audio-separator[cpu]" in active("separation.txt", mac)
    assert "audio-separator[gpu]" in active("separation.txt", win)
    assert "mlx-whisper" in active("ml.txt", mac) and "mlx-whisper" not in active("ml.txt", win)


def test_claude_found_in_homebrew_folder():
    from lyric2resolve.claude_link import cli

    assert Path("/opt/homebrew/bin/claude") in cli.claude_candidates({"HOME": "/Users/me"})


# ------------------------------------------------------------------ phase 3: MLX Whisper on the M chip
def test_choose_backend():
    from lyric2resolve.transcription import choose_backend

    assert choose_backend("mps", "darwin", has_mlx=True) == "mlx"
    assert choose_backend("mps", "darwin", has_mlx=False) == "faster-whisper"   # CPU fallback
    assert choose_backend("cuda", "win32", has_mlx=True) == "faster-whisper"


class _FakeStable:
    def __init__(self, fail_mlx=False):
        self.loaded, self.fail_mlx, self.calls = [], fail_mlx, []

    def load_mlx_whisper(self, name):
        if self.fail_mlx:
            raise ImportError("No module named 'mlx'")
        self.loaded.append(("mlx", name))
        return self._model()

    def load_faster_whisper(self, name, **kw):
        self.loaded.append(("faster", name, kw.get("device")))
        return self._model()

    def _model(self):
        outer = self

        class M:
            def transcribe(self, audio, **kw):
                outer.calls.append(kw)
                from types import SimpleNamespace

                w = SimpleNamespace(word="hi", start=1.0, end=1.4, probability=0.9)
                return SimpleNamespace(segments=[SimpleNamespace(words=[w])], language="nl")

        return M()


def test_mlx_engine_transcribes_with_its_own_vad_and_frees_memory(monkeypatch, tmp_path):
    from lyric2resolve.transcription import engine

    fake = _FakeStable()
    monkeypatch.setitem(sys.modules, "stable_whisper", fake)
    monkeypatch.delenv("HF_HUB_CACHE", raising=False)
    e = engine.StableTsEngine(engine.EngineOptions(model="large-v3-turbo", backend="mlx", device="mps",
                                                   model_dir=str(tmp_path / "models")))
    t = e.transcribe("x.wav")
    assert fake.loaded == [("mlx", "large-v3-turbo")] and [w.text for w in t.words] == ["hi"]
    kw = fake.calls[0]
    assert kw["vad"] is True and kw["vad_threshold"] == 0.35 and "vad_filter" not in kw
    assert kw["condition_on_previous_text"] is False and kw["word_timestamps"] is True
    assert t.params["engine"] == "stable-ts/mlx" and sys.modules["os"].environ["HF_HUB_CACHE"] == str(tmp_path / "models")
    e.close()
    assert e._model is None


def test_mlx_failure_falls_back_to_cpu(monkeypatch):
    from lyric2resolve.transcription import engine

    fake = _FakeStable(fail_mlx=True)
    monkeypatch.setitem(sys.modules, "stable_whisper", fake)
    e = engine.StableTsEngine(engine.EngineOptions(backend="mlx", device="mps"))
    e.transcribe("x.wav")
    assert fake.loaded == [("faster", "large-v3", "cpu")] and "MLX Whisper could not be used" in e.fallback_reason
    assert "vad_filter" in fake.calls[0]  # now the faster-whisper options


def test_engine_from_settings_on_mac(monkeypatch):
    from lyric2resolve import transcription
    from lyric2resolve.settings import AppSettings

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr("lyric2resolve.settings.load_settings", lambda d=None: (AppSettings(), []))
    monkeypatch.setattr(transcription, "choose_backend", lambda device, platform=None, has_mlx=None: "mlx")
    e = transcription.engine_from_settings()
    assert e.opt.backend == "mlx" and e.opt.model == "large-v3-turbo" and e.opt.device == "cpu"


# ------------------------------------------------------------------ phase 4: rendering on the Mac

def test_pick_encoder_per_platform():
    from lyric2resolve.render import mux

    both = lambda ff, name: True  # noqa: E731
    assert mux.pick_encoder("ffmpeg", "darwin", both) == "h264_videotoolbox"
    assert mux.pick_encoder("ffmpeg", "win32", both) == "h264_nvenc"
    assert mux.pick_encoder("ffmpeg", "darwin", lambda ff, n: False) == "libx264"
    assert mux.pick_encoder("ffmpeg", "linux", lambda ff, n: n == "h264_videotoolbox") == "libx264"


def test_videotoolbox_command_keeps_dj_format():
    from lyric2resolve.render import mux

    s = mux.MuxSettings(fps=30, encoder="h264_videotoolbox")
    cmd = mux.mux_command("ffmpeg", "f_%04d.png", 1, Path("song.wav"), Path("o.mp4"), s)
    i = cmd.index("-c:v")
    assert cmd[i + 1] == "h264_videotoolbox" and cmd[cmd.index("-q:v") + 1] == "65"
    assert "-allow_sw" in cmd and "-crf" not in cmd and "-preset" not in cmd
    for flag in ("-profile:v", "-fps_mode", "-g", "-movflags"):
        assert flag in cmd  # same Rekordbox/Serato-safe stream as NVENC/libx264
    assert mux.vt_quality(0) == 100 and mux.vt_quality(60) == 1


def test_videotoolbox_failure_falls_back_to_libx264(monkeypatch):
    from lyric2resolve.render import mux

    seen = []

    def fake_run(cmd):
        enc = cmd[cmd.index("-c:v") + 1]
        seen.append(enc)
        if enc != "libx264":
            raise RuntimeError("VideoToolbox session failed")

    monkeypatch.setattr(mux, "run", fake_run)
    s = mux.MuxSettings(fps=25, encoder="h264_videotoolbox")
    assert mux.encode("ffmpeg", "f_%04d.png", 1, Path("s.wav"), Path("o.mp4"), s) == "libx264"
    assert seen == ["h264_videotoolbox", "libx264"]


def test_recommended_preset_for_8gb_air():
    from lyric2resolve.editor import visuals_api
    from lyric2resolve.render import presets
    from lyric2resolve.setup_tools import GpuInfo

    air = GpuInfo(True, "Apple M1", "", None, 8192, "apple")
    name, why = presets.recommended(air)
    assert name == "draft" and "8 GB" in why
    assert presets.recommended(GpuInfo(True, "Apple M3 Max", "", None, 36 * 1024, "apple"))[0] == "standard"
    assert presets.recommended(GpuInfo(True, "RTX 4070", "560", (12, 4), 12000))[0] == "standard"
    assert visuals_api.machine_preset(lambda: air)["name"] == "draft"

    def broken():
        raise OSError("no sysctl")

    assert visuals_api.machine_preset(broken)["name"] == "standard"


def test_metal_cpu_fallback_message_on_mac(monkeypatch):
    from lyric2resolve.render import blender

    monkeypatch.setattr(blender.sys, "platform", "darwin")
    dev, msg = blender.choose_device({"backends": {}})
    assert dev == "CPU" and "Metal" in msg and "NVIDIA" not in msg
    assert blender.choose_device({"backends": {"METAL": ["Apple M1"]}})[0] == "METAL"


# ------------------------------------------------------------------ phase 5: Mac integration

def test_install_fonts_on_mac_copies_to_library_fonts(tmp_path, monkeypatch):
    from lyric2resolve.assets import fonts

    monkeypatch.setattr(fonts.sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    root = tmp_path / "fonts"
    (root / "custom").mkdir(parents=True)
    (root / "custom" / "Mine-Bold.otf").write_bytes(b"OTTO-font")
    assert fonts.user_fonts_dir() == tmp_path / "home" / "Library" / "Fonts"
    assert fonts.install_fonts(root, notify=lambda: None) == ["Mine-Bold.otf"]  # no registry on a Mac
    assert (tmp_path / "home" / "Library" / "Fonts" / "Mine-Bold.otf").read_bytes() == b"OTTO-font"
    assert fonts.user_fonts_dir({"LOCALAPPDATA": "C:/L"}, "win32") == Path("C:/L") / "Microsoft" / "Windows" / "Fonts"


def test_font_install_endpoint(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from lyric2resolve import project as proj
    from lyric2resolve.assets import fonts
    from lyric2resolve.editor.app import EditorSession, create_app

    words = proj.make_words([{"text": "hi", "start": 0.5, "end": 1.0}])
    s = EditorSession(proj.save(proj.Project(name="t", words=words, blocks=proj.blocks_by_line(words)),
                                tmp_path / "p" / proj.PROJECT_FILE))
    c = TestClient(create_app(s, fonts_root=tmp_path / "fonts"))
    monkeypatch.setattr(fonts, "install_fonts", lambda root: ["A.ttf", "B.otf"])
    r = c.post("/api/fonts/install")
    assert r.status_code == 200 and r.json()["installed"] == 2 and "Restart DaVinci Resolve" in r.json()["message"]

    def refuse(root):
        raise RuntimeError("only supported on Windows and macOS")

    monkeypatch.setattr(fonts, "install_fonts", refuse)
    assert c.post("/api/fonts/install").status_code == 400


def test_verify_mac_checks(tmp_path, monkeypatch):
    import importlib.util

    from lyric2resolve import setup_tools, verify
    from lyric2resolve.export import resolve_job
    from lyric2resolve.render import mux

    ctx = verify.Context(repo=Path(__file__).resolve().parents[1], quick=True)

    def one(name):
        (res,) = verify.run_checks(ctx, only={name})
        return res

    monkeypatch.setattr(verify.sys, "platform", "linux")
    assert one("mac_whisper_mlx").status == verify.SKIP
    monkeypatch.setattr(verify.sys, "platform", "darwin")
    real_find = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda n, *a: None if n == "mlx_whisper" else real_find(n, *a))
    assert one("mac_whisper_mlx").status == verify.WARN

    monkeypatch.setattr(setup_tools, "find_tool", lambda name, configured="", **kw: Path("/opt/homebrew/bin/ffmpeg"))
    monkeypatch.setattr(mux, "pick_encoder", lambda ff, platform=None, has=None: "h264_videotoolbox")
    r = one("video_encoder")
    assert r.status == verify.OK and "h264_videotoolbox" in r.detail
    monkeypatch.setattr(mux, "pick_encoder", lambda ff, platform=None, has=None: "libx264")
    assert "libx264" in one("video_encoder").detail

    scripts = tmp_path / "Blackmagic Design" / "DaVinci Resolve" / "Fusion" / "Scripts" / "Utility"
    monkeypatch.setattr(resolve_job, "resolve_scripts_dir", lambda env=None, platform=None: scripts)
    assert one("resolve_scripts_folder").status == verify.WARN
    (tmp_path / "Blackmagic Design" / "DaVinci Resolve").mkdir(parents=True)
    assert one("resolve_scripts_folder").status == verify.OK


@pytest.mark.skipif(sys.platform.startswith("win"), reason="process groups are Mac/Linux")
def test_claude_stop_ends_child_processes_too(tmp_path):
    """Stop on a Mac must also end the MCP server that claude started (same process group)."""
    import os
    import time

    from lyric2resolve.claude_link.cli import ClaudeRun

    pidfile = tmp_path / "child.pid"
    script = f"import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); " \
             f"open(r'{pidfile}','w').write(str(p.pid)); time.sleep(60)"
    run = ClaudeRun([sys.executable, "-c", script], "", tmp_path).start()
    for _ in range(100):
        if pidfile.exists() and pidfile.read_text():
            break
        time.sleep(0.05)
    child = int(pidfile.read_text())
    run.cancel()
    assert run.wait(10)
    for _ in range(100):
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            break
        try:  # reap if it became our zombie (it is not our child, so usually not needed)
            os.waitpid(child, os.WNOHANG)
        except ChildProcessError:
            pass
        time.sleep(0.05)
    else:
        pytest.fail("the child process survived Stop")
