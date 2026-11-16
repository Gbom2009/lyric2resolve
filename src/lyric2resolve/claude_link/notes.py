"""Per-project Claude memory: a saved session id and a CLAUDE.md notes file next to project.json.

CLAUDE.md has an auto-generated "state" part (rewritten before every Assistant run, so a
fresh Claude session knows the project) and a free "notes" part (decisions, style choices)
that the app never overwrites. Both Claude and the user may edit the notes part.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from lyric2resolve import project as proj

NOTES_FILE = "CLAUDE.md"
SESSION_FILE = "claude_session.json"
STATE_BEGIN = "<!-- l2r:state:begin (auto-generated, rewritten by the app) -->"
STATE_END = "<!-- l2r:state:end -->"
NOTES_HEADER = "## Notes (decisions, style choices; kept by the app, edit freely)"


@dataclass
class SessionInfo:
    session_id: str = ""
    created: str = ""
    last_used: str = ""
    runs: int = 0
    history: list[dict] = field(default_factory=list)  # [{"role": "user"|"assistant", "text": ..., "time": ...}]

    MAX_HISTORY = 200

    def add(self, role: str, text: str) -> None:
        self.history.append({"role": role, "text": text, "time": _now()})
        del self.history[:-self.MAX_HISTORY]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def session_path(project_dir: Path) -> Path:
    return Path(project_dir) / SESSION_FILE


def load_session(project_dir: Path) -> SessionInfo:
    try:
        data = json.loads(session_path(project_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return SessionInfo()
    if not isinstance(data, dict):
        return SessionInfo()
    known = SessionInfo.__dataclass_fields__
    return SessionInfo(**{k: v for k, v in data.items() if k in known})


def save_session(project_dir: Path, info: SessionInfo) -> Path:
    path = session_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(info), indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def reset_session(project_dir: Path) -> None:
    """Forget the Claude session (start a new conversation). CLAUDE.md notes are kept."""
    try:
        session_path(project_dir).unlink()
    except FileNotFoundError:
        pass


# ------------------------------------------------------------------ CLAUDE.md
def _fmt_t(t: float) -> str:
    m, s = divmod(max(0.0, t), 60)
    return f"{int(m)}:{s:05.2f}"


def state_markdown(p: proj.Project, project_path: Path) -> str:
    a = p.analysis or {}
    st = p.settings
    lines = [
        f"# lyric2resolve project: {p.name}",
        "",
        "You are the Assistant inside the lyric2resolve app. Change the project ONLY through the",
        "`lyric2resolve` MCP tools (they edit the project that is open in the editor, with undo).",
        "Do not edit project.json directly. Keep answers short. Record lasting decisions",
        "(style choices, section plans) in the Notes part below - you may edit this file.",
        "You may read and write files inside this project folder. Reference files the user attached are in",
        "`context/` (images can be viewed with the Read tool). Custom Blender scenes go in `scenes/<name>/scene.py`",
        "(see the `custom_scene_guide` tool) and are rendered with the `render_clip` tool.",
        "",
        "## Current state",
        f"- File: `{project_path}`",
        f"- Words: {len(p.words)}, blocks: {len(p.blocks)}, sections: {len(p.sections)}, gaps: {len(p.gaps)}",
        f"- Language: {p.language or 'auto'}; lyrics given: {'yes' if p.lyrics else 'no'}",
    ]
    if a.get("bpm"):
        lines.append(f"- BPM {a.get('bpm'):.1f}, key {a.get('key', '?')}, duration {a.get('duration', 0):.1f} s")
    lines.append(f"- Export: {st.fps} fps, layouts {', '.join(st.layouts)}, styling level "
                 f"{st.styling_level}")
    if p.sections:
        lines.append("- Sections: " + ", ".join(f"{s.label} {_fmt_t(s.start)}-{_fmt_t(s.end)}" for s in p.sections))
    if p.gaps:
        lines.append("- Instrumental gaps: " + ", ".join(f"{_fmt_t(g.start)}-{_fmt_t(g.end)}" for g in p.gaps))
    ctx = project_path.parent / "context"
    if ctx.is_dir():
        files = sorted(f.name for f in ctx.iterdir() if f.is_file())
        if files:
            lines.append("- Attached reference files (context/): " + ", ".join(files[:30]))
    if getattr(p, "clips", None):
        lines.append("- Clips on the timeline: " + ", ".join(f"{c.name} {_fmt_t(c.start)}-{_fmt_t(c.end)}"
                                                             for c in p.clips))
    if p.extra.get("template"):
        lines.append(f"- Template: {p.extra['template']}")
    lines.append(f"- State written: {_now()}")
    return "\n".join(lines)


_STATE_RE = re.compile(re.escape(STATE_BEGIN) + r".*?" + re.escape(STATE_END), re.S)


def write_notes(project_path: Path, p: proj.Project | None = None) -> Path:
    """Create/refresh CLAUDE.md next to project.json, keeping the user's/Claude's notes."""
    project_path = Path(project_path)
    p = p if p is not None else proj.load(project_path)
    path = project_path.parent / NOTES_FILE
    block = f"{STATE_BEGIN}\n{state_markdown(p, project_path)}\n{STATE_END}"
    try:
        old = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        old = ""
    if _STATE_RE.search(old):
        new = _STATE_RE.sub(lambda m: block, old, count=1)
    else:
        rest = old.strip()
        new = block + "\n\n" + (rest if rest else NOTES_HEADER + "\n\n- (nothing yet)") + "\n"
    if NOTES_HEADER not in new:
        new = new.rstrip() + "\n\n" + NOTES_HEADER + "\n\n- (nothing yet)\n"
    path.write_text(new, encoding="utf-8")
    return path


def read_user_notes(project_dir: Path) -> str:
    """The free notes part of CLAUDE.md (everything after the auto-generated state)."""
    try:
        text = (Path(project_dir) / NOTES_FILE).read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    text = _STATE_RE.sub("", text)
    return text.replace(NOTES_HEADER, "").strip()
