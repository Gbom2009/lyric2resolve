"""Editor backend: an EditorSession (pure logic) wrapped by a FastAPI app.

All edits go through POST /api/op/{name} with a JSON body; every successful edit is
recorded for undo/redo and saved to project.json immediately (autosave).
"""

from __future__ import annotations

import inspect
import threading
from pathlib import Path
from typing import Any, Callable

from lyric2resolve import project as proj
from lyric2resolve.analysis import sanity

from . import ops, presets
from .history import History

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _apply_presets(p: proj.Project, default: str | None = None, section_id: str | None = None,
                   merge_short: bool = False) -> None:
    presets.apply_presets(p, default, section_id)
    if merge_short:
        presets.merge_short_blocks(p)


def _set_settings(p: proj.Project, **values: Any) -> None:
    known = {f for f in proj.ProjectSettings.__dataclass_fields__}
    for k, v in values.items():
        if k not in known:
            raise ops.OpError(f"unknown setting {k}")
        cur = getattr(p.settings, k)
        setattr(p.settings, k, type(cur)(v) if isinstance(cur, (int, float, str, bool)) and v is not None else v)


def _set_section_preset(p: proj.Project, section_id: str, preset: str | None) -> None:
    if preset and preset.lower() not in presets.PRESETS:
        raise ops.OpError(f"unknown preset {preset}")
    ops.update_section(p, section_id, preset=preset.lower() if preset else None)


# op name -> function(project, **args). Only these can be called from the browser.
OPS: dict[str, Callable] = {
    "merge_words": ops.merge_words,
    "merge_blocks": ops.merge_blocks,
    "split_block": ops.split_block,
    "split_block_words": ops.split_block_words,
    "move_word": ops.move_word,
    "remove_block": ops.remove_block,
    "set_block_text": ops.set_block_text,
    "set_block_style": ops.set_block_style,
    "set_word_text": ops.set_word_text,
    "set_word_timing": ops.set_word_timing,
    "nudge_words": ops.nudge_words,
    "nudge_block": ops.nudge_block,
    "add_gap": ops.add_gap,
    "update_gap": ops.update_gap,
    "remove_gap": ops.remove_gap,
    "update_section": ops.update_section,
    "set_section_preset": _set_section_preset,
    "apply_presets": _apply_presets,
    "merge_short_blocks": presets.merge_short_blocks,
    "set_settings": _set_settings,
}


class EditorSession:
    def __init__(self, path: Path, project: proj.Project | None = None):
        self.path = Path(path)
        self.project = project if project is not None else proj.load(self.path)
        self.history = History()
        self.lock = threading.Lock()

    # ------------------------------------------------------------ views
    def flags(self) -> list[dict]:
        activity = self.project.analysis.get("vocal_activity")
        act = [tuple(a) for a in activity] if activity else None
        return [f.to_dict() for f in sanity.check(self.project, act)]

    def blocks_view(self) -> list[dict]:
        out = []
        for b in self.project.blocks:
            try:
                s, e = self.project.block_span(b)
            except proj.ProjectError:
                continue
            out.append({"id": b.id, "start": s, "end": e, "word_ids": b.word_ids, "style": b.style,
                        "text": self.project.block_text(b), "display": presets.display_text(self.project, b),
                        "overridden": b.text_override is not None})
        return out

    def state(self) -> dict:
        return {"project": self.project.to_dict(), "blocks": self.blocks_view(), "flags": self.flags(),
                "history": self.history.state(), "problems": self.project.validate()}

    # ------------------------------------------------------------ edits
    def apply(self, name: str, args: dict | None = None) -> dict:
        fn = OPS.get(name)
        if fn is None:
            raise ops.OpError(f"unknown operation {name}")
        args = dict(args or {})
        params = inspect.signature(fn).parameters
        accepts_kwargs = any(p.kind == p.VAR_KEYWORD for p in params.values())
        bad = [k for k in args if k not in params and not accepts_kwargs]
        if bad:
            raise ops.OpError(f"{name}: unexpected arguments {bad}")
        with self.lock:
            self.history.record(name, self.project)
            try:
                fn(self.project, **args)
                problems = self.project.validate()
                if problems:
                    raise ops.OpError("; ".join(problems))
            except (ops.OpError, ValueError, TypeError, proj.ProjectError) as exc:
                # restore the snapshot: a failed op never leaves a half-edited project
                restored = self.history.undo(self.project)
                self.history.redo_stack.clear()
                if restored:
                    self.project = restored[1]
                raise ops.OpError(str(exc)) from exc
            self.save()
        return self.state()

    def undo(self) -> dict:
        with self.lock:
            res = self.history.undo(self.project)
            if res:
                self.project = res[1]
                self.save()
        return self.state()

    def redo(self) -> dict:
        with self.lock:
            res = self.history.redo(self.project)
            if res:
                self.project = res[1]
                self.save()
        return self.state()

    def save(self) -> None:
        proj.save(self.project, self.path)

    def audio_path(self, kind: str) -> Path | None:
        key = {"song": "song_wav", "vocals": "vocals_wav", "instrumental": "instrumental_wav"}.get(kind)
        value = self.project.audio.get(key) if key else None
        return Path(value) if value and Path(value).is_file() else None


def create_app(session: EditorSession):
    from fastapi import Body, FastAPI, HTTPException
    from fastapi.responses import FileResponse, HTMLResponse
    from fastapi.staticfiles import StaticFiles

    app = FastAPI(title="lyric2resolve editor")
    app.state.session = session

    @app.get("/api/state")
    def get_state():
        return session.state()

    @app.post("/api/op/{name}")
    def do_op(name: str, args: dict = Body(default_factory=dict)):
        try:
            return session.apply(name, args)
        except ops.OpError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/undo")
    def undo():
        return session.undo()

    @app.post("/api/redo")
    def redo():
        return session.redo()

    @app.get("/api/audio/{kind}")
    def audio(kind: str):
        path = session.audio_path(kind)
        if path is None:
            raise HTTPException(status_code=404, detail=f"no {kind} audio in this project")
        return FileResponse(path, media_type="audio/wav")

    if (STATIC_DIR / "index.html").exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

        @app.get("/")
        def index():
            return FileResponse(STATIC_DIR / "index.html")
    else:
        @app.get("/")
        def index_placeholder():
            return HTMLResponse("<h1>lyric2resolve editor</h1><p>The editor UI arrives in Phase 7. "
                                "API docs: <a href='/docs'>/docs</a></p>")

    return app


def main(argv: list[str]) -> int:
    """lyric2resolve editor --project path/to/project.json [--port 8765] [--no-browser]"""
    import argparse
    import webbrowser

    from lyric2resolve.settings import load_settings

    s, _ = load_settings()
    ap = argparse.ArgumentParser(prog="lyric2resolve editor")
    ap.add_argument("--project", type=Path, required=True)
    ap.add_argument("--port", type=int, default=s.editor_port)
    ap.add_argument("--host", default=s.editor_host)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)
    try:
        session = EditorSession(args.project)
    except proj.ProjectError as exc:
        print(f"ERROR: {exc}")
        return 1
    import uvicorn

    url = f"http://{args.host}:{args.port}/"
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"Editor running at {url}  (Ctrl+C to stop)")
    uvicorn.run(create_app(session), host=args.host, port=args.port, log_level="warning")
    return 0
