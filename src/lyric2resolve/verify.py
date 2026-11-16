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
    blender_runner: object = None  # tests inject a fake BlenderRunner


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


@check("audio_offset")
def _audio_offset(ctx: Context) -> CheckResult:
    """Pure-math A/B offset detection on synthetic audio (checks numpy/scipy install)."""
    import numpy as np

    from lyric2resolve.audio import align

    sr = 44100
    rng = np.random.default_rng(0)
    v = rng.standard_normal((sr * 6, 2)).astype(np.float32) * 0.1
    late = align.compensate(v, sr, -120.0, length=len(v))
    res = align.estimate_offset(v, late, sr)
    ok = abs(res.offset_ms - 120.0) < 1.0
    return CheckResult("audio_offset", OK if ok else FAIL, f"expected +120.0 ms, got {res.offset_ms:+.2f} ms")


@check("vocal_separation")
def _separation(ctx: Context) -> CheckResult:
    try:
        import audio_separator  # noqa: F401
    except ImportError:
        return CheckResult("vocal_separation", WARN, "audio-separator not installed (optional; only needed "
                           "when you have no acapella). Re-run setup_windows.bat to retry.")
    if ctx.quick:
        return CheckResult("vocal_separation", SKIP, "installed; smoke test skipped (--quick)")
    import tempfile

    import numpy as np

    from lyric2resolve import paths
    from lyric2resolve.audio import stems, wavio

    with tempfile.TemporaryDirectory() as tmp:
        sr = 44100
        t = np.arange(sr * 5) / sr
        x = (0.2 * np.sin(2 * np.pi * 220 * t) + 0.2 * np.sin(2 * np.pi * 55 * t)).astype(np.float32)
        song = wavio.write(Path(tmp) / "song.wav", np.stack([x, x], axis=1), sr)
        backend = stems.AudioSeparatorBackend(model_dir=paths.ensure_data_dir() / "models" / "separation")
        v, i = backend.separate(song, Path(tmp) / "out")
        return CheckResult("vocal_separation", OK, f"{backend.model}: {v.name}, {i.name}")


TINY_CLIP_WORDS = ("hello", "world", "sing", "song", "together", "tonight")


@check("whisper_model_load")
def _whisper_load(ctx: Context) -> CheckResult:
    if ctx.quick:
        return CheckResult("whisper_model_load", SKIP, "--quick")
    from lyric2resolve.transcription import engine_from_settings

    eng = engine_from_settings()
    eng.model()
    ctx.whisper = eng  # type: ignore[attr-defined]  # reused by the next check
    return CheckResult("whisper_model_load", OK, f"{eng.opt.model} on {eng.opt.device}/{eng.opt.compute_type}")


@check("whisper_tiny_clip")
def _whisper_clip(ctx: Context) -> CheckResult:
    if ctx.quick:
        return CheckResult("whisper_tiny_clip", SKIP, "--quick")
    eng = getattr(ctx, "whisper", None)
    if eng is None:
        return CheckResult("whisper_tiny_clip", SKIP, "model did not load")
    clip = ctx.repo / "tests" / "data" / "tiny_vocal.wav"
    tr = eng.transcribe(str(clip))
    text = " ".join(w.text for w in tr.words).lower()
    hits = [w for w in TINY_CLIP_WORDS if w in text]
    ordered = all(a.start <= b.start for a, b in zip(tr.words, tr.words[1:]))
    status = OK if len(hits) >= 4 and ordered else WARN
    al = eng.align(str(clip), "Hello world.\nWe sing this song together tonight.")
    return CheckResult("whisper_tiny_clip", status,
                       f"heard: '{text}' ({len(hits)}/{len(TINY_CLIP_WORDS)} key words, lang {tr.language}); "
                       f"forced alignment: {len(al.words)} words")


