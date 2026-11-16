"""One background render at a time, with pollable progress (used by the editor API and the MCP server)."""

from __future__ import annotations

import threading
import time
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Callable


class RenderJobs:
    def __init__(self, render_fn: Callable | None = None):
        if render_fn is None:
            from lyric2resolve.render import render_project as render_fn
        self._render = render_fn
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._state: dict = {"running": False, "started": None}

    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self, project_path: Path, template: str = "spectrum_bars", preset: str = "preview",
              aspects: list[str] | None = None, sections: list[str] | None = None,
              estimate_only: bool = False) -> dict:
        if self.running():
            raise RuntimeError("a render is already running - wait for it or cancel it first")
        self._cancel = threading.Event()
        with self._lock:
            self._state = {"running": True, "started": time.time(), "template": template, "preset": preset,
                           "aspects": aspects, "sections": sections, "estimate_only": estimate_only,
                           "aspect": None, "done": 0, "total": 0, "fraction": 0.0, "eta_s": None,
                           "log": [], "report": None, "error": ""}

        def log(msg: str) -> None:
            with self._lock:
                self._state["log"] = (self._state["log"] + [str(msg)])[-30:]

        def on_progress(aspect: str, pr) -> None:
            with self._lock:
                self._state.update(aspect=aspect, done=pr.done, total=pr.total, fraction=round(pr.fraction, 4),
                                   eta_s=pr.eta_s)

        def work() -> None:
            try:
                rep = self._render(Path(project_path), template=template, preset_name=preset, aspects=aspects,
                                   sections=sections, estimate_only=estimate_only, on_progress=on_progress,
                                   log=log, cancel=self._cancel)
                with self._lock:
                    self._state["report"] = asdict(rep) if hasattr(rep, "__dataclass_fields__") else rep
            except Exception as exc:  # shown to the user / Claude, never crashes the server
                with self._lock:
                    self._state["error"] = str(exc) or traceback.format_exc(limit=2)
            finally:
                with self._lock:
                    self._state["running"] = False
                    self._state["finished"] = time.time()

        self._thread = threading.Thread(target=work, daemon=True)
        self._thread.start()
        return self.progress()

    def progress(self) -> dict:
        with self._lock:
            return {**self._state, "log": list(self._state.get("log", []))}

    def cancel(self) -> dict:
        self._cancel.set()
        return self.progress()

    def wait(self, timeout: float | None = None) -> bool:
        if self._thread:
            self._thread.join(timeout)
        return not self.running()
