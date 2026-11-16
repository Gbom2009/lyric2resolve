"""Install/update the app's Python dependencies into the current interpreter (the .venv).

    python scripts/setup_update.py --full     first full setup (setup_windows.bat calls this)
    python scripts/setup_update.py --update   called by the launcher's updater when requirements changed
    add --dry-run to only print the plan

Stdlib only. Picks the PyTorch CUDA wheel index that matches your NVIDIA driver.
"""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from lyric2resolve import setup_tools  # noqa: E402
from lyric2resolve.settings import load_settings  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--full", action="store_true")
    mode.add_argument("--update", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--write-pins", type=Path, help=argparse.SUPPRESS)  # internal plan step
    ap.add_argument("--ensure-cuda12-libs", nargs="?", const="", default=None, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    if args.ensure_cuda12_libs is not None:  # internal plan step (Windows + NVIDIA)
        import site

        if not sys.platform.startswith("win"):
            print("cuBLAS 12 step: only needed on Windows - skipped.")
            return 0

        sites = [p for p in site.getsitepackages() + sys.path if p and p.lower().endswith("site-packages")]
        if setup_tools.has_cublas12(sites):
            print("cuBLAS 12 for Whisper: already available (from torch).")
            return 0
        print("Installing cuBLAS 12 for Whisper (the CUDA 13 PyTorch build does not include it, ~500 MB)...")
        cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", setup_tools.CUBLAS12_PACKAGE]
        if args.ensure_cuda12_libs:
            cmd += ["-c", args.ensure_cuda12_libs]
        return subprocess.call(cmd, cwd=str(REPO))

    if args.write_pins:  # runs in a fresh process after the torch step, so it sees the new versions
        info = setup_tools.probe_torch(Path(sys.executable))
        args.write_pins.parent.mkdir(parents=True, exist_ok=True)
        args.write_pins.write_text(setup_tools.torch_pins(info.get("versions") or {}), encoding="utf-8")
        print("PyTorch versions pinned for the next steps: " + ", ".join(
            f"{k} {v}" for k, v in (info.get("versions") or {}).items()))
        return 0

    from lyric2resolve import paths

    gpu = setup_tools.detect_gpu()
    print(f"GPU: {gpu.describe()}")
    print(f"PyTorch wheels: {setup_tools.torch_index_url(gpu)}")
    installed = importlib.util.find_spec("torch") is not None
    broken: list[str] = []
    if installed:
        print("Checking the installed PyTorch (torch / torchaudio / torchvision)...")
        broken = setup_tools.torch_problems(setup_tools.probe_torch(Path(sys.executable)), gpu)
        for b in broken:
            print(f"  problem: {b}")
    plan = setup_tools.plan_setup(REPO, Path(sys.executable), gpu,
                                  mode="update" if args.update else "full",
                                  torch_installed=installed, torch_broken=broken,
                                  pins=paths.ensure_data_dir() / "cache" / "torch-pins.txt")
    if args.dry_run:
        for note in plan.notes:
            print("NOTE:", note)
        for cmd in plan.commands:
            print(" ".join(cmd))
        return 0
    print("Installing dependencies - this can take a while (torch is ~2-3 GB)...")
    ok = setup_tools.run_plan(plan, lambda cmd: subprocess.call(cmd, cwd=str(REPO)))
    if ok:
        info = setup_tools.probe_torch(Path(sys.executable))
        problems = setup_tools.torch_problems(info, gpu)
        if problems:
            ok = False
            print("PyTorch is still not OK: " + "; ".join(problems))
            print("Copy these messages into the Claude session.")
        elif info.get("versions"):
            print("PyTorch OK: " + ", ".join(f"{k} {v}" for k, v in info["versions"].items())
                  + (", CUDA available" if info.get("cuda") else ", CPU only"))

    settings, _ = load_settings()
    ffmpeg = setup_tools.find_tool("ffmpeg", settings.ffmpeg_path)
    print(f"ffmpeg: {ffmpeg or 'NOT FOUND'}")
    if not ffmpeg:
        print(setup_tools.FFMPEG_HELP)
    print("Done." if ok else "Setup FAILED - see the messages above.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
