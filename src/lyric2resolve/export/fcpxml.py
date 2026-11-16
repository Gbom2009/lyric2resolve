"""FCPXML 1.9 writer for DaVinci Resolve (File > Import > Timeline).

Structure (one file per layout, one timeline each):
    resources: format (fps + 1920x1080 or 1080x1920), asset (Track A = full song), effect (Basic Title)
    library/event/project/sequence/spine/gap  (covers the whole song, starts at the start timecode)
        asset-clip  lane -1  -> the full song on an audio track
        title       lane  1  -> one Basic Title per lyric block (none inside instrumental gaps)
        marker               -> sections and bars
Version 1.9 is chosen because every current Resolve (18.x-20.x) imports it; validate with the DTD.
"""

from __future__ import annotations

import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

from .timecode import fcp_time
from .timeline import Plan

FCPXML_VERSION = "1.9"
BASIC_TITLE_UID = ".../Titles.localized/Bumper:Opener.localized/Basic Title.localized/Basic Title.moti"
POSITION_KEY = "9999/999166631/999166633/1/100/101"   # Basic Title "Position" parameter
DTD_URL = ("https://raw.githubusercontent.com/CommandPost/CommandPost/develop/src/extensions/cp/apple/"
           "fcpxml/dtd/FCPXMLv1_9.dtd")  # Apple's DTD, mirrored by CommandPost (downloaded for validation only)


def _rgba(hex_color: str, alpha: float = 1.0) -> str:
    n = int(hex_color[1:], 16)
    r, g, b = (n >> 16) & 255, (n >> 8) & 255, n & 255
    return f"{r / 255:.4g} {g / 255:.4g} {b / 255:.4g} {alpha:.4g}"


def file_url(path: str) -> str:
    """file:// URL for Windows (C:\\...) and POSIX (/...) absolute paths on any OS; relative stays relative."""
    if len(path) > 2 and path[1] == ":":
        return "file:///" + urllib.parse.quote(path.replace("\\", "/"), safe="/:")
    if path.startswith("/"):
        return "file://" + urllib.parse.quote(path, safe="/")
    if path.startswith("\\\\"):  # UNC \\server\share
        return "file:" + urllib.parse.quote(path.replace("\\", "/"), safe="/")
    return urllib.parse.quote(path.replace("\\", "/"))


def _stem(path: str) -> str:
    """File name without extension for Windows or POSIX paths, on any OS."""
    from pathlib import PureWindowsPath

    return PureWindowsPath(path).stem if "\\" in path else Path(path).stem


def build(plan: Plan, audio_rate: int = 44100) -> ET.Element:
    r = plan.rate
    t0 = plan.start_tc_frames
    root = ET.Element("fcpxml", version=FCPXML_VERSION)
    res = ET.SubElement(root, "resources")
    ET.SubElement(res, "format", id="r1", frameDuration=r.frame_duration, width=str(plan.width),
                  height=str(plan.height), colorSpace="1-1-1 (Rec. 709)")
    asset = ET.SubElement(res, "asset", id="r2", name=_stem(plan.song_path), start="0s",
                          duration=fcp_time(plan.duration_frames, r), hasAudio="1", audioSources="1",
                          audioChannels="2", audioRate=str(audio_rate))
    ET.SubElement(asset, "media-rep", kind="original-media", src=file_url(plan.song_path))
    ET.SubElement(res, "effect", id="r3", name="Basic Title", uid=BASIC_TITLE_UID)

    lib = ET.SubElement(root, "library")
    event = ET.SubElement(lib, "event", name="lyric2resolve")
    proj = ET.SubElement(event, "project", name=f"{plan.project_name or 'Lyrics'} {plan.layout.replace(':', 'x')}")
    seq = ET.SubElement(proj, "sequence", format="r1", duration=fcp_time(plan.duration_frames, r),
                        tcStart=fcp_time(t0, r), tcFormat="NDF", audioLayout="stereo", audioRate="48k")
    spine = ET.SubElement(seq, "spine")
    gap = ET.SubElement(spine, "gap", name="Lyrics", offset=fcp_time(t0, r), start=fcp_time(t0, r),
                        duration=fcp_time(plan.duration_frames, r))
    ET.SubElement(gap, "asset-clip", ref="r2", lane="-1", name=_stem(plan.song_path), offset=fcp_time(t0, r),
                  start="0s", duration=fcp_time(plan.duration_frames, r), audioRole="dialogue")
    for i, c in enumerate(plan.clips, start=1):
        s = c.style
        title = ET.SubElement(gap, "title", ref="r3", lane="1", name=c.text[:60] or f"Lyric {i}",
                              offset=fcp_time(t0 + c.start_frame, r), start=fcp_time(t0 + c.start_frame, r),
                              duration=fcp_time(c.duration, r))
        ET.SubElement(title, "param", name="Position", key=POSITION_KEY, value=f"{c.x:g} {c.y:g}")
        text = ET.SubElement(title, "text")
        ts = ET.SubElement(text, "text-style", ref=f"ts{i}")
        ts.text = "\n".join(c.lines) if c.lines else c.text
        tdef = ET.SubElement(title, "text-style-def", id=f"ts{i}")
        attrs = {"font": s.font_family, "fontSize": str(c.font_px), "fontFace": s.font_style,
                 "fontColor": _rgba(s.fill, s.fill_opacity), "alignment": s.align,
                 "bold": "1" if any(k in s.font_style.lower() for k in ("bold", "black", "heavy")) else "0",
                 "italic": "1" if "italic" in s.font_style.lower() else "0"}
        if s.outline_width > 0:
            attrs.update(strokeColor=_rgba(s.outline_color), strokeWidth=f"{s.outline_width:g}")
        if s.shadow_opacity > 0:
            attrs.update(shadowColor=_rgba(s.shadow_color, s.shadow_opacity),
                         shadowOffset=f"{(s.shadow_offset_x ** 2 + s.shadow_offset_y ** 2) ** 0.5:.3g} 315",
                         shadowBlurRadius=f"{s.shadow_blur:g}")
        ET.SubElement(tdef, "text-style", **attrs)
    for m in plan.markers:
        ET.SubElement(gap, "marker", start=fcp_time(t0 + m.frame, r), duration=r.frame_duration, value=m.name,
                      **({"note": m.note} if m.note else {}))
    return root


def to_string(plan: Plan, audio_rate: int = 44100) -> str:
    root = build(plan, audio_rate)
    ET.indent(root, space="  ")
    body = ET.tostring(root, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n' + body + "\n"


def write(plan: Plan, path: Path, audio_rate: int = 44100) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_string(plan, audio_rate), encoding="utf-8")
    return path


def validate(xml_text: str, dtd_path: Path) -> list[str]:
    """Validate against the FCPXML DTD with lxml. Returns error messages (empty = valid)."""
    from lxml import etree

    dtd = etree.DTD(str(dtd_path))
    doc = etree.fromstring(xml_text.encode("utf-8"))
    if dtd.validate(doc):
        return []
    return [f"line {e.line}: {e.message}" for e in dtd.error_log.filter_from_errors()]
