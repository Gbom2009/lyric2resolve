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
# cu128 stops at torch 2.11 (checked 2026-11-16); drivers with CUDA 13 get cu130 (newer torch, RTX 50 support).
CUDA_TAGS = ((13, 0, "cu130"), (12, 8, "cu128"), (12, 6, "cu126"), (12, 4, "cu124"), (11, 8, "cu118"))

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
    kind: str = "nvidia"          # nvidia | apple (Apple Silicon: Metal / MPS, unified memory)

    @property
    def apple(self) -> bool:
        return self.kind == "apple"

    def describe(self) -> str:
        if self.apple:
            return f"{self.name} GPU (Metal / MPS), {self.memory_mb // 1024} GB unified memory"
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


def detect_apple_silicon(probe: Probe = run_probe) -> GpuInfo:
    """macOS: 'Apple M1/M2/…' from sysctl; Intel Macs have no MPS-capable GPU for our purposes."""
    brand = (probe(["sysctl", "-n", "machdep.cpu.brand_string"]) or "").strip()
    mem = (probe(["sysctl", "-n", "hw.memsize"]) or "0").strip()
    if not brand.startswith("Apple"):
        return GpuInfo()
    try:
        mb = int(mem) // (1024 * 1024)
    except ValueError:
        mb = 0
    return GpuInfo(True, brand, "", None, mb, "apple")


def detect_gpu(probe: Probe = run_probe, platform: str | None = None) -> GpuInfo:
    if (platform or sys.platform) == "darwin":
        return detect_apple_silicon(probe)
    header = probe(["nvidia-smi"])
    query = probe(["nvidia-smi", "--query-gpu=name,driver_version,memory.total",
                   "--format=csv,noheader,nounits"])
    return parse_nvidia_smi(header, query)


def torch_index_tag(gpu: GpuInfo) -> str:
    if gpu.apple:
        return "pypi"  # macOS arm64 wheels on PyPI include Metal (MPS) support
    if not gpu.available or not gpu.cuda:
        return "cpu"
    for major, minor, tag in CUDA_TAGS:
        if gpu.cuda >= (major, minor):
            return tag
    return "cpu"


def torch_index_url(gpu: GpuInfo) -> str:
    tag = torch_index_tag(gpu)
    return "https://pypi.org/simple" if tag == "pypi" else TORCH_INDEX.format(tag=tag)


def torch_index_args(gpu: GpuInfo) -> list[str]:
    tag = torch_index_tag(gpu)
    return [] if tag == "pypi" else ["--index-url", TORCH_INDEX.format(tag=tag)]


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


MAC_BIN_DIRS = ("/opt/homebrew/bin", "/usr/local/bin")   # Homebrew on Apple Silicon / Intel


def mac_candidates(env: dict[str, str], tool: str) -> list[Path]:
    home = Path(env.get("HOME") or str(Path.home()))
    if tool == "blender":
        return [Path("/Applications/Blender.app/Contents/MacOS/Blender"),
                home / "Applications" / "Blender.app" / "Contents" / "MacOS" / "Blender"]
    return [Path(d) / tool for d in MAC_BIN_DIRS]


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
    if platform == "darwin":
        for cand in mac_candidates(env, tool):
            if cand.is_file():
                return cand
    return None


def tool_version(path: Path | None, probe: Probe = run_probe) -> str:
    if not path:
        return ""
    out = probe([str(path), "-version" if path.stem.lower().startswith("ffmpeg") else "--version"]) or ""
    return out.strip().splitlines()[0] if out.strip() else ""


FFMPEG_HELP = ("ffmpeg not found. Install it with:  winget install Gyan.FFmpeg   (then reopen the launcher),\n"
               "or download from https://www.gyan.dev/ffmpeg/builds/ and set the path in settings.\n"
               "Mac: install Homebrew (https://brew.sh), then in Terminal: brew install ffmpeg")
