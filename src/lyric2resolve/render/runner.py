"""Headless Blender rendering: build .blend, estimate from test frames, render with progress, cancel, resume.

Process creation is injectable so everything is tested with a fake 'blender' (a Python script that prints
Blender-like output and writes PNG files).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import blender as bl

SAVED = re.compile(r"Saved: '(.+?)'")
FRAME = re.compile(r"Fra:(\d+)")
LONG_RENDER_WARN_S = 3 * 3600


@dataclass
class Progress:
    done: int
    total: int
    frame: int | None
    elapsed_s: float
    eta_s: float | None
    message: str = ""

    @property
    def fraction(self) -> float:
        return self.done / self.total if self.total else 0.0


@dataclass
class Estimate:
    frames: int
    seconds_per_frame: float
    bytes_per_frame: int
    total_seconds: float
    total_bytes: int
    warning: str = ""

    def summary(self) -> str:
        h, m = divmod(int(self.total_seconds) // 60, 60)
        gb = self.total_bytes / 1e9
        return (f"{self.frames} frames x {self.seconds_per_frame:.1f} s = about {h} h {m:02d} min, "
                f"about {gb:.1f} GB of PNG frames" + (f"\n{self.warning}" if self.warning else ""))


@dataclass
class RenderResult:
    ok: bool
    cancelled: bool = False
    frames_dir: str = ""
    rendered: int = 0
    skipped: int = 0
    log_tail: list[str] = field(default_factory=list)
    error: str = ""


def frame_files(out_dir: Path) -> dict[int, Path]:
    found = {}
    for f in out_dir.glob("frame_*.png"):
        m = re.search(r"(\d+)\.png$", f.name)
        if m and f.stat().st_size > 0:
            found[int(m.group(1))] = f
    return found


def missing_frames(out_dir: Path, start: int, end: int) -> list[int]:
    have = frame_files(out_dir)
    return [f for f in range(start, end + 1) if f not in have]


def frame_ranges(frames: list[int]) -> list[tuple[int, int]]:
    """[1,2,3,7,8] -> [(1,3),(7,8)] so resumed renders only ask Blender for missing runs."""
    out: list[tuple[int, int]] = []
    for f in sorted(frames):
        if out and f == out[-1][1] + 1:
            out[-1] = (out[-1][0], f)
        else:
            out.append((f, f))
    return out


class BlenderRunner:
    def __init__(self, blender: Path, popen: Callable = subprocess.Popen, clock: Callable[[], float] = time.monotonic,
                 prefix: list[str] | None = None):
        """prefix: replaces the executable (tests run a fake Blender as [python, fake_blender.py])."""
        self.blender, self.popen, self.clock = Path(blender), popen, clock
        self.prefix = prefix

    # -------------------------------------------------------------- process helper
    def _run(self, cmd: list[str], on_line: Callable[[str], None] | None = None,
             cancel: threading.Event | None = None) -> tuple[int, list[str], bool]:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform.startswith("win") else 0
        if self.prefix:
            cmd = self.prefix + cmd[1:]
        proc = self.popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                          errors="replace", bufsize=1, creationflags=flags)
        tail: list[str] = []
        cancelled = False
        for line in proc.stdout:
            line = line.rstrip()
            tail = (tail + [line])[-40:]
            if on_line:
                on_line(line)
            if cancel is not None and cancel.is_set():
                cancelled = True
                proc.terminate()
                break
        try:
            code = proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            code = -9
        return code, tail, cancelled

    # -------------------------------------------------------------- steps
    def version(self) -> tuple[int, int, int] | None:
        code, tail, _ = self._run([str(self.blender), "--version"])
        return bl.parse_version("\n".join(tail)) if code == 0 else None

    def detect_gpu(self, tmp: Path) -> tuple[str, str]:
        probe = tmp / "l2r_gpu_probe.py"
        probe.write_text(bl.GPU_PROBE, encoding="utf-8")
        code, tail, _ = self._run([str(self.blender), "-b", "--factory-startup", "-noaudio", "-P", str(probe)])
        return bl.choose_device(bl.parse_gpu_probe("\n".join(tail)))

    def build(self, scene_script: Path, scene_data: Path, log: Callable[[str], None] = lambda s: None) -> list[Path]:
        code, tail, _ = self._run(bl.build_command(self.blender, scene_script, scene_data), log)
        data = json.loads(scene_data.read_text(encoding="utf-8"))
        blends = [scene_data.parent / f"{data['name']}_{a.replace(':', 'x')}.blend" for a in data["aspects"]]
        missing = [b for b in blends if not b.exists()]
        if code != 0 or missing:
            raise RuntimeError("Building the Blender scene failed:\n" + "\n".join(tail[-15:]))
        return blends

    def write_job(self, folder: Path, job: dict) -> tuple[Path, Path]:
        folder.mkdir(parents=True, exist_ok=True)
        setup = folder / "l2r_render_setup.py"
        setup.write_text(bl.RENDER_SETUP, encoding="utf-8")
        job_path = folder / "l2r_render_job.json"
        job_path.write_text(json.dumps(job, indent=1), encoding="utf-8")
        return setup, job_path

    def render(self, blend: Path, job: dict, start: int, end: int,
               on_progress: Callable[[Progress], None] = lambda p: None,
               cancel: threading.Event | None = None) -> RenderResult:
        out_dir = Path(job["output"]).parent
        out_dir.mkdir(parents=True, exist_ok=True)
        total = end - start + 1
        todo = missing_frames(out_dir, start, end)
        skipped = total - len(todo)
        setup, job_path = self.write_job(out_dir.parent, job)
        t0 = self.clock()
        state = {"done": skipped, "rendered": 0, "frame": None}

        def on_line(line: str) -> None:
            m = FRAME.search(line)
            if m:
                state["frame"] = int(m.group(1))
            if SAVED.search(line):
                state["done"] += 1
                state["rendered"] += 1
                el = self.clock() - t0
                per = el / state["rendered"]
                on_progress(Progress(state["done"], total, state["frame"], el, per * (total - state["done"])))

        on_progress(Progress(skipped, total, None, 0.0, None, f"{skipped} frames already rendered (resume)"
                             if skipped else "starting"))
        tail: list[str] = []
        for a, b in frame_ranges(todo):
            code, tail, cancelled = self._run(bl.render_command(self.blender, blend, setup, job_path, a, b), on_line,
                                              cancel)
            if cancelled:
                return RenderResult(False, True, str(out_dir), state["rendered"], skipped, tail)
            if code != 0:
                return RenderResult(False, False, str(out_dir), state["rendered"], skipped, tail,
                                    "Blender stopped with an error:\n" + "\n".join(tail[-12:]))
        still = missing_frames(out_dir, start, end)
        if still:
            return RenderResult(False, False, str(out_dir), state["rendered"], skipped, tail,
                                f"{len(still)} frames are missing after rendering (first: {still[0]})")
        return RenderResult(True, False, str(out_dir), state["rendered"], skipped, tail)

    def estimate(self, blend: Path, job: dict, start: int, end: int, test_frames: int = 3) -> Estimate:
        """Render a few frames from the middle into a scratch folder and extrapolate time and disk use."""
        mid = start + (end - start) // 2
        a, b = mid, min(end, mid + test_frames - 1)
        scratch = Path(job["output"]).parent.parent.parent / "_estimate"   # next to frames/, never inside it
        shutil.rmtree(scratch, ignore_errors=True)
        est_job = dict(job, output=str(scratch / "frame_"))
        t0 = self.clock()
        res = self.render(blend, est_job, a, b)
        took = self.clock() - t0
        n = b - a + 1
        if not res.ok:
            raise RuntimeError(res.error or "test render failed")
        files = list(frame_files(scratch).values())
        per = took / max(1, n)
        size = int(sum(f.stat().st_size for f in files) / max(1, len(files)))
        shutil.rmtree(scratch, ignore_errors=True)
        frames = end - start + 1
        total = per * frames
        warn = (f"WARNING: this render takes more than {LONG_RENDER_WARN_S // 3600} hours. Time savers: use DRAFT/"
                "STANDARD, render selected sections only, render at 30 fps, or render 1080p and upscale in Resolve."
                if total > LONG_RENDER_WARN_S else "")
        return Estimate(frames, per, size, total, size * frames, warn)
