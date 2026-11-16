"""Phase 2: setup logic, settings, verify_local report (all with fakes, no GPU)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from lyric2resolve import paths, setup_tools, verify
from lyric2resolve.settings import AppSettings, load_settings, save_settings

SMI_HEADER = """
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 572.16                 Driver Version: 572.16         CUDA Version: 12.8     |
|-----------------------------------------+------------------------+----------------------+
"""
SMI_QUERY = "NVIDIA GeForce RTX 4070, 572.16, 12282\n"
REPO = paths.code_dir()


@pytest.fixture(autouse=True)
def _data(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.DATA_ENV, str(tmp_path / "data"))


# ------------------------------------------------------------------ GPU / torch index
def test_parse_nvidia_smi():
    gpu = setup_tools.parse_nvidia_smi(SMI_HEADER, SMI_QUERY)
    assert gpu.available and gpu.cuda == (12, 8)
    assert gpu.name == "NVIDIA GeForce RTX 4070" and gpu.memory_mb == 12282 and gpu.driver == "572.16"
    assert "RTX 4070" in gpu.describe()
    assert not setup_tools.parse_nvidia_smi(None, None).available


@pytest.mark.parametrize("cuda,tag", [((13, 0), "cu128"), ((12, 8), "cu128"), ((12, 6), "cu126"),
                                      ((12, 5), "cu124"), ((12, 2), "cu118"), ((11, 4), "cpu")])
def test_torch_index_tag(cuda, tag):
    assert setup_tools.torch_index_tag(setup_tools.GpuInfo(True, cuda=cuda)) == tag


def test_no_gpu_means_cpu_wheels():
    gpu = setup_tools.detect_gpu(lambda cmd: None)
    assert setup_tools.torch_index_url(gpu).endswith("/cpu")


def test_detect_gpu_with_fake_probe():
    def probe(cmd):
        return SMI_QUERY if "--query-gpu=name,driver_version,memory.total" in cmd else SMI_HEADER

    assert setup_tools.detect_gpu(probe).cuda == (12, 8)


# ------------------------------------------------------------------ tools
def test_find_tool_order(tmp_path):
    exe = tmp_path / "my-ffmpeg.exe"
    exe.write_text("x")
    assert setup_tools.find_tool("ffmpeg", str(exe), which=lambda n: "/usr/bin/ffmpeg") == exe
    assert setup_tools.find_tool("ffmpeg", "", which=lambda n: "/usr/bin/ffmpeg") == Path("/usr/bin/ffmpeg")
    assert setup_tools.find_tool("ffmpeg", str(tmp_path / "missing"), which=lambda n: None, platform="linux") is None


def test_find_blender_in_windows_program_files(tmp_path):
    exe = tmp_path / "Blender Foundation" / "Blender 4.2" / "blender.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("x")
    env = {"ProgramFiles": str(tmp_path), "ProgramFiles(x86)": str(tmp_path / "x86")}
    assert setup_tools.find_tool("blender", "", env=env, which=lambda n: None, platform="win32") == exe


# ------------------------------------------------------------------ setup plan
def _plan(mode="full", torch_installed=False, gpu=None):
    gpu = gpu or setup_tools.GpuInfo(True, cuda=(12, 6))
    return setup_tools.plan_setup(REPO, Path("py"), gpu, mode=mode, torch_installed=torch_installed)


def test_full_plan_installs_groups_in_order_with_cuda_index():
    plan = _plan()
    flat = [" ".join(c) for c in plan.commands]
    order = [next(i for i, c in enumerate(flat) if f"{g}.txt" in c) for g in ("core", "torch", "ml", "separation")]
    assert order == sorted(order)
    torch_cmd = flat[order[1]]
    assert "--index-url https://download.pytorch.org/whl/cu126" in torch_cmd
    assert flat[-1].endswith(f"--no-deps -e {REPO}")
    assert order[3] in plan.optional and order[1] not in plan.optional


def test_update_plan_skips_installed_torch():
    plan = _plan(mode="update", torch_installed=True)
    assert not any("torch.txt" in " ".join(c) for c in plan.commands)
    assert any("skipped" in n for n in plan.notes)
    assert any("torch.txt" in " ".join(c) for c in _plan(mode="update", torch_installed=False).commands)


def test_cpu_plan_has_note():
    plan = _plan(gpu=setup_tools.GpuInfo())
    assert any("CPU-only" in n for n in plan.notes)


def test_run_plan_optional_failure_continues_required_failure_stops():
    plan = setup_tools.SetupPlan(commands=[["a"], ["b"], ["c"]], optional=[1])
    ran, log = [], []
    assert setup_tools.run_plan(plan, lambda c: (ran.append(c[0]), 1 if c[0] == "b" else 0)[1], log.append)
    assert ran == ["a", "b", "c"] and any("optional" in m for m in log)
    ran.clear()
    assert not setup_tools.run_plan(plan, lambda c: (ran.append(c[0]), 1 if c[0] == "a" else 0)[1], log.append)
    assert ran == ["a"]


def test_setup_update_script_dry_run():
    out = subprocess.run([sys.executable, str(REPO / "scripts" / "setup_update.py"), "--update", "--dry-run"],
                         capture_output=True, text=True, check=True).stdout
    assert "core.txt" in out and "PyTorch wheels:" in out


def test_requirement_files_exist_and_core_has_no_torch():
    req = REPO / "requirements"
    for name in ("launcher", "core", "torch", "ml", "separation", "dev"):
        assert (req / f"{name}.txt").exists()
    assert "torch" not in (req / "core.txt").read_text()


# ------------------------------------------------------------------ settings
def test_settings_defaults_and_roundtrip(tmp_path):
    s, warnings = load_settings(tmp_path)
    assert s == AppSettings() and warnings == []
    s.default_fps = 29.97
    s.styling_level = "full"
    save_settings(s, tmp_path)
    loaded, warnings = load_settings(tmp_path)
    assert loaded.default_fps == 29.97 and loaded.styling_level == "full" and not warnings


def test_settings_invalid_values_fall_back(tmp_path):
    (tmp_path / "app.json").write_text(json.dumps({
        "schema_version": 1, "default_fps": 26, "styling_level": "fancy", "editor_port": -1,
        "layouts": ["4:3"], "device": "tpu", "future_key": 5}), encoding="utf-8")
    s, warnings = load_settings(tmp_path)
    assert s.default_fps == 25.0 and s.styling_level == "basic" and s.editor_port == 8765
    assert s.layouts == ["16:9", "9:16"] and s.device == "cuda"
    assert len(warnings) == 5
    assert s.extra == {"future_key": 5}
    save_settings(s, tmp_path)
    assert json.loads((tmp_path / "app.json").read_text())["future_key"] == 5  # kept


def test_settings_fps_tolerance_and_migration(tmp_path):
    (tmp_path / "app.json").write_text(json.dumps({"fps": 23.976000001, "resolution": "1080x1920"}))
    s, warnings = load_settings(tmp_path)
    assert s.default_fps == 23.976 and (s.width, s.height) == (1080, 1920) and s.schema_version == 1
    assert not warnings


def test_settings_corrupt_file(tmp_path):
    (tmp_path / "app.json").write_text("{nope")
    s, warnings = load_settings(tmp_path)
    assert s == AppSettings() and warnings


# ------------------------------------------------------------------ verify_local
def test_verify_report_with_fakes(tmp_path):
    ctx = verify.Context(repo=REPO, offline=True, quick=True,
                         probe=lambda cmd: SMI_QUERY if "--query-gpu" in " ".join(cmd) else
                         (SMI_HEADER if cmd[0] == "nvidia-smi" else "git version 2.45"))
    verify.register_pending()
    results = verify.run_checks(ctx)
    by = {r.name: r for r in results}
    assert by["gpu"].status == verify.OK and "cu128" in by["gpu"].detail
    assert by["asset_apis"].status == verify.SKIP
    assert by["whisper_model_load"].status == verify.SKIP  # --quick
    assert by["fcpxml_validity"].status == verify.SKIP  # not implemented yet
    md, js = verify.write_report(results, ctx, tmp_path)
    text = md.read_text(encoding="utf-8")
    assert "| gpu |" in text and "Summary" in text
    data = json.loads(js.read_text(encoding="utf-8"))
    assert {r["name"] for r in data["results"]} >= {"python", "git", "ffmpeg", "gpu", "torch_cuda", "blender"}


def test_verify_crashing_check_becomes_fail(monkeypatch):
    monkeypatch.setattr(verify, "CHECKS", [("boom", lambda ctx: 1 / 0)])
    res = verify.run_checks(verify.Context(repo=REPO))
    assert res[0].status == verify.FAIL and "ZeroDivisionError" in res[0].detail
