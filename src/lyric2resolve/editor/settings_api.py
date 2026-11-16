"""Settings page API, theme CSS, and the in-browser update banner (same updater logic as the launcher)."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Callable

from lyric2resolve import branding, paths, settings as st, setup_tools

PERMISSION_LABELS = {"": "CLI default", "default": "default", "acceptEdits": "accept edits", "plan": "plan only",
                     "dontAsk": "don't ask (deny)", "auto": "auto"}
CHECK_EVERY_S = 30 * 60


class UpdateChecker:
    """Runs the updater's check in the background; the browser polls the cached result."""

    def __init__(self, repo: Path | None = None, settings_dir: Path | None = None, check: Callable | None = None):
        self.repo = Path(repo) if repo else paths.code_dir()
        self.settings_dir = settings_dir
        self._check = check
        self._lock = threading.Lock()
        self._result: dict = {"state": "not_checked"}
        self._when = 0.0
        self._thread: threading.Thread | None = None

    def _run(self) -> None:
        try:
            if self._check is not None:
                res = self._check()
            else:
                from lyric2resolve.updater import changelog, core
                from lyric2resolve.updater.config import load_config
                from lyric2resolve.updater.gitops import Git

                git = Git(self.repo)
                status = core.check_for_update(git, load_config(self.settings_dir))
                res = {"state": status.state, "behind": status.behind, "ahead": status.ahead,
                       "commits": status.commits[:20], "dirty": status.dirty, "message": status.message,
                       "changelog": changelog.render_entries(status.changelog_entries),
                       "update_available": status.update_available, "version": core.version_label(git)}
        except Exception as exc:  # never break the editor because of the updater
            res = {"state": "error", "message": str(exc)}
        with self._lock:
            self._result = res
            self._when = time.time()

    def status(self, refresh: bool = False, wait: float = 0.0) -> dict:
        if os.environ.get("L2R_NO_UPDATE_CHECK") == "1" and self._check is None:  # tests / dev servers
            return {"state": "disabled", "message": "update check disabled (L2R_NO_UPDATE_CHECK=1)",
                    "checking": False, "via_launcher": False}
        stale = time.time() - self._when > CHECK_EVERY_S
        if (refresh or stale) and not (self._thread and self._thread.is_alive()):
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        if wait and self._thread:
            self._thread.join(wait)
        with self._lock:
            out = dict(self._result)
        out["checking"] = bool(self._thread and self._thread.is_alive())
        out["checked_at"] = self._when or None
        out["via_launcher"] = os.environ.get("L2R_LAUNCHER") == "1"
        return out


_probe_cache: dict = {}


def detect_tools(s: st.AppSettings, probe=setup_tools.run_probe, ttl: float = 60.0) -> dict:
    """ffmpeg / Blender / Claude Code paths + versions and NVIDIA GPU (cached for a minute: probing is slow)."""
    key = (s.ffmpeg_path, s.blender_path, s.claude_cli_path)
    hit = _probe_cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    from lyric2resolve.claude_link import cli

    out = {}
    for tool, conf, help_ in (("ffmpeg", s.ffmpeg_path, setup_tools.FFMPEG_HELP),
                              ("blender", s.blender_path, setup_tools.BLENDER_HELP)):
        exe = setup_tools.find_tool(tool, conf)
        out[tool] = {"path": str(exe or ""), "version": setup_tools.tool_version(exe, probe) if exe else "",
                     "help": "" if exe else help_}
    cs = cli.status(s.claude_cli_path)
    out["claude"] = {"path": cs.path, "version": cs.version, "help": "" if cs.installed else cs.message}
    out["gpu"] = setup_tools.detect_gpu(probe).describe()
    _probe_cache[key] = (time.time(), out)
    return out