@check("fcpxml_validity")
def _fcpxml(ctx: Context) -> CheckResult:
    """Generate FCPXML for a synthetic project in both layouts and validate it against Apple's DTD."""
    import tempfile

    from lyric2resolve import project as proj
    from lyric2resolve.export import fcpxml
    from lyric2resolve.export.timeline import build_plan

    words = proj.make_words([{"text": t, "start": 1 + i * 0.5, "end": 1.4 + i * 0.5, "line": i // 3}
                             for i, t in enumerate("we sing this song all night long".split())])
    p = proj.Project(name="verify", words=words, blocks=proj.blocks_by_line(words), audio={"duration_s": 10})
    if ctx.offline:
        return CheckResult("fcpxml_validity", SKIP, "offline (DTD download needed)")
    with tempfile.TemporaryDirectory() as tmp:
        dtd = Path(tmp) / "fcpxml.dtd"
        req = urllib.request.Request(fcpxml.DTD_URL, headers={"User-Agent": "lyric2resolve-verify/1"})
        with urllib.request.urlopen(req, timeout=20) as r:
            dtd.write_bytes(r.read())
        errors = []
        for layout in ("16:9", "9:16"):
            errors += fcpxml.validate(fcpxml.to_string(build_plan(p, layout)), dtd)
    return CheckResult("fcpxml_validity", FAIL if errors else OK,
                       "; ".join(errors[:3]) or "FCPXML 1.9 valid (16:9 + 9:16); now test the import in Resolve")


@check("claude_cli")
def _claude_cli(ctx: Context) -> CheckResult:
    """Optional Assistant: is the Claude Code CLI installed? (Login is not checked: we never touch tokens.)"""
    from lyric2resolve.claude_link import cli
    from lyric2resolve.settings import load_settings

    st = cli.status(load_settings()[0].claude_cli_path)
    if not st.installed:
        return CheckResult("claude_cli", WARN, "optional - " + st.message.splitlines()[0])
    return CheckResult("claude_cli", OK, f"{st.version} at {st.path}; send a message in the editor's Assistant card "
                                         "to check the login")


@check("mcp_server")
def _mcp_server(ctx: Context) -> CheckResult:
    """Start the app's MCP server like Claude Code does (stdio) and list its tools."""
    import subprocess
    import tempfile

    from lyric2resolve import project as proj
    from lyric2resolve.claude_link import cli

    with tempfile.TemporaryDirectory() as tmp:
        words = proj.make_words([{"text": "hello", "start": 1.0, "end": 1.5}])
        path = proj.save(proj.Project(name="verify", words=words, blocks=proj.blocks_by_line(words)),
                         Path(tmp) / "verify" / proj.PROJECT_FILE)
        srv = cli.mcp_config(path)["mcpServers"][cli.SERVER_NAME]
        import os

        env = {**os.environ, **srv["env"]}
        msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "get_project", "arguments": {}}}]
        out = subprocess.run([srv["command"], *srv["args"]], input="".join(json.dumps(m) + "\n" for m in msgs),
                             capture_output=True, text=True, encoding="utf-8", env=env, timeout=60,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        resp = [json.loads(x) for x in out.stdout.splitlines() if x.strip()]
    if len(resp) != 3 or resp[2]["result"]["isError"]:
        return CheckResult("mcp_server", FAIL, (out.stderr or out.stdout or "no answer").strip()[-300:])
    return CheckResult("mcp_server", OK, f"{len(resp[1]['result']['tools'])} tools; get_project works")


@check("blender_3_frame_render")
def _blender_render(ctx: Context) -> CheckResult:
    """The app's real render path (scene build + headless render) for 3 preview frames of a tiny test song."""
    import tempfile

    import numpy as np

    from lyric2resolve import project as proj
    from lyric2resolve.audio import wavio
    from lyric2resolve.render import presets, render_project
    from lyric2resolve.render.blender import find_blender
    from lyric2resolve.settings import load_settings

    if ctx.quick:
        return CheckResult("blender_3_frame_render", SKIP, "--quick")
    if ctx.blender_runner is None and not find_blender(load_settings()[0].blender_path):
        return CheckResult("blender_3_frame_render", WARN, "Blender not found - " + setup_tools.BLENDER_HELP)
    with tempfile.TemporaryDirectory() as tmp:
        sr = 44100
        t = np.arange(4 * sr) / sr
        y = (0.4 * np.sin(2 * np.pi * 80 * t) * (np.mod(t, 0.5) < 0.1)).astype(np.float32)
        wav = wavio.write(Path(tmp) / "song.wav", np.stack([y, y], axis=1), sr)
        words = proj.make_words([{"text": "test", "start": 0.5, "end": 1.0}])
        path = proj.save(proj.Project(name="verify", words=words, blocks=proj.blocks_by_line(words),
                                      audio={"song_wav": str(wav), "duration_s": 4.0}),
                         Path(tmp) / "verify" / proj.PROJECT_FILE)
        preset = presets.replace(presets.get("preview"), max_seconds=3 / 15)  # 3 frames at 15 fps
        t0 = time.perf_counter()
        rep = render_project(path, "spectrum_bars", preset, ["16:9"], do_mux=False, log=lambda m: None,
                             runner=ctx.blender_runner, textures_root=Path(tmp) / "tex")
        secs = time.perf_counter() - t0
        frames = sorted((Path(rep.folder) / "frames" / "16x9").glob("*.png"))
    if not rep.ok or len(frames) != 3:
        return CheckResult("blender_3_frame_render", FAIL,
                           f"{len(frames)} of 3 frames; {' '.join(rep.messages)[-300:]}")
    return CheckResult("blender_3_frame_render", OK,
                       f"3 frames (Eevee, 960x540) incl. scene build in {secs:.0f} s; {' '.join(rep.messages)}")


# Placeholders so the report shows what is still to come (later phases replace them).
PENDING: dict[str, str] = {}


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
