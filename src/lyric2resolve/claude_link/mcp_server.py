"""The app's own MCP server (stdio, JSON-RPC 2.0, newline-delimited) so Claude can work inside the app.

Started by Claude Code from the generated MCP config:
    python -m lyric2resolve.claude_link.mcp_server --project <project.json> [--editor-url http://127.0.0.1:PORT/]

Backends: with --editor-url every change goes through the running editor's API (the editor stays the
single owner of the project, with undo, and the browser shows the changes); without it the server
edits project.json directly (standalone use, e.g. `claude` started by hand in the project folder).
Stdlib only (no `mcp` package needed): implements initialize, ping, tools/list, tools/call.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

SERVER_INFO = {"name": "lyric2resolve", "version": "0.17"}
PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
INSTRUCTIONS = ("Tools to read and edit the open lyric2resolve project (lyric words/blocks with timings, "
                "instrumental gaps, sections, text styles), check sanity flags, export to Resolve formats and "
                "run Blender preview renders. Times are in seconds. Every edit can be undone with `undo`.")


class ToolError(Exception):
    pass


# ------------------------------------------------------------------ backends
class FileBackend:
    """Edits project.json in-process via the editor's EditorSession (same ops, undo, validation)."""

    def __init__(self, project_path: Path, jobs=None):
        from lyric2resolve.editor.app import EditorSession

        self.path = Path(project_path)
        self.session = EditorSession(self.path)
        self._jobs = jobs

    @property
    def jobs(self):
        if self._jobs is None:
            from lyric2resolve.render.jobs import RenderJobs

            self._jobs = RenderJobs()
        return self._jobs

    def state(self) -> dict:
        return self.session.state()

    def op(self, name: str, args: dict) -> dict:
        from lyric2resolve.editor import ops

        try:
            return self.session.apply(name, args)
        except ops.OpError as exc:
            raise ToolError(str(exc)) from exc

    def undo(self) -> dict:
        return self.session.undo()

    def redo(self) -> dict:
        return self.session.redo()

    def export(self, formats: list[str], layouts: list[str] | None) -> dict:
        from lyric2resolve import export as ex

        out = self.path.parent / "export"
        try:
            res = ex.export(self.session.project, out, formats, layouts or None, "downbeats",
                            install_resolve_script="resolve" in formats)
        except (RuntimeError, ValueError) as exc:
            raise ToolError(str(exc)) from exc
        res["folder"] = str(out)
        return res

    def textures(self) -> list[dict]:
        from lyric2resolve.assets import textures

        return textures.list_textures()

    def fonts(self) -> list[dict]:
        from lyric2resolve.assets import fonts

        return fonts.list_fonts()

    def render_start(self, body: dict) -> dict:
        try:
            return self.jobs.start(self.path, **body)
        except RuntimeError as exc:
            raise ToolError(str(exc)) from exc

    def render_progress(self) -> dict:
        return self.jobs.progress()

    def render_cancel(self) -> dict:
        return self.jobs.cancel()