def register(app, settings_dir: Path | None, fonts_list: Callable[[], list[dict]], static_dir: Path,
             checker: UpdateChecker | None = None) -> None:
    from fastapi import Body, HTTPException
    from fastapi.responses import FileResponse, Response

    checker = checker or UpdateChecker(settings_dir=settings_dir)
    app.state.update_checker = checker

    def sdir() -> Path:
        return Path(settings_dir) if settings_dir else paths.settings_dir()

    def view(s: st.AppSettings, warnings: list[str]) -> dict:
        from lyric2resolve.updater.config import load_config

        try:
            brand = branding.load_brand(settings_dir=settings_dir)
            brand_info = {"name": brand.name, "logo": brand.logo, "source": brand.source,
                          "video_text_style": brand.video_text_style, "error": ""}
        except branding.BrandError as exc:
            brand_info = {"error": str(exc)}
        return {"settings": s.to_dict(), "warnings": warnings, "data_dir": str(paths.data_dir()),
                "brand_file": str(branding.user_brand_path(settings_dir)),
                "choices": {"fps": list(st.FPS_CHOICES), "styling_level": list(st.STYLING_LEVELS),
                            "whisper_model": list(st.WHISPER_MODELS), "theme": list(st.THEMES),
                            "device": ["cuda", "cpu"], "claude_permission_mode": PERMISSION_LABELS},
                "updater": load_config(settings_dir).to_dict(), "brand": brand_info}

    @app.get("/api/settings")
    def get_settings(probe: bool = True):
        s, warnings = st.load_settings(settings_dir)
        out = view(s, warnings)
        if probe:
            out["detected"] = detect_tools(s)
        return out

    @app.put("/api/settings")
    def put_settings(body: dict = Body(...)):
        s, _ = st.load_settings(settings_dir)
        data = s.to_dict()
        known = set(st.AppSettings.__dataclass_fields__) - {"extra", "schema_version"}
        unknown = sorted(set(body) - known)
        if unknown:
            raise HTTPException(status_code=400, detail=f"unknown settings {unknown}")
        data.update(body)
        try:
            new = st.AppSettings.from_dict(data)
        except TypeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        warnings = new.validate()
        st.save_settings(new, settings_dir)
        _probe_cache.clear()
        return view(new, warnings)

    @app.put("/api/settings/updater")
    def put_updater(body: dict = Body(...)):
        from lyric2resolve.updater.config import UpdaterConfig, load_config, save_config

        cur = load_config(settings_dir).to_dict()
        allowed = {"branch", "check_at_launch", "check_at_login", "fetch_timeout_s", "keep_rollback_tags"}
        bad = sorted(set(body) - allowed)
        if bad:
            raise HTTPException(status_code=400, detail=f"cannot change {bad} here")
        cur.update(body)
        try:
            cfg = UpdaterConfig.from_dict(cur)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        save_config(cfg, settings_dir)
        note = ""
        if "check_at_login" in body:
            note = ("To switch the login check on/off in Windows, use: .venv\\Scripts\\python.exe launcher.pyw "
                    f"login-check {'on' if cfg.check_at_login else 'off'}")
        return {"updater": cfg.to_dict(), "note": note}

    # ------------------------------------------------------------ update banner
    @app.get("/api/update/status")
    def update_status(refresh: bool = False):
        return checker.status(refresh)

    @app.post("/api/update/request")
    def update_request():
        cur = checker.status()
        if not cur.get("update_available"):
            raise HTTPException(status_code=409, detail="no update available (check again first)")
        if not cur.get("via_launcher"):
            raise HTTPException(status_code=409, detail="The editor was not started from the launcher. Close it and "
                                                        "open the lyric2resolve shortcut to update.")
        from lyric2resolve.updater import appctl

        appctl.request_update(sdir())
        return {"requested": True, "message": "The launcher now stops the editor, updates (with automatic "
                                              "rollback on problems) and shows what changed."}

    # ------------------------------------------------------------ theme
    @app.get("/theme.css")
    def theme_css():
        s, _ = st.load_settings(settings_dir)
        fonts = fonts_list() if branding.branding_on(s) else []
        return Response(branding.current_css(s, settings_dir, fonts), media_type="text/css",
                        headers={"Cache-Control": "no-store"})

    @app.get("/settings")
    def settings_page():
        return FileResponse(static_dir / "settings.html", headers={"Cache-Control": "no-store"})

    @app.get("/api/brand")
    def brand():
        """Brand info (+ its video text style, which the settings page saves as a style via the normal op)."""
        return view(st.load_settings(settings_dir)[0], [])["brand"]
