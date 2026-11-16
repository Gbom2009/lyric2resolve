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
    assert str(home / ".local" / "bin") in added and env["PATH"].startswith(added[0])
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
