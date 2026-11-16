"""lyric2resolve - Build timeline (DaVinci Resolve script; works in Resolve free and Studio).

Run it from Resolve: Workspace > Scripts > Utility > lyric2resolve_build_timeline
(`lyric2resolve export ... --format resolve` copies it into your Resolve Scripts folder.)

It reads the last Resolve export job written by lyric2resolve and builds, in the CURRENT project:
  - one timeline per layout (16:9 / 9:16) with the full song on audio track 1,
  - one Fusion Text+ clip per lyric block on video track 1 at the exact frames,
    styled per the chosen styling level (BASIC / STYLED / FULL with simple animations),
  - section / bar markers.
Text+ clips are made from a Media Pool item named "l2r_textplus" (a Fusion Composition; see
docs/RESOLVE_SCRIPT.md). Without it the script imports the FCPXML instead (exact timing, plain titles).

Self-contained: standard library only, no lyric2resolve imports (Resolve runs it with its own Python).
API calls follow the Resolve scripting README (Developer/Scripting/README.txt, 2026 edition).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

TEMPLATE_NAME = "l2r_textplus"
BIN_NAME = "lyric2resolve"
MARKER_COLORS = {"section": "Blue", "downbeat": "Cyan", "beat": "Sky"}
FPS_STRINGS = {23.976: "23.976", 24.0: "24", 25.0: "25", 29.97: "29.97", 30.0: "30", 50.0: "50", 59.94: "59.94",
               60.0: "60"}


# ------------------------------------------------------------------ locating things
def data_dir() -> Path:
    if os.environ.get("LYRIC2RESOLVE_DATA"):
        return Path(os.environ["LYRIC2RESOLVE_DATA"]).expanduser()
    if sys.platform.startswith("win"):
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "lyric2resolve"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "lyric2resolve"
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "lyric2resolve"


def data_dirs() -> list[Path]:
    """All places the app may keep its data (Python from the Microsoft Store uses %USERPROFILE%\\lyric2resolve-data
    because its AppData writes are hidden from other programs such as Resolve)."""
    out = [data_dir()]
    if sys.platform.startswith("win") and not os.environ.get("LYRIC2RESOLVE_DATA"):
        out.append(Path(os.environ.get("USERPROFILE", str(Path.home()))) / "lyric2resolve-data")
    return out


def load_job(path: str | None = None) -> dict:
    if path is None:
        path = os.environ.get("L2R_JOB")
    if path is None:
        found = [d / "exports" / "last_resolve_job.json" for d in data_dirs()]
        found = [f for f in found if f.exists()]
        pointer = max(found, key=lambda f: f.stat().st_mtime) if found else data_dir() / "exports" / "x"
        if not pointer.exists():
            raise RuntimeError("No lyric2resolve export found. In the editor click Export… and tick "
                               "'Resolve script', then run this script again.")
        path = json.loads(pointer.read_text(encoding="utf-8"))["job"]
    return json.loads(Path(path).read_text(encoding="utf-8"))


def get_resolve(globals_dict: dict | None = None):
    g = globals_dict or globals()
    if g.get("resolve"):
        return g["resolve"]
    bmd = g.get("bmd")
    if bmd is not None:
        r = bmd.scriptapp("Resolve")
        if r:
            return r
    try:
        import DaVinciResolveScript as dvr  # noqa: N813 - official module name
        return dvr.scriptapp("Resolve")
    except ImportError as exc:
        raise RuntimeError("Run this script from inside DaVinci Resolve (Workspace > Scripts).") from exc


def iter_clips(folder):
    for clip in folder.GetClipList() or []:
        yield clip
    for sub in folder.GetSubFolderList() or []:
        yield from iter_clips(sub)


def find_clip(media_pool, name: str):
    for clip in iter_clips(media_pool.GetRootFolder()):
        if clip.GetName() == name:
            return clip
    return None


def find_or_make_bin(media_pool, name: str):
    root = media_pool.GetRootFolder()
    for sub in root.GetSubFolderList() or []:
        if sub.GetName() == name:
            return sub
    return media_pool.AddSubFolder(root, name) or root


# ------------------------------------------------------------------ Text+ styling
def hex_rgb(h: str) -> tuple[float, float, float]:
    n = int(h[1:], 16)
    return ((n >> 16) & 255) / 255.0, ((n >> 8) & 255) / 255.0, (n & 255) / 255.0


def text_tool(comp):
    tools = comp.GetToolList(False, "TextPlus") or {}
    if tools:
        return list(tools.values())[0]
    tool = comp.AddTool("TextPlus", -32768, -32768)
    out = comp.FindTool("MediaOut1")
    if out is not None and tool is not None:
        out.ConnectInput("Input", tool)
    return tool


def style_text(comp, tool, clip: dict, timeline: dict, level: str, log) -> None:
    """Set text + look on a Text+ tool. Every step is best-effort: a failure is logged, never fatal."""
    s = clip["style"]
    w, h = timeline["width"], timeline["height"]

    def setp(name, value, time=None):
        try:
            if time is None:
                tool.SetInput(name, value)
            else:
                tool.SetInput(name, value, time)
        except Exception as exc:  # noqa: BLE001
            log(f"  could not set {name}: {exc}")

    setp("StyledText", "\n".join(clip["lines"]) or clip["text"])
    setp("Font", s["font_family"])
    setp("Style", s["font_style"])
    size = clip["font_px"] / float(w)     # Text+ Size is relative to the frame width
    setp("Size", size)
    setp("Center", {1: 0.5 + clip["x"] / float(w), 2: 0.5 + clip["y"] / float(h)})
    setp("HorizontalJustificationNew", {"left": 0, "center": 1, "right": 2}[s["align"]])
    r, g, b = hex_rgb(s["fill"])
    setp("Red1", r), setp("Green1", g), setp("Blue1", b), setp("Alpha1", s["fill_opacity"])
    if level == "basic":
        return
    if s["outline_width"] > 0:
        r, g, b = hex_rgb(s["outline_color"])
        setp("Enabled2", 1), setp("Red2", r), setp("Green2", g), setp("Blue2", b)
        setp("Thickness2", s["outline_width"] / float(h) * 2.0)
    if s["shadow_opacity"] > 0:
        r, g, b = hex_rgb(s["shadow_color"])
        setp("Enabled3", 1), setp("Red3", r), setp("Green3", g), setp("Blue3", b), setp("Alpha3", s["shadow_opacity"])
        setp("Softness3", s["shadow_blur"] / 10.0)
        setp("Offset3", {1: s["shadow_offset_x"] / float(w), 2: -s["shadow_offset_y"] / float(h)})
    if s["glow_size"] > 0:
        try:
            glow = comp.AddTool("SoftGlow", -32768, -32768)
            out = comp.FindTool("MediaOut1")
            glow.ConnectInput("Input", tool)
            out.ConnectInput("Input", glow)
            glow.SetInput("Gain", s["glow_strength"])
            glow.SetInput("XGlowSize", s["glow_size"] / 2.0)
        except Exception as exc:  # noqa: BLE001
            log(f"  glow not added: {exc}")
    if level == "full":
        animate(comp, tool, clip, timeline, log)


def animate(comp, tool, clip: dict, timeline: dict, log) -> None:
    """Simple animations with keyframes (comp time 0 = first frame of the clip)."""
    s = clip["style"]
    n = max(1, round(s["animation_ms"] / 1000.0 * timeline["fps"]))
    last = clip["end"] - clip["start"] - 1
    try:
        start = int(comp.GetAttrs().get("COMPN_RenderStart", 0))
    except Exception:  # noqa: BLE001
        start = 0

    def keys(name, pairs):
        try:
            tool.AddModifier(name, "BezierSpline")
            for t, v in pairs:
                tool.SetInput(name, v, start + t)
        except Exception as exc:  # noqa: BLE001
            log(f"  animation on {name} skipped: {exc}")

    a_in, a_out = s["animation_in"], s["animation_out"]
    alpha = s["fill_opacity"]
    if a_in == "fade" or a_out == "fade":
        pts = []
        pts += [(0, 0.0), (n, alpha)] if a_in == "fade" else [(0, alpha)]
        pts += [(max(n + 1, last - n), alpha), (last, 0.0)] if a_out == "fade" else []
        keys("Alpha1", pts)
    if a_in == "pop":
        size = clip["font_px"] / float(timeline["width"])
        keys("Size", [(0, size * 0.6), (n, size * 1.08), (n + max(1, n // 2), size)])
    if a_in == "slide_up":
        cx = 0.5 + clip["x"] / float(timeline["width"])
        cy = 0.5 + clip["y"] / float(timeline["height"])
        keys("Center", [(0, {1: cx, 2: cy - 0.04}), (n, {1: cx, 2: cy})])
    if a_in == "word_reveal" and clip.get("words"):
        total = len(clip["text"]) or 1
        pts, chars = [(0, 0.0)], 0
        for text, ws, _we in clip["words"]:
            chars += len(text) + 1
            pts.append((max(0, ws - clip["start"]), min(1.0, chars / total)))
        keys("End", pts)  # Text+ Write On "End"


# ------------------------------------------------------------------ build
class BuildError(RuntimeError):
    pass


def ensure_frame_rate(project, fps: float, log) -> None:
    want = FPS_STRINGS.get(round(fps, 3), str(fps))
    have = str(project.GetSetting("timelineFrameRate") or "")
    if have and abs(float(have.split()[0]) - fps) < 0.01:
        return
    if project.SetSetting("timelineFrameRate", want):
        log(f"Project frame rate set to {want} fps")
        return
    raise BuildError(f"This project runs at {have} fps but the lyrics were exported at {want} fps. "
                     f"Create a new project, set Project Settings > Timeline frame rate to {want}, and run the "
                     "script again (Resolve cannot change the frame rate once media is in a project).")


def build_timeline(resolve, job: dict, tl_job: dict, media_pool, project, song, template, log) -> dict:
    name = tl_job["name"]
    tl = media_pool.CreateEmptyTimeline(name)
    if not tl:
        raise BuildError(f"Could not create timeline '{name}' (name already used?)")
    project.SetCurrentTimeline(tl)
    tl.SetSetting("useCustomSettings", "1")
    tl.SetSetting("timelineResolutionWidth", str(tl_job["width"]))
    tl.SetSetting("timelineResolutionHeight", str(tl_job["height"]))
    tl.SetStartTimecode(job["start_timecode"])
    t0 = tl.GetStartFrame()
    report = {"timeline": name, "titles": 0, "markers": 0, "mode": "textplus"}
    audio = media_pool.AppendToTimeline([{"mediaPoolItem": song, "startFrame": 0,
                                          "endFrame": tl_job["duration_frames"] - 1, "mediaType": 2,
                                          "trackIndex": 1, "recordFrame": t0}])
    if not audio:
        log("WARNING: the song could not be placed on the timeline")
    for i, clip in enumerate(tl_job["clips"], start=1):
        items = media_pool.AppendToTimeline([{"mediaPoolItem": template, "startFrame": 0,
                                              "endFrame": clip["end"] - clip["start"] - 1, "mediaType": 1,
                                              "trackIndex": 1, "recordFrame": t0 + clip["start"]}])
        if not items:
            log(f"WARNING: title {i} could not be placed ({clip['text'][:40]})")
            continue
        item = items[0]
        try:
            item.SetName(clip["text"][:60])
        except Exception:  # noqa: BLE001
            pass
        comp = item.GetFusionCompByIndex(1)
        if comp is None:
            log(f"WARNING: title {i} has no Fusion composition (is '{TEMPLATE_NAME}' a Fusion Composition?)")
            continue
        tool = text_tool(comp)
        style_text(comp, tool, clip, {**tl_job, "fps": job["fps"]}, job["styling_level"], log)
        report["titles"] += 1
    for m in tl_job["markers"]:
        if tl.AddMarker(m["frame"], MARKER_COLORS.get(m["kind"], "Blue"), m["name"], m.get("note", ""), 1,
                        f"l2r:{m['kind']}:{m['frame']}"):
            report["markers"] += 1
    return report


def run(resolve, job: dict, log=print) -> list[dict]:
    pm = resolve.GetProjectManager()
    project = pm.GetCurrentProject()
    if project is None:
        raise BuildError("Open (or create) a Resolve project first.")
    ensure_frame_rate(project, job["fps"], log)
    media_pool = project.GetMediaPool()
    template = find_clip(media_pool, TEMPLATE_NAME)
    reports = []
    if template is None:
        log(f"No Media Pool item named '{TEMPLATE_NAME}' found -> importing the FCPXML timelines instead "
            "(exact timing, plain titles). See docs/RESOLVE_SCRIPT.md to get real Text+ clips.")
        for tl_job in job["timelines"]:
            tl = media_pool.ImportTimelineFromFile(tl_job["fcpxml"], {"timelineName": tl_job["name"],
                                                                      "importSourceClips": True})
            reports.append({"timeline": tl_job["name"], "mode": "fcpxml", "ok": bool(tl)})
        return reports
    media_pool.SetCurrentFolder(find_or_make_bin(media_pool, BIN_NAME))
    imported = media_pool.ImportMedia([job["song_path"]])
    if not imported:
        raise BuildError(f"Could not import the song: {job['song_path']}")
    song = imported[0]
    for tl_job in job["timelines"]:
        reports.append(build_timeline(resolve, job, tl_job, media_pool, project, song, template, log))
    return reports


def main() -> int:
    try:
        resolve = get_resolve()
        job = load_job()
        for rep in run(resolve, job):
            print("lyric2resolve:", rep)
        print("lyric2resolve: done.")
        return 0
    except Exception as exc:  # noqa: BLE001 - show the reason in Resolve's console
        print(f"lyric2resolve ERROR: {exc}")
        return 1


if __name__ == "__main__":
    main()
