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
    args = ap.parse_args(argv)

    gpu = setup_tools.detect_gpu()
    print(f"GPU: {gpu.describe()}")
    print(f"PyTorch wheels: {setup_tools.torch_index_url(gpu)}")
    plan = setup_tools.plan_setup(REPO, Path(sys.executable), gpu,
                                  mode="update" if args.update else "full",
                                  torch_installed=importlib.util.find_spec("torch") is not None)
    if args.dry_run:
        for note in plan.notes:
            print("NOTE:", note)
        for cmd in plan.commands:
            print(" ".join(cmd))
        return 0
    print("Installing dependencies - this can take a while (torch is ~2-3 GB)...")
    ok = setup_tools.run_plan(plan, lambda cmd: subprocess.call(cmd, cwd=str(REPO)))

    settings, _ = load_settings()
    ffmpeg = setup_tools.find_tool("ffmpeg", settings.ffmpeg_path)
    print(f"ffmpeg: {ffmpeg or 'NOT FOUND'}")
    if not ffmpeg:
        print(setup_tools.FFMPEG_HELP)
    print("Done." if ok else "Setup FAILED - see the messages above.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