BLENDER_HELP = ("Blender not found. Install Blender 4.x from https://www.blender.org/download/ "
                "(Windows: winget install BlenderFoundation.Blender; Mac: drag Blender into Applications) and set the "
                "path in settings if needed.")


# ------------------------------------------------------------------ pip plans
OPTIONAL_GROUPS = ("separation",)  # failure only warns: the app works without it


# ------------------------------------------------------------------ torch health
TORCH_PACKAGES = ("torch", "torchaudio", "torchvision")
# Runs in the venv's python (a separate process: importing torch inside the setup process would lock its
# DLLs on Windows while pip replaces them). Prints one JSON line.
TORCH_PROBE = r"""
import json
from importlib import metadata
out = {"versions": {}, "errors": {}, "cuda": None}
for n in ("torch", "torchaudio", "torchvision"):
    try:
        out["versions"][n] = metadata.version(n)
    except metadata.PackageNotFoundError:
        pass
for n in out["versions"]:
    try:
        __import__(n)
    except Exception as e:
        out["errors"][n] = f"{type(e).__name__}: {e}"[:300]
if "torch" in out["versions"] and "torch" not in out["errors"]:
    import torch
    out["cuda"] = bool(torch.cuda.is_available())
    try:
        out["mps"] = bool(torch.backends.mps.is_available())
    except Exception:
        out["mps"] = False
print("L2R_TORCH " + json.dumps(out))
"""


def probe_torch(python: Path, probe: Probe | None = None) -> dict:
    """Installed torch/torchaudio/torchvision versions, import errors and CUDA availability."""
    import json

    out = (probe or (lambda c: run_probe(c, timeout=240)))([str(python), "-c", TORCH_PROBE]) or ""
    for line in out.splitlines():
        if line.startswith("L2R_TORCH "):
            try:
                return json.loads(line[len("L2R_TORCH "):])
            except ValueError:
                break
    return {"versions": {}, "errors": {"probe": "could not run the torch check"}, "cuda": None}


def _split(v: str) -> tuple[tuple[int, ...], str]:
    base, _, local = v.partition("+")
    nums = tuple(int(x) for x in re.findall(r"\d+", base)[:3])
    return nums, local


def torch_problems(info: dict, gpu: "GpuInfo") -> list[str]:
    """Why the installed torch set is broken ([] = fine or not installed).

    The real-world failure (2026-11-16): a later pip step pulled torchvision from PyPI, which replaced the CUDA
    torch with PyPI's CPU-only Windows torch; the CUDA torchaudio left behind then fails with
    'Could not load this library: ...libtorchaudio.pyd'. torchaudio itself no longer needs the exact torch version
    (torch 2.15 + torchaudio 2.11 load fine), so versions are not compared - builds and imports are.
    """
    v = info.get("versions") or {}
    if "torch" not in v:
        return []
    problems = [f"{n} does not load ({e})" for n, e in (info.get("errors") or {}).items()]
    if gpu.apple:  # macOS: one PyPI build, no CPU/CUDA variants; only MPS matters
        if info.get("mps") is False and not info.get("errors"):
            problems.append("torch cannot use the Apple GPU (torch.backends.mps.is_available() is False)")
        return problems
    builds = {n: _split(x)[1] for n, x in v.items()}
    tlocal = builds["torch"]
    if len(set(builds.values())) > 1:
        problems.append("mixed CPU/CUDA builds: " + ", ".join(f"{n} {v[n]}" for n in v))
    if gpu.available and gpu.cuda and not tlocal.startswith("cu") and info.get("cuda") is not True:
        problems.append(f"torch {v['torch']} is not a CUDA build although an NVIDIA GPU was found")
    elif gpu.available and gpu.cuda and info.get("cuda") is False and not info.get("errors"):
        problems.append("torch cannot use the GPU (torch.cuda.is_available() is False)")
    return problems


