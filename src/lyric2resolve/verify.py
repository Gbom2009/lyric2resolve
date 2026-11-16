"""Local verification checks (run on the user's PC via scripts/verify_local.py).

Each check returns a CheckResult. Later phases register more checks with @check.
Heavy imports happen inside the checks so this module imports with stdlib only.
"""

from __future__ import annotations

import datetime as _dt
import json
import platform
import sys
import time
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from lyric2resolve import setup_tools

OK, WARN, FAIL, SKIP = "ok", "warn", "fail", "skip"
ICON = {OK: "✅", WARN: "⚠️", FAIL: "❌", SKIP: "⏭️"}


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str = ""
    seconds: float = 0.0


@dataclass
class Context:
    repo: Path
    quick: bool = False          # skip slow checks (model loads, renders)
    offline: bool = False        # skip network checks
    probe: setup_tools.Probe = setup_tools.run_probe


CheckFn = Callable[[Context], CheckResult]
CHECKS: list[tuple[str, CheckFn]] = []


def check(name: str):
    def deco(fn: CheckFn) -> CheckFn:
        CHECKS.append((name, fn))
        return fn
    return deco


def run_checks(ctx: Context, only: set[str] | None = None) -> list[CheckResult]:
    results = []
    for name, fn in CHECKS:
        if only and name not in only:
            continue
        start = time.perf_counter()
        try:
            res = fn(ctx)
        except Exception as exc:  # a crashing check is a failed check, never a crashed report
            res = CheckResult(name, FAIL, f"{type(exc).__name__}: {exc}")
        res.name = name
        res.seconds = round(time.perf_counter() - start, 2)
        results.append(res)
    return results


# ------------------------------------------------------------------ checks
@check("python")
def _python(ctx: Context) -> CheckResult:
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    detail = f"{platform.python_version()} ({sys.executable}); venv: {'yes' if in_venv else 'NO'}"
    if sys.version_info < (3, 10):
        return CheckResult("python", FAIL, detail + " - need 3.10+")
    return CheckResult("python", OK if in_venv else WARN, detail)


@check("tkinter")
def _tk(ctx: Context) -> CheckResult:
    try:
        import tkinter  # noqa: F401
    except ImportError as exc:
        return CheckResult("tkinter", FAIL, f"{exc} - reinstall Python with 'tcl/tk and IDLE'")
    return CheckResult("tkinter", OK, f"Tk {tkinter.TkVersion}")


@check("git")
def _git(ctx: Context) -> CheckResult:
    out = ctx.probe(["git", "--version"])
    return CheckResult("git", OK, out.strip()) if out else CheckResult("git", FAIL, "git not found")


@check("ffmpeg")
def _ffmpeg(ctx: Context) -> CheckResult:
    from lyric2resolve.settings import load_settings

    path = setup_tools.find_tool("ffmpeg", load_settings()[0].ffmpeg_path)
    if not path:
        return CheckResult("ffmpeg", FAIL, setup_tools.FFMPEG_HELP)
    return CheckResult("ffmpeg", OK, f"{path} - {setup_tools.tool_version(path, ctx.probe)}")


@check("gpu")
def _gpu(ctx: Context) -> CheckResult:
    gpu = setup_tools.detect_gpu(ctx.probe)
    return CheckResult("gpu", OK if gpu.available else WARN,
                       gpu.describe() + f"; torch wheels: {setup_tools.torch_index_tag(gpu)}")


@check("torch_cuda")
def _torch(ctx: Context) -> CheckResult:
    try:
        import torch
    except ImportError:
        return CheckResult("torch_cuda", FAIL, "torch not installed - run setup_windows.bat")
    if not torch.cuda.is_available():
        return CheckResult("torch_cuda", WARN, f"torch {torch.__version__} but CUDA not available (CPU only)")
    return CheckResult("torch_cuda", OK, f"torch {torch.__version__}, CUDA {torch.version.cuda}, "
                                         f"{torch.cuda.get_device_name(0)}")


@check("blender")
def _blender(ctx: Context) -> CheckResult:
    from lyric2resolve.settings import load_settings

    path = setup_tools.find_tool("blender", load_settings()[0].blender_path)
    if not path:
        return CheckResult("blender", WARN, setup_tools.BLENDER_HELP)
    return CheckResult("blender", OK, f"{path} - {setup_tools.tool_version(path, ctx.probe)}")


ASSET_APIS = {
    "polyhaven": "https://api.polyhaven.com/types",
    "ambientcg": "https://ambientcg.com/api/v2/full_json?limit=1",
    "google_fonts": "https://github.com/google/fonts",
}


@check("asset_apis")
def _apis(ctx: Context) -> CheckResult:
    if ctx.offline:
        return CheckResult("asset_apis", SKIP, "offline mode")
    bad, good = [], []
    for name, url in ASSET_APIS.items():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "lyric2resolve-verify/1"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                (good if resp.status < 400 else bad).append(f"{name} {resp.status}")
        except Exception as exc:  # noqa: BLE001 - report any network error
            bad.append(f"{name}: {exc}")
    return CheckResult("asset_apis", FAIL if bad else OK, "; ".join(good + bad))


# Placeholders so the report shows what is still to come (later phases replace them).
PENDING = {
    "whisper_model_load": "Phase 4",
    "whisper_tiny_clip": "Phase 4",
    "vocal_separation": "Phase 3",
    "blender_3_frame_render": "Phase 15",
    "fcpxml_validity": "Phase 10",
}


def _pending(name: str, phase: str) -> CheckFn:
    return lambda ctx: CheckResult(name, SKIP, f"not implemented yet ({phase})")


def register_pending() -> None:
    have = {n for n, _ in CHECKS}
    for name, phase in PENDING.items():
        if name not in have:
            CHECKS.append((name, _pending(name, phase)))


# ------------------------------------------------------------------ report
def git_version(ctx: Context) -> str:
    out = ctx.probe(["git", "-C", str(ctx.repo), "log", "-1", "--format=%h %cs"])
    return (out or "unknown").strip()


def render_markdown(results: list[CheckResult], meta: dict) -> str:
    lines = ["# REPORT_LOCAL", "",
             f"- app version: {meta['version']}", f"- date: {meta['date']}",
             f"- system: {meta['system']}", ""]
    counts = {s: sum(r.status == s for r in results) for s in (OK, WARN, FAIL, SKIP)}
    lines.append(f"**Summary:** {counts[OK]} ok, {counts[WARN]} warnings, {counts[FAIL]} failed, {counts[SKIP]} skipped")
    lines += ["", "| check | status | detail | s |", "|---|---|---|---|"]
    for r in results:
        detail = r.detail.replace("|", "/").replace("\n", " ")
        lines.append(f"| {r.name} | {ICON[r.status]} {r.status} | {detail} | {r.seconds} |")
    lines += ["", "Paste this whole file into the Claude session."]
    return "\n".join(lines) + "\n"


def write_report(results: list[CheckResult], ctx: Context, out_dir: Path) -> tuple[Path, Path]:
    meta = {"version": git_version(ctx), "date": _dt.datetime.now().isoformat(timespec="seconds"),
            "system": f"{platform.system()} {platform.release()} / Python {platform.python_version()}"}
    out_dir.mkdir(parents=True, exist_ok=True)
    md, js = out_dir / "REPORT_LOCAL.md", out_dir / "REPORT_LOCAL.json"
    md.write_text(render_markdown(results, meta), encoding="utf-8")
    js.write_text(json.dumps({"meta": meta, "results": [asdict(r) for r in results]}, indent=2), encoding="utf-8")
    return md, js
