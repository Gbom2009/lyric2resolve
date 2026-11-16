"""Setup logic (stdlib only: runs before the heavy dependencies exist).

Detects the NVIDIA driver/CUDA version, picks the matching PyTorch wheel index,
finds ffmpeg/Blender, and builds the pip commands for each requirement group.
Command execution is injected so everything is unit-testable without a GPU.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

TORCH_INDEX = "https://download.pytorch.org/whl/{tag}"
# (minimum driver CUDA version, wheel tag) newest first. Verify against pytorch.org when bumping torch.
CUDA_TAGS = ((12, 8, "cu128"), (12, 6, "cu126"), (12, 4, "cu124"), (11, 8, "cu118"))

GROUPS_FULL = ("core", "torch", "ml", "separation")
GROUPS_CI = ("core",)

Probe = Callable[[list[str]], str | None]  # runs a command, returns stdout or None


def run_probe(cmd: list[str], timeout: float = 15) -> str | None:
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform.startswith("win") else 0
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              encoding="utf-8", errors="replace", creationflags=flags)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout if proc.returncode == 0 else None


# ------------------------------------------------------------------ GPU
@dataclass
class GpuInfo:
    available: bool = False
    name: str = ""
    driver: str = ""
    cuda: tuple[int, int] | None = None
    memory_mb: int = 0

    def describe(self) -> str:
        if not self.available:
            return "No NVIDIA GPU detected (nvidia-smi not found or failed)"
        cuda = f"{self.cuda[0]}.{self.cuda[1]}" if self.cuda else "?"
        return f"{self.name} ({self.memory_mb} MB), driver {self.driver}, CUDA {cuda}"


def parse_nvidia_smi(header: str | None, query: str | None) -> GpuInfo:
    """header = plain `nvidia-smi` output (has 'CUDA Version: X.Y');
    query = `nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader,nounits`."""
    if not header and not query:
        return GpuInfo()
    info = GpuInfo(available=True)
    m = re.search(r"CUDA Version:\s*(\d+)\.(\d+)", header or "")
    if m:
        info.cuda = (int(m.group(1)), int(m.group(2)))
    first = (query or "").strip().splitlines()[0] if (query or "").strip() else ""
    parts = [p.strip() for p in first.split(",")]
    if len(parts) >= 3:
        info.name, info.driver = parts[0], parts[1]
        try:
            info.memory_mb = int(float(parts[2]))
        except ValueError:
            pass
    return info


def detect_gpu(probe: Probe = run_probe) -> GpuInfo:
    header = probe(["nvidia-smi"])
    query = probe(["nvidia-smi", "--query-gpu=name,driver_version,memory.total",
                   "--format=csv,noheader,nounits"])
    return parse_nvidia_smi(header, query)


def torch_index_tag(gpu: GpuInfo) -> str:
    if not gpu.available or not gpu.cuda:
        return "cpu"
    for major, minor, tag in CUDA_TAGS:
        if gpu.cuda >= (major, minor):
            return tag
    return "cpu"


def torch_index_url(gpu: GpuInfo) -> str:
    return TORCH_INDEX.format(tag=torch_index_tag(gpu))


# ------------------------------------------------------------------ tools
def windows_candidates(env: dict[str, str], tool: str) -> list[Path]:
    pf = [env.get("ProgramFiles", r"C:\Program Files"), env.get("ProgramFiles(x86)", r"C:\Program Files (x86)")]
    local = env.get("LOCALAPPDATA", "")
    out: list[Path] = []
    if tool == "ffmpeg":
        for base in pf + [r"C:"]:
            out.append(Path(base) / "ffmpeg" / "bin" / "ffmpeg.exe")
        if local:
            out.append(Path(local) / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe")
    elif tool == "blender":
        for base in pf:
            found = sorted(Path(base, "Blender Foundation").glob("Blender*/blender.exe"), reverse=True) \
                if Path(base, "Blender Foundation").exists() else []
            out.extend(found)
        steam = Path(pf[1]) / "Steam" / "steamapps" / "common" / "Blender" / "blender.exe"
        out.append(steam)
    return out


def find_tool(tool: str, configured: str = "", env: dict[str, str] | None = None,
              which: Callable[[str], str | None] = shutil.which, platform: str | None = None) -> Path | None:
    """Configured path > PATH > common install folders (Windows)."""
    env = os.environ if env is None else env
    platform = platform or sys.platform
    if configured:
        p = Path(configured).expanduser()
        if p.is_file():
            return p
    hit = which(tool)
    if hit:
        return Path(hit)
    if platform.startswith("win"):
        for cand in windows_candidates(env, tool):
            if cand.is_file():
                return cand
    return None


def tool_version(path: Path | None, probe: Probe = run_probe) -> str:
    if not path:
        return ""
    out = probe([str(path), "-version" if path.stem.lower().startswith("ffmpeg") else "--version"]) or ""
    return out.strip().splitlines()[0] if out.strip() else ""


FFMPEG_HELP = ("ffmpeg not found. Install it with:  winget install Gyan.FFmpeg   (then reopen the launcher),\n"
               "or download from https://www.gyan.dev/ffmpeg/builds/ and set the path in settings.")
BLENDER_HELP = ("Blender not found. Install Blender 4.x from https://www.blender.org/download/ "
                "(or: winget install BlenderFoundation.Blender) and set the path in settings if needed.")


# ------------------------------------------------------------------ pip plans
OPTIONAL_GROUPS = ("separation",)  # failure only warns: the app works without it


@dataclass
class SetupPlan:
    commands: list[list[str]] = field(default_factory=list)
    optional: list[int] = field(default_factory=list)  # indices of commands allowed to fail
    notes: list[str] = field(default_factory=list)


def plan_setup(repo: Path, python: Path, gpu: GpuInfo, mode: str = "full",
               torch_installed: bool = False, groups: tuple[str, ...] = GROUPS_FULL) -> SetupPlan:
    """mode 'full' installs everything; 'update' skips torch when it is already installed."""
    pip = [str(python), "-m", "pip", "install", "--disable-pip-version-check"]
    req = repo / "requirements"
    plan = SetupPlan()
    plan.commands.append([str(python), "-m", "pip", "install", "--disable-pip-version-check", "-q",
                          "--upgrade", "pip", "setuptools", "wheel"])
    for group in groups:
        path = req / f"{group}.txt"
        if not path.exists():
            continue
        if group == "torch":
            if mode == "update" and torch_installed:
                plan.notes.append("torch already installed - skipped (run setup_windows.bat to reinstall).")
                continue
            tag = torch_index_tag(gpu)
            if tag == "cpu":
                plan.notes.append("No NVIDIA GPU/CUDA detected: installing CPU-only torch (transcription will be slow).")
            plan.commands.append(pip + ["-r", str(path), "--index-url", TORCH_INDEX.format(tag=tag)])
        else:
            if group in OPTIONAL_GROUPS:
                plan.optional.append(len(plan.commands))
            plan.commands.append(pip + ["-r", str(path)])
    plan.commands.append(pip + ["--no-deps", "-e", str(repo)])
    return plan


def run_plan(plan: SetupPlan, runner: Callable[[list[str]], int], log: Callable[[str], None] = print) -> bool:
    """Run the plan; required failures stop it (False), optional ones only warn."""
    for note in plan.notes:
        log(f"NOTE: {note}")
    total = len(plan.commands)
    for i, cmd in enumerate(plan.commands):
        shown = " ".join(cmd[1:]) if len(cmd) > 1 else cmd[0]
        log(f"[{i + 1}/{total}] {shown}")
        code = runner(cmd)
        if code != 0:
            if i in plan.optional:
                log(f"WARNING: optional step failed (exit {code}); continuing. The app works without it.")
                continue
            log(f"ERROR: step failed (exit {code}).")
            return False
    return True