def torch_pins(versions: dict) -> str:
    """Constraints for later pip steps: exact public versions (a local '+cu128' build satisfies them)."""
    return "".join(f"{n}=={versions[n].partition('+')[0]}\n" for n in TORCH_PACKAGES if n in versions)


@dataclass
class SetupPlan:
    commands: list[list[str]] = field(default_factory=list)
    optional: list[int] = field(default_factory=list)  # indices of commands allowed to fail
    notes: list[str] = field(default_factory=list)


def plan_setup(repo: Path, python: Path, gpu: GpuInfo, mode: str = "full",
               torch_installed: bool = False, groups: tuple[str, ...] = GROUPS_FULL,
               torch_broken: list[str] | None = None, pins: Path | None = None,
               platform: str | None = None) -> SetupPlan:
    """Pip commands per requirement group.

    torch: installed once as a matching torch/torchaudio/torchvision set from the CUDA index; skipped when
    already installed and healthy; uninstalled + reinstalled when `torch_broken` lists problems.
    pins: after the torch step its versions are written there and passed as constraints (-c) to every later
    pip step, so no other package can replace torch with another build (the cause of libtorchaudio errors).
    """
    pip = [str(python), "-m", "pip", "install", "--disable-pip-version-check"]
    req = repo / "requirements"
    plan = SetupPlan()
    pinned = False  # becomes True after the torch step wrote the pins file
    plan.commands.append([str(python), "-m", "pip", "install", "--disable-pip-version-check", "-q",
                          "--upgrade", "pip", "setuptools", "wheel"])
    for group in groups:
        path = req / f"{group}.txt"
        if not path.exists():
            continue
        if group == "torch":
            tag = torch_index_tag(gpu)
            if torch_installed and torch_broken:
                plan.notes.append("PyTorch is broken (" + "; ".join(torch_broken) + ") - reinstalling a matching "
                                  "torch/torchaudio/torchvision set (~2-3 GB download).")
                plan.commands.append([str(python), "-m", "pip", "uninstall", "-y", *TORCH_PACKAGES])
                plan.commands.append(pip + ["-r", str(path)] + torch_index_args(gpu))
            elif torch_installed:
                plan.notes.append("torch already installed and working - skipped.")
                if mode == "full":  # still add torchvision when an older setup did not install it
                    plan.commands.append(pip + ["-r", str(path)] + torch_index_args(gpu))
            else:
                if tag == "cpu":
                    plan.notes.append("No NVIDIA GPU/CUDA detected: installing CPU-only torch "
                                      "(transcription will be slow).")
                plan.commands.append(pip + ["-r", str(path)] + torch_index_args(gpu))
            if pins is not None:
                plan.commands.append([str(python), str(repo / "scripts" / "setup_update.py"), "--write-pins",
                                      str(pins)])
                pinned = True
            if (platform or sys.platform).startswith("win") and tag.startswith("cu"):
                # faster-whisper's CTranslate2 needs cublas64_12.dll; CUDA 13 torch only ships cublas64_13.dll
                plan.commands.append([str(python), str(repo / "scripts" / "setup_update.py"), "--ensure-cuda12-libs"]
                                     + ([str(pins)] if pins is not None else []))
        else:
            if group in OPTIONAL_GROUPS:
                plan.optional.append(len(plan.commands))
            extra = ["-c", str(pins)] if pinned else []
            plan.commands.append(pip + ["-r", str(path)] + extra)
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


CUBLAS12_PACKAGE = "nvidia-cublas-cu12"


def has_cublas12(site_dirs: list[str]) -> bool:
    """True when cublas64_12.dll is available from torch's lib folder or an nvidia-cublas-cu12 wheel."""
    for sp in site_dirs:
        for cand in (Path(sp) / "torch" / "lib" / "cublas64_12.dll", Path(sp) / "nvidia" / "cublas" / "bin" /
                     "cublas64_12.dll"):
            if cand.is_file():
                return True
    return False