class HttpBackend:
    """Talks to the running editor (127.0.0.1) so the browser and Claude share one project + undo stack."""

    def __init__(self, base_url: str, project_path: Path, timeout: float = 120):
        self.base = base_url.rstrip("/") + "/"
        self.path = Path(project_path)
        self.timeout = timeout

    def _call(self, method: str, route: str, body: Any = None) -> Any:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(urllib.parse.urljoin(self.base, route.lstrip("/")), data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8") or "null")
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("detail", "")
            except (ValueError, AttributeError):
                detail = ""
            raise ToolError(detail or f"editor answered HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise ToolError(f"the editor is not reachable at {self.base} ({exc.reason}); is the app running?") from exc

    def _ensure_open(self) -> None:
        cur = (self._call("GET", "api/projects") or {}).get("current")
        if not cur or Path(cur).resolve() != self.path.resolve():
            self._call("POST", "api/open", {"path": str(self.path)})

    def state(self) -> dict:
        self._ensure_open()
        return self._call("GET", "api/state")

    def op(self, name: str, args: dict) -> dict:
        self._ensure_open()
        return self._call("POST", f"api/op/{name}", args)

    def undo(self) -> dict:
        self._ensure_open()
        return self._call("POST", "api/undo", {})

    def redo(self) -> dict:
        self._ensure_open()
        return self._call("POST", "api/redo", {})

    def export(self, formats: list[str], layouts: list[str] | None) -> dict:
        self._ensure_open()
        return self._call("POST", "api/export", {"formats": formats, "layouts": layouts})

    def textures(self) -> list[dict]:
        return self._call("GET", "api/textures").get("textures", [])

    def fonts(self) -> list[dict]:
        return self._call("GET", "api/fonts").get("fonts", [])

    def render_start(self, body: dict) -> dict:
        self._ensure_open()
        return self._call("POST", "api/render", body)

    def render_progress(self) -> dict:
        return self._call("GET", "api/render/progress")

    def render_cancel(self) -> dict:
        return self._call("POST", "api/render/cancel", {})


# ------------------------------------------------------------------ views (compact, for the model)
def _r(t: Any) -> Any:
    return round(t, 3) if isinstance(t, float) else t


def summary(state: dict) -> dict:
    p = state["project"]
    a = p.get("analysis") or {}
    st = p.get("settings") or {}
    styles = state.get("styles") or {}
    return {
        "name": p.get("name"), "language": p.get("language"), "words": len(p.get("words", [])),
        "blocks": len(state.get("blocks", [])), "flags": len(state.get("flags", [])),
        "layout_warnings": len(state.get("layout_warnings", [])),
        "analysis": {k: _r(a.get(k)) for k in ("bpm", "key", "duration") if k in a},
        "sections": [{"id": s["id"], "label": s["label"], "start": _r(s["start"]), "end": _r(s["end"]),
                      "preset": s.get("preset"), "style": s.get("style")} for s in p.get("sections", [])],
        "gaps": [{"id": g["id"], "start": _r(g["start"]), "end": _r(g["end"]), "source": g.get("source")}
                 for g in p.get("gaps", [])],
        "settings": {k: st.get(k) for k in ("fps", "layouts", "case", "max_chars", "styling_level", "granularity",
                                            "sync_offset_ms") if k in st},
        "styles": {"default": styles.get("default"), "by_section": styles.get("by_section"),
                   "available": sorted((styles.get("presets") or {}).keys())},
        "history": state.get("history"), "problems": state.get("problems"),
    }


def _window(items: list[dict], start: float | None, end: float | None, limit: int, offset: int) -> dict:
    sel = [x for x in items if (start is None or x["end"] >= start) and (end is None or x["start"] <= end)]
    page = sel[offset: offset + limit]
    return {"total": len(sel), "offset": offset, "items": page, "more": offset + len(page) < len(sel)}


def blocks_view(state: dict, start=None, end=None, limit=200, offset=0) -> dict:
    items = [{"id": b["id"], "start": _r(b["start"]), "end": _r(b["end"]), "text": b["display"],
              "word_ids": b["word_ids"], **({"style": b["style"]} if b.get("style") else {})}
             for b in state.get("blocks", [])]
    return _window(items, start, end, limit, offset)


def words_view(state: dict, start=None, end=None, limit=300, offset=0) -> dict:
    block_of = {w: b["id"] for b in state.get("blocks", []) for w in b["word_ids"]}
    items = [{"id": w["id"], "text": w["text"], "start": _r(w["start"]), "end": _r(w["end"]),
              "conf": _r(w.get("confidence")), "block": block_of.get(w["id"])}
             for w in state["project"].get("words", [])]
    return _window(items, start, end, limit, offset)


def after_edit(state: dict) -> dict:
    return {"ok": True, "blocks": len(state.get("blocks", [])), "flags": len(state.get("flags", [])),
            "layout_warnings": len(state.get("layout_warnings", [])), "problems": state.get("problems"),
            "can_undo": (state.get("history") or {}).get("can_undo")}


# ------------------------------------------------------------------ tools
def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or [], "additionalProperties": False}


NUM, STR, BOOL = {"type": "number"}, {"type": "string"}, {"type": "boolean"}
STRS = {"type": "array", "items": {"type": "string"}}
RANGE = {"start": {**NUM, "description": "seconds (optional)"}, "end": {**NUM, "description": "seconds (optional)"},
         "limit": {"type": "integer"}, "offset": {"type": "integer"}}
EDIT_OPS = ("merge_words", "merge_blocks", "split_block", "split_block_words", "move_word", "remove_block",
            "set_block_text", "set_block_style", "set_word_text", "set_word_timing", "nudge_words", "nudge_block",
            "add_gap", "update_gap", "remove_gap", "update_section", "set_section_preset", "apply_presets",
            "merge_short_blocks", "set_settings", "save_style", "delete_style", "set_default_style",
            "set_section_style", "set_styling_level", "apply_template")


class Tool:
    def __init__(self, name: str, description: str, schema: dict, fn: Callable[..., Any]):
        self.name, self.description, self.schema, self.fn = name, description, schema, fn

    def spec(self) -> dict:
        return {"name": self.name, "description": self.description, "inputSchema": self.schema}


def build_tools(be) -> dict[str, Tool]:
    def op(name: str, **args) -> dict:
        return after_edit(be.op(name, {k: v for k, v in args.items() if v is not None}))

    def set_style(name: str, style: dict | None = None, section_label: str | None = None,
                  block_id: str | None = None, make_default: bool = False) -> dict:
        state = None
        if style is not None:
            from lyric2resolve.styling import TextStyle

            valid = set(TextStyle.__dataclass_fields__)
            unknown = sorted(set(style) - valid)
            if unknown:
                raise ToolError(f"unknown style fields {unknown}; valid fields: {', '.join(sorted(valid))}")
            state = be.op("save_style", {"name": name, "style": style})
        if section_label:
            state = be.op("set_section_style", {"section_label": section_label, "name": name})
        if block_id:
            state = be.op("set_block_style", {"block_id": block_id, "style": name})
        if make_default:
            state = be.op("set_default_style", {"name": name})
        if state is None:
            raise ToolError("give a style dict to save and/or where to use it (section_label, block_id, make_default)")
        return after_edit(state)

    def export(formats: list[str] | None = None, layouts: list[str] | None = None) -> dict:
        return be.export(formats or ["fcpxml"], layouts)

    def preview_render(template: str = "spectrum_bars", preset: str = "preview", aspects: list[str] | None = None,
                       sections: list[str] | None = None, estimate_only: bool = False) -> dict:
        return be.render_start({"template": template, "preset": preset, "aspects": aspects, "sections": sections,
                                "estimate_only": estimate_only})

    def edit_project(op: str, args: dict | None = None) -> dict:
        if op not in EDIT_OPS:
            raise ToolError(f"unknown op {op}; use one of {', '.join(EDIT_OPS)}")
        return after_edit(be.op(op, args or {}))

    tools = [
        Tool("get_project", "Overview of the open project: counts, BPM/key, sections, gaps, settings, styles, undo state.",
             _obj({}), lambda: summary(be.state())),
        Tool("list_blocks", "Text blocks (what becomes one title clip) with timings and word ids. Filter by time.",
             _obj(RANGE), lambda **k: blocks_view(be.state(), **k)),
        Tool("list_words", "Atomic words (text, start, end, confidence, block). Filter by time.",
             _obj(RANGE), lambda **k: words_view(be.state(), **k)),
        Tool("get_flags", "Rough-cut sanity flags (likely Whisper mistakes) and safe-area/line-length warnings.",
             _obj({}), lambda: {k: v for k, v in be.state().items() if k in ("flags", "layout_warnings")}),
        Tool("merge_words", "Merge consecutive words into ONE block (start = first word, end = last word).",
             _obj({"word_ids": STRS}, ["word_ids"]), lambda word_ids: op("merge_words", word_ids=word_ids)),
        Tool("split_block", "Split a block before the given word (each word keeps its own timing).",
             _obj({"block_id": STR, "before_word_id": STR}, ["block_id", "before_word_id"]),
             lambda block_id, before_word_id: op("split_block", block_id=block_id, before_word_id=before_word_id)),
        Tool("move_word", "Move a block's first/last word to the neighbouring block. direction: 'prev' or 'next'.",
             _obj({"word_id": STR, "direction": STR}, ["word_id", "direction"]),
             lambda word_id, direction: op("move_word", word_id=word_id, direction=direction)),
        Tool("set_block_text", "Override the displayed text of a block (null = back to the words' text).",
             _obj({"block_id": STR, "text": {"type": ["string", "null"]}}, ["block_id"]),
             lambda block_id, text=None: after_edit(be.op("set_block_text", {"block_id": block_id, "text": text}))),
        Tool("set_word_text", "Correct the text of one word (e.g. a Whisper mistake).",
             _obj({"word_id": STR, "text": STR}, ["word_id", "text"]),
             lambda word_id, text: op("set_word_text", word_id=word_id, text=text)),
        Tool("set_word_timing", "Set a word's start and/or end time in seconds.",
             _obj({"word_id": STR, "start": NUM, "end": NUM}, ["word_id"]),
             lambda word_id, start=None, end=None: op("set_word_timing", word_id=word_id, start=start, end=end)),
        Tool("add_gap", "Add an instrumental gap region (no text clips are exported inside gaps).",
             _obj({"start": NUM, "end": NUM}, ["start", "end"]), lambda start, end: op("add_gap", start=start, end=end)),
        Tool("remove_gap", "Remove an instrumental gap region.", _obj({"gap_id": STR}, ["gap_id"]),
             lambda gap_id: op("remove_gap", gap_id=gap_id)),
        Tool("apply_section_presets",
             "Rebuild blocks from presets. preset per section (word|line|phrase|auto) via set_section_preset first; "
             "'default' sets the preset for sections without one; section_id limits it to one section.",
             _obj({"default": STR, "section_id": STR, "merge_short": BOOL}),
             lambda **k: op("apply_presets", **k)),
        Tool("set_section_preset", "Set the block preset for one section: word, line, phrase, auto (null = default).",
             _obj({"section_id": STR, "preset": {"type": ["string", "null"]}}, ["section_id"]),
             lambda section_id, preset=None: after_edit(be.op("set_section_preset",
                                                              {"section_id": section_id, "preset": preset}))),
        Tool("list_styles", "Text style presets (font, size, colors, outline, shadow, glow, position, animation).",
             _obj({}), lambda: be.state().get("styles", {})),
        Tool("set_style",
             "Save a style preset and/or use it for a section label (e.g. 'chorus'), one block, or as the default. "
             "style fields (see list_styles for full examples): font_family, font_style, size_px (0 = auto), fill "
             "(#rrggbb), outline_color, outline_width, shadow_color, shadow_opacity, glow_color, glow_size, align, "
             "position_y_16x9, position_y_9x16, animation_in, animation_out, animation_ms. Built-in names cannot be "
             "overwritten; omit style to just assign an existing one.",
             _obj({"name": STR, "style": {"type": "object"}, "section_label": STR, "block_id": STR,
                   "make_default": BOOL}, ["name"]), set_style),
        Tool("set_styling_level", "How much styling the Resolve script applies: basic, styled or full.",
             _obj({"level": STR}, ["level"]), lambda level: op("set_styling_level", level=level)),
        Tool("edit_project", "Run any editor operation by name: " + ", ".join(EDIT_OPS) + ".",
             _obj({"op": STR, "args": {"type": "object"}}, ["op"]), edit_project),
        Tool("undo", "Undo the last edit.", _obj({}), lambda: after_edit(be.undo())),
        Tool("redo", "Redo the last undone edit.", _obj({}), lambda: after_edit(be.redo())),
        Tool("export", "Export the timeline. formats: fcpxml (Resolve import), resolve (Text+ build script job), "
                       "srt_csv_edl (SRT line + word, CSV, EDL with markers). "
                       "layouts: 16:9 and/or 9:16 (default: the project's layouts).",
             _obj({"formats": STRS, "layouts": STRS}), export),
        Tool("preview_render", "Start a Blender render in the background (default: low-res PREVIEW). "
                               "templates: spectrum_bars, pulsing_blob, tunnel, particle_field, floor_grid; presets: "
                               "preview, draft, standard, high, ultra. estimate_only = only time/disk estimate.",
             _obj({"template": STR, "preset": STR, "aspects": STRS, "sections": STRS, "estimate_only": BOOL}),
             preview_render),
        Tool("render_progress", "Progress of the background render (frames done/total, ETA, log, result).",
             _obj({}), lambda: be.render_progress()),
        Tool("cancel_render", "Cancel the background render (it can be resumed later).", _obj({}),
             lambda: be.render_cancel()),
        Tool("list_textures", "CC0 textures/HDRIs in the library (name, kind, source, path).", _obj({}),
             lambda: {"textures": be.textures()}),
        Tool("list_fonts", "Fonts in the font library (family, license, files).", _obj({}),
             lambda: {"fonts": be.fonts()}),
    ]
    return {t.name: t for t in tools}


# ------------------------------------------------------------------ JSON-RPC
class McpServer:
    def __init__(self, backend, tools: dict[str, Tool] | None = None):
        self.backend = backend
        self.tools = tools or build_tools(backend)

    def handle(self, msg: dict) -> dict | None:
        """One JSON-RPC message -> response (None for notifications)."""
        mid = msg.get("id")
        method = msg.get("method", "")
        params = msg.get("params") or {}
        if mid is None:  # notification (e.g. notifications/initialized, notifications/cancelled)
            return None
        try:
            if method == "initialize":
                want = str(params.get("protocolVersion", ""))
                result = {"protocolVersion": want if want in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
                          "capabilities": {"tools": {"listChanged": False}}, "serverInfo": SERVER_INFO,
                          "instructions": INSTRUCTIONS}
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": [t.spec() for t in self.tools.values()]}
            elif method == "tools/call":
                result = self.call_tool(str(params.get("name", "")), params.get("arguments") or {})
            else:
                return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"unknown method {method}"}}
        except Exception as exc:  # protocol-level failure; tool errors are returned as isError results
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": str(exc)}}
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def call_tool(self, name: str, args: dict) -> dict:
        tool = self.tools.get(name)
        if tool is None:
            return _tool_result(f"unknown tool {name}", True)
        try:
            out = tool.fn(**args)
        except ToolError as exc:
            return _tool_result(str(exc), True)
        except TypeError as exc:
            return _tool_result(f"bad arguments for {name}: {exc}", True)
        except Exception as exc:  # keep the server alive whatever happens
            return _tool_result(f"{type(exc).__name__}: {exc}", True)
        return _tool_result(json.dumps(out, ensure_ascii=False, default=str), False)

    def serve(self, stdin=None, stdout=None) -> None:
        stdin = stdin or sys.stdin
        stdout = stdout or sys.stdout
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
            else:
                batch = msg if isinstance(msg, list) else [msg]
                resps = [r for r in (self.handle(m) for m in batch if isinstance(m, dict)) if r is not None]
                if not resps:
                    continue
                resp = resps if isinstance(msg, list) else resps[0]
            stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            stdout.flush()


def _tool_result(text: str, is_error: bool) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lyric2resolve mcp-server")
    ap.add_argument("--project", type=Path, required=True)
    ap.add_argument("--editor-url", default="")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
        sys.stdin.reconfigure(encoding="utf-8")
    backend = HttpBackend(a.editor_url, a.project) if a.editor_url else FileBackend(a.project)
    McpServer(backend).serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
