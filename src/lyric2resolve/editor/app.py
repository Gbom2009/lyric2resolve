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
from lyric2resolve import styling
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


def _apply_template(p: proj.Project, name: str) -> None:
    from lyric2resolve import templates

    templates.op_apply_template(p, name)


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
    "add_text": ops.add_text,
    "retime_block": ops.retime_block,
    "add_gap": ops.add_gap,
    "update_gap": ops.update_gap,
    "remove_gap": ops.remove_gap,
    "update_section": ops.update_section,
    "set_section_preset": _set_section_preset,
    "apply_presets": _apply_presets,
    "merge_short_blocks": presets.merge_short_blocks,
    "set_settings": _set_settings,
    "save_style": styling.op_save_style,
    "delete_style": styling.op_delete_style,
    "set_default_style": styling.op_set_default_style,
    "set_section_style": styling.op_set_section_style,
    "set_styling_level": styling.op_set_styling_level,
    "apply_template": lambda p, name: _apply_template(p, name),
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

    def layout_warnings(self) -> list[dict]:
        """Safe-area / line-length warnings per block and layout (warn only, never change)."""
        from lyric2resolve import layout

        cfg = self.project.settings
        out = []
        for b in self.project.blocks:
            text = presets.display_text(self.project, b)
            for lay in cfg.layouts:
                res = layout.check_text(text, lay, cfg.font_size_px or None, cfg.max_lines,
                                        cfg.width if lay == "16:9" else None, cfg.height if lay == "16:9" else None)
                if not res.ok:
                    out.append({"block_id": b.id, "layout": lay, "lines": res.lines, "message": res.message()})
        return out

    def styles_view(self) -> dict:
        book = styling.StyleBook.from_project(self.project.styles)
        return {"presets": {k: v.to_dict() for k, v in book.all().items()}, "builtin": list(styling.BUILTIN),
                "default": book.default, "by_section": book.by_section, "levels": list(styling.LEVELS),
                "animations": list(styling.ANIMATIONS)}

    def state(self) -> dict:
        return {"styles": self.styles_view(),"project": self.project.to_dict(), "blocks": self.blocks_view(), "flags": self.flags(),
                "layout_warnings": self.layout_warnings(),
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
            except (ops.OpError, ValueError, TypeError, proj.ProjectError, styling.StyleError, OSError) as exc:
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


def list_projects(projects_dir: Path) -> list[dict]:
    out = []
    for f in sorted(Path(projects_dir).glob(f"*/{proj.PROJECT_FILE}")):
        try:
            p = proj.load(f)
        except proj.ProjectError:
            continue
        out.append({"name": p.name, "path": str(f), "modified": p.modified, "words": len(p.words),
                    "blocks": len(p.blocks), "language": p.language})
    out.sort(key=lambda d: d["modified"], reverse=True)
    return out


def create_app(session: EditorSession | None = None, projects_dir: Path | None = None,
               fonts_root: Path | None = None, settings_dir: Path | None = None, textures_root: Path | None = None,
               assistant=None, jobs=None, update_checker=None, new_projects=None):
    """session: project opened at start (optional). projects_dir: folder offered in the project picker.
    assistant: claude_link.Assistant (optional Claude link); jobs: render.jobs.RenderJobs (background renders);
    update_checker: editor.settings_api.UpdateChecker (in-browser update banner)."""
    from fastapi import Body, FastAPI, HTTPException, Request
    from fastapi.responses import FileResponse, HTMLResponse
    from fastapi.staticfiles import StaticFiles

    app = FastAPI(title="lyric2resolve editor")
    holder: dict[str, EditorSession | None] = {"session": session}
    allowed: set[Path] = {session.path.resolve()} if session else set()
    app.state.holder = holder

    def current() -> EditorSession:
        s = holder["session"]
        if s is None:
            raise HTTPException(status_code=409, detail="no project open")
        return s

    @app.get("/api/projects")
    def projects():
        found = list_projects(projects_dir) if projects_dir else []
        cur = holder["session"]
        return {"projects": found, "current": str(cur.path) if cur else None,
                "projects_dir": str(projects_dir) if projects_dir else None}

    @app.post("/api/open")
    def open_project(body: dict = Body(...)):
        path = Path(str(body.get("path", ""))).resolve()
        inside = projects_dir is not None and Path(projects_dir).resolve() in path.parents
        if not (inside or path in allowed) or path.name != proj.PROJECT_FILE:
            raise HTTPException(status_code=403, detail="only projects from the projects folder can be opened")
        try:
            holder["session"] = EditorSession(path)
        except proj.ProjectError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        allowed.add(path)
        return holder["session"].state()

    @app.get("/api/state")
    def get_state():
        return current().state()

    @app.post("/api/op/{name}")
    def do_op(name: str, args: dict = Body(default_factory=dict)):
        try:
            return current().apply(name, args)
        except ops.OpError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/export/formats")
    def export_formats():
        from lyric2resolve import export as ex

        return {"formats": ex.ALL_FORMATS, "layouts": ["16:9", "9:16"]}

    @app.post("/api/export")
    def do_export(body: dict = Body(default_factory=dict)):
        from lyric2resolve import export as ex

        s = current()
        out = s.path.parent / "export"
        try:
            formats = body.get("formats") or ["fcpxml"]
            res = ex.export(s.project, out, formats, body.get("layouts") or None, body.get("beats") or "downbeats",
                            install_resolve_script="resolve" in formats)
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        res["folder"] = str(out)
        return res

    @app.post("/api/undo")
    def undo():
        return current().undo()

    @app.post("/api/redo")
    def redo():
        return current().redo()

    def _fonts_root() -> Path:
        from lyric2resolve.assets import fonts

        return Path(fonts_root) if fonts_root else fonts.fonts_dir()

    # ------------------------------------------------------------ karaoke (read-only, offline)
    def _karaoke_project(path: str) -> proj.Project:
        p = Path(path).resolve()
        inside = projects_dir is not None and Path(projects_dir).resolve() in p.parents
        if not (inside or p in allowed) or p.name != proj.PROJECT_FILE:
            raise HTTPException(status_code=403, detail="only projects from the projects folder can be played")
        cur = holder["session"]
        if cur is not None and cur.path.resolve() == p:
            return cur.project  # the open project, including unsaved-to-disk state
        try:
            return proj.load(p)
        except proj.ProjectError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/karaoke/data")
    def karaoke_data(path: str):
        from lyric2resolve import karaoke

        return karaoke.karaoke_data(_karaoke_project(path))

    @app.get("/api/karaoke/audio/{kind}")
    def karaoke_audio(kind: str, path: str):
        p = _karaoke_project(path)
        key = {"song": "song_wav", "vocals": "vocals_wav", "instrumental": "instrumental_wav"}.get(kind)
        f = Path(p.audio.get(key, "")) if key and p.audio.get(key) else None
        if f is None or not f.is_file():
            raise HTTPException(status_code=404, detail=f"no {kind} audio")
        return FileResponse(f, media_type="audio/wav")

    @app.get("/api/karaoke/playlists")
    def get_playlists():
        from lyric2resolve import karaoke

        return karaoke.load_playlists(settings_dir).to_dict()

    @app.put("/api/karaoke/playlists")
    def put_playlists(body: dict = Body(...)):
        from lyric2resolve import karaoke

        try:
            pls = karaoke.Playlists({str(k): [str(x) for x in v] for k, v in (body.get("playlists") or {}).items()},
                                    str(body.get("current", "")))
            karaoke.save_playlists(pls, settings_dir)
        except (ValueError, AttributeError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return pls.to_dict()

    def _textures_root() -> Path:
        from lyric2resolve.assets import textures

        return Path(textures_root) if textures_root else textures.textures_dir()

    @app.get("/api/textures")
    def texture_list():
        from lyric2resolve.assets import textures

        return {"textures": textures.list_textures(_textures_root()), "folder": str(_textures_root())}

    @app.get("/api/textures/file/{rel:path}")
    def texture_file(rel: str):
        root = _textures_root().resolve()
        path = (root / rel).resolve()
        if root not in path.parents or not path.is_file() or path.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            raise HTTPException(status_code=404, detail="image not found")
        return FileResponse(path)

    # ------------------------------------------------------------ visual ideas + templates
    @app.get("/api/ideas")
    def ideas():
        from lyric2resolve.assets import textures
        from lyric2resolve.visuals import brief as br
        from lyric2resolve.visuals import prompts

        s = current()
        b = br.build_brief(s.project)
        tex = textures.list_textures(_textures_root())
        lay = list(s.project.settings.layouts)
        fps = s.project.settings.fps
        return {"brief": b.to_dict(), "markdown": prompts.brief_markdown(b),
                "blender_prompt": prompts.blender_prompt(b, fps, lay, tex, textures_root=str(_textures_root())),
                "threejs_prompt": prompts.threejs_prompt(b, fps, lay, tex)}

    @app.get("/api/templates")
    def template_list():
        from lyric2resolve import templates

        return {"templates": templates.list_templates(), "current": (holder["session"].project.extra.get("template")
                                                                     if holder["session"] else None)}

    @app.post("/api/templates/save")
    def template_save(body: dict = Body(...)):
        from lyric2resolve import templates

        try:
            path = templates.save(current().project, str(body.get("name", "")))
        except templates.TemplateError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"saved": str(path), "templates": templates.list_templates()}

    @app.get("/api/fonts")
    def font_list():
        from lyric2resolve.assets import fonts

        return {"fonts": fonts.list_fonts(_fonts_root())}

    @app.get("/api/fonts/file/{rel:path}")
    def font_file(rel: str):
        root = _fonts_root().resolve()
        path = (root / rel).resolve()
        if root not in path.parents or path.suffix.lower() not in (".ttf", ".otf") or not path.is_file():
            raise HTTPException(status_code=404, detail="font not found")
        return FileResponse(path, media_type="font/ttf" if path.suffix.lower() == ".ttf" else "font/otf")

    # ------------------------------------------------------------ background render (UI + MCP server)
    def _jobs():
        nonlocal jobs
        if jobs is None:
            from lyric2resolve.render.jobs import RenderJobs

            jobs = RenderJobs()
        return jobs

    @app.post("/api/render")
    def render_start(body: dict = Body(default_factory=dict)):
        allowed_keys = {"template", "preset", "aspects", "sections", "estimate_only"}
        args = {k: v for k, v in body.items() if k in allowed_keys and v is not None}
        try:
            return _jobs().start(current().path, **args)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/render/progress")
    def render_progress():
        return _jobs().progress()

    @app.post("/api/render/cancel")
    def render_cancel():
        return _jobs().cancel()

    # ------------------------------------------------------------ Claude link (optional Assistant)
    def _assistant():
        nonlocal assistant
        if assistant is None:
            from lyric2resolve.claude_link import Assistant

            assistant = Assistant(settings_dir=settings_dir)
        return assistant

    @app.get("/api/assistant/status")
    def assistant_status():
        return _assistant().status()

    @app.get("/api/assistant/history")
    def assistant_history():
        return _assistant().history(current().path)

    def assistant_send(request, body: dict = Body(...)):
        s = current()
        a = _assistant()
        a.editor_url = str(request.base_url)  # the MCP server edits through this editor (shared undo)
        try:
            return a.send(s.path, str(body.get("message", "")), s.project)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=424, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # real class (not a string) so FastAPI injects the request despite `from __future__ import annotations`
    assistant_send.__annotations__["request"] = Request
    app.post("/api/assistant/send")(assistant_send)

    @app.get("/api/assistant/events")
    def assistant_events(after: int = 0):
        return _assistant().poll(after)

    @app.post("/api/assistant/cancel")
    def assistant_cancel():
        _assistant().cancel()
        return _assistant().poll(0)

    @app.post("/api/assistant/reset")
    def assistant_reset():
        if _assistant().busy():
            raise HTTPException(status_code=409, detail="wait until the Assistant has finished")
        _assistant().reset(current().path)
        return _assistant().history(current().path)

    @app.get("/api/audio/{kind}")
    def audio(kind: str):
        path = current().audio_path(kind)
        if path is None:
            raise HTTPException(status_code=404, detail=f"no {kind} audio in this project")
        return FileResponse(path, media_type="audio/wav")

    # ------------------------------------------------------------ new project from the browser
    from . import newproject

    def _new_jobs():
        nonlocal new_projects
        if new_projects is None:
            if projects_dir is None:
                raise HTTPException(status_code=409, detail="no projects folder configured")
            new_projects = newproject.NewProjectJobs(projects_dir, settings_dir=settings_dir)
        return new_projects

    def _open_new(path: Path) -> dict:
        path = path.resolve()
        holder["session"] = EditorSession(path)
        allowed.add(path)
        return holder["session"].state()

    newproject.register(app, _new_jobs, _open_new)

    from . import settings_api
    from lyric2resolve.assets import fonts as _fonts_mod

    settings_api.register(app, settings_dir, lambda: _fonts_mod.list_fonts(_fonts_root()), STATIC_DIR,
                          update_checker)

    if (STATIC_DIR / "index.html").exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

        @app.get("/")
        def index():
            return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-store"})

        @app.get("/library")
        def library_page():
            return FileResponse(STATIC_DIR / "library.html", headers={"Cache-Control": "no-store"})

        @app.get("/ideas")
        def ideas_page():
            return FileResponse(STATIC_DIR / "ideas.html", headers={"Cache-Control": "no-store"})

        @app.get("/karaoke")
        def karaoke_page():
            return FileResponse(STATIC_DIR / "karaoke.html", headers={"Cache-Control": "no-store"})
    else:  # pragma: no cover - only before the frontend existed
        @app.get("/")
        def index_placeholder():
            return HTMLResponse("<h1>lyric2resolve editor</h1><p><a href='/docs'>API docs</a></p>")

    return app


def main(argv: list[str]) -> int:
    """lyric2resolve editor --project path/to/project.json [--port 8765] [--no-browser]"""
    import argparse
    import webbrowser

    from lyric2resolve.settings import load_settings

    s, _ = load_settings()
    ap = argparse.ArgumentParser(prog="lyric2resolve editor")
    ap.add_argument("--project", type=Path, help="project.json to open (default: show the project list)")
    ap.add_argument("--port", type=int, default=s.editor_port)
    ap.add_argument("--host", default=s.editor_host)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)
    from lyric2resolve import paths

    session = None
    if args.project:
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
    uvicorn.run(create_app(session, paths.ensure_data_dir() / "projects"), host=args.host, port=args.port, log_level="warning")
    return 0
