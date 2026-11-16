"""SRT (line + word), CSV and EDL (markers) exports from the clip plan."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from .timecode import Rate, frames_to_tc
from .timeline import Plan


def srt_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(plan: Plan, words: bool = False) -> str:
    """SRT with times from the song start (00:00:00,000 = first audio sample).

    words=True: one cue per word (start..end of the word, clipped to the block's clip)."""
    r = plan.rate
    cues: list[tuple[float, float, str]] = []
    for c in plan.clips:
        if words:
            for w in c.words:
                s, e = max(w.start_frame, c.start_frame), min(max(w.end_frame, w.start_frame + 1), c.end_frame)
                if e > s:
                    cues.append((r.seconds(s), r.seconds(e), w.text))
        else:
            cues.append((r.seconds(c.start_frame), r.seconds(c.end_frame), "\n".join(c.lines) or c.text))
    out = []
    for i, (s, e, text) in enumerate(cues, start=1):
        out.append(f"{i}\n{srt_time(s)} --> {srt_time(e)}\n{text}\n")
    return "\n".join(out)


def to_csv(plan: Plan) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["index", "start_s", "end_s", "start_tc", "end_tc", "start_frame", "end_frame", "text"])
    r = plan.rate
    for i, c in enumerate(plan.clips, start=1):
        w.writerow([i, f"{r.seconds(c.start_frame):.3f}", f"{r.seconds(c.end_frame):.3f}",
                    frames_to_tc(plan.start_tc_frames + c.start_frame, r),
                    frames_to_tc(plan.start_tc_frames + c.end_frame, r), c.start_frame, c.end_frame, c.text])
    return buf.getvalue()


MARKER_COLORS = {"section": "Blue", "downbeat": "Cyan", "beat": "Sky", "lyric": "Yellow"}


def to_edl(plan: Plan, lyric_markers: bool = True) -> str:
    """CMX3600 EDL: one audio event for the song + LOC marker lines.

    In Resolve: right-click the timeline in the Media Pool > Timelines > Import > Timeline Markers from EDL
    (or import it as a timeline)."""
    r: Rate = plan.rate
    t0 = plan.start_tc_frames
    title = (plan.project_name or "LYRICS").upper()[:60]
    lines = [f"TITLE: {title} {plan.layout}", "FCM: NON-DROP FRAME", ""]
    src_in, src_out = frames_to_tc(0, r), frames_to_tc(plan.duration_frames, r)
    rec_in, rec_out = frames_to_tc(t0, r), frames_to_tc(t0 + plan.duration_frames, r)
    lines.append(f"001  AX       A     C        {src_in} {src_out} {rec_in} {rec_out}")
    lines.append(f"* FROM CLIP NAME: {Path(plan.song_path).name}")
    markers = [(m.frame, MARKER_COLORS.get(m.kind, "Blue"), m.name) for m in plan.markers]
    if lyric_markers:
        markers += [(c.start_frame, MARKER_COLORS["lyric"], c.text[:80]) for c in plan.clips]
    for frame, color, name in sorted(markers, key=lambda x: x[0]):
        clean = " ".join(name.replace("\n", " ").split())
        lines.append(f"* LOC: {frames_to_tc(t0 + frame, r)} {color.upper():8} {clean}")
    return "\n".join(lines) + "\n"


def write_all(plan: Plan, out: Path, base: str, tag: str) -> list[Path]:
    files = {
        f"{base}_{tag}_lines.srt": to_srt(plan, words=False),
        f"{base}_{tag}_words.srt": to_srt(plan, words=True),
        f"{base}_{tag}.csv": to_csv(plan),
        f"{base}_{tag}_markers.edl": to_edl(plan),
    }
    written = []
    for name, text in files.items():
        p = out / name
        p.write_text(text, encoding="utf-8")
        written.append(p)
    return written
