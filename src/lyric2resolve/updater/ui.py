"""Tkinter windows for the launcher and the update process.

Thin layer only: all decisions and texts come from core.py / messages.py.
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

from lyric2resolve import paths

from . import core, messages
from .config import load_config
from .gitops import Git

BG = "#f7f7f5"
FG = "#111111"
ACCENT = "#0b5cad"
FONT = ("Segoe UI", 10) if sys.platform.startswith("win") else ("Helvetica", 10)
TITLE_FONT = (FONT[0], 13, "bold")


def _tk():
    import tkinter as tk
    from tkinter import messagebox, scrolledtext, ttk

    return tk, ttk, scrolledtext, messagebox


def open_folder(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


class _Base:
    def __init__(self, title: str, master=None):
        tk, ttk, self.scrolledtext, self.messagebox = _tk()
        self.tk, self.ttk = tk, ttk
        # master: optional existing Tk root (tests share one interpreter; Windows Tk dislikes many)
        self.root = tk.Toplevel(master) if master is not None else tk.Tk()
        self.root.title(title)
        self.root.configure(bg=BG)
        self.root.minsize(520, 200)
        self.q: queue.Queue = queue.Queue()
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TButton", font=FONT, padding=6)
        style.configure("Accent.TButton", font=(FONT[0], FONT[1], "bold"), foreground="white", background=ACCENT)
        self.frame = None
        self.root.after(100, self._poll)

    def clear(self):
        if self.frame is not None:
            self.frame.destroy()
        self.frame = self.tk.Frame(self.root, bg=BG, padx=18, pady=14)
        self.frame.pack(fill="both", expand=True)
        return self.frame

    def label(self, parent, text, title=False, wrap=560):
        lbl = self.tk.Label(parent, text=text, bg=BG, fg=FG, justify="left", anchor="w", wraplength=wrap,
                            font=TITLE_FONT if title else FONT)
        lbl.pack(fill="x", pady=(0, 8))
        return lbl

    def textbox(self, parent, content, height=16):
        box = self.scrolledtext.ScrolledText(parent, wrap="word", height=height, font=FONT, bg="white", fg=FG,
                                             relief="solid", borderwidth=1)
        box.insert("1.0", content)
        box.configure(state="disabled")
        box.pack(fill="both", expand=True, pady=(0, 10))
        return box

    def buttons(self, parent, spec):
        row = self.tk.Frame(parent, bg=BG)
        row.pack(fill="x")
        for i, (text, cmd) in enumerate(spec):
            self.ttk.Button(row, text=text, command=cmd, style="Accent.TButton" if i == 0 else "TButton").pack(
                side="left", padx=(0, 8))
        return row

    def run_bg(self, fn, tag):
        threading.Thread(target=lambda: self.q.put((tag, fn())), daemon=True).start()

    def _poll(self):
        try:
            while True:
                tag, payload = self.q.get_nowait()
                self.on_message(tag, payload)
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def on_message(self, tag, payload):  # pragma: no cover - overridden
        pass


class LauncherWindow(_Base):
    def __init__(self, repo: Path, skip_check: bool = False, login_check: bool = False, master=None,
                 auto_start: bool = True):
        super().__init__("lyric2resolve", master)
        self.repo, self.git, self.cfg = repo, Git(repo), load_config()
        self.login_check = login_check
        self.version = core.version_label(self.git)
        self.auto_start = auto_start and not login_check
        self.server = None            # editor subprocess
        self.app_state = "idle"       # idle | checking | starting | running | needs_setup | failed
        self.app_detail = ""
        self.url = ""
        self.last_status = None
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        if login_check:
            self.root.withdraw()
        if login_check or (self.cfg.check_at_launch and not skip_check):
            self.check_now()
        else:
            self.show_status(core.UpdateStatus(core.UP_TO_DATE if skip_check else core.NOT_CHECKED))

    def check_now(self):
        self.show_status(None)
        self.run_bg(lambda: core.check_for_update(self.git, self.cfg), "status")

    def on_message(self, tag, payload):
        if tag == "status":
            if payload.update_available:
                self.root.deiconify()
                self.show_update(payload)
            elif self.login_check:
                self.root.destroy()
            else:
                self.show_status(payload)
                if self.auto_start and self.app_state == "idle":
                    self.start_app()
        elif tag == "rollback":
            self.messagebox.showinfo("Roll back", messages.rollback_text(payload), parent=self.root)
            self.version = core.version_label(self.git)
            self.app_state = "idle"
            self.check_now()
        elif tag == "deps":
            ok, detail = payload
            if ok:
                self.app_state = "starting"
                self.run_bg(self._start_server, "started")
            else:
                self.app_state, self.app_detail = "needs_setup", detail
            self.show_status(self.last_status)
        elif tag == "started":
            ok, detail = payload
            self.app_state, self.app_detail = ("running", "") if ok else ("failed", detail)
            if ok:
                self.open_browser()
                self.root.after(2000, self._watch_update_request)
            self.show_status(self.last_status)

    # ------------------------------------------------------------ app (editor server)
    def start_app(self):
        from . import appctl

        self.app_state = "checking"
        self.show_status(self.last_status)
        self.run_bg(lambda: appctl.deps_ready(self.repo), "deps")

    def _start_server(self):
        from lyric2resolve.settings import load_settings

        from . import appctl

        s, _ = load_settings()
        port = appctl.pick_port(s.editor_port, s.editor_host)
        log = paths.ensure_data_dir() / "logs" / "editor.log"
        self.server = appctl.start_editor(self.repo, port, log, s.editor_host)
        self.url = f"http://{s.editor_host}:{port}/"
        ok = appctl.wait_for_port(port, s.editor_host, timeout=60, alive=lambda: self.server.poll() is None)
        return ok, "" if ok else f"The editor did not start. Details: {log}"

    def _watch_update_request(self):
        """'Update now' in the browser banner -> run the normal (self-copying) update from here."""
        from . import appctl

        if self.app_state != "running":
            return
        if appctl.take_update_request(paths.settings_dir()):
            self.root.deiconify()
            self.do_update()
            return
        self.root.after(2000, self._watch_update_request)

    def open_browser(self):
        import webbrowser

        if self.url:
            webbrowser.open(self.url)

    def stop_app(self):
        from . import appctl

        appctl.stop(self.server)
        self.server = None
        self.app_state = "idle"

    def run_setup(self):
        from . import appctl

        appctl.run_setup(self.repo)
        self.messagebox.showinfo("Setup", "The setup runs in a separate window (this can take a while).\n"
                                 "When it says 'Setup complete', click 'Start editor'.", parent=self.root)

    def on_close(self):
        self.stop_app()
        self.root.destroy()

    def show_status(self, status):
        self.last_status = status
        f = self.clear()
        self.label(f, "lyric2resolve", title=True)
        self.label(f, messages.status_line(status, self.version))
        self.label(f, messages.app_line(self.app_state, self.url, self.app_detail))
        spec = []
        if self.app_state == "running":
            spec.append(("Open editor in browser", self.open_browser))
        elif self.app_state == "needs_setup":
            spec += [("Run setup", self.run_setup), ("Start editor", self.start_app)]
        elif self.app_state in ("idle", "failed"):
            spec.append(("Start editor", self.start_app))
        spec += [("Check for updates", self.check_now), ("Roll back", self.do_rollback),
                 ("Open data folder", lambda: open_folder(paths.ensure_data_dir()))]
        self.buttons(f, spec)
        if self.app_state == "running":
            self.label(f, "Closing this window stops the editor.")

    def show_update(self, status):
        f = self.clear()
        self.root.geometry("680x520")
        self.label(f, "Update available", title=True)
        self.label(f, f"Installed: {self.version}")
        self.textbox(f, messages.update_available_text(status))
        spec = [("Update now", self.do_update), ("Later", lambda: self.show_status(status))]
        if status.dirty:
            spec[0] = ("Update now (refused: local edits)", self.do_update)
        self.buttons(f, spec)

    def do_update(self):
        core_pkg = Path(core.__file__).resolve().parents[1]
        from .selfcopy import start_apply_process

        self.stop_app()  # release files held by the running app before replacing them
        start_apply_process(core_pkg, self.repo)
        self.root.destroy()

    def do_rollback(self):
        if self.messagebox.askyesno("Roll back", "Go back to the previous version of the app?\n"
                                    "Your projects and settings are not touched.", parent=self.root):
            self.stop_app()
            self.run_bg(lambda: core.rollback(self.git), "rollback")

    def mainloop(self):
        self.root.mainloop()


class ApplyWindow(_Base):
    """Runs in the temporary updater copy (separate process)."""

    def __init__(self, repo: Path, master=None):
        super().__init__("lyric2resolve - updating", master)
        self.repo, self.git, self.cfg = repo, Git(repo), load_config()
        f = self.clear()
        self.label(f, "Updating lyric2resolve", title=True)
        self.bar = self.ttk.Progressbar(f, maximum=len(core.STEP_NAMES), length=480, mode="determinate")
        self.bar.pack(fill="x", pady=(0, 10))
        self.step_labels = []
        for i, name in enumerate(core.STEP_NAMES):
            self.step_labels.append(self.label(f, f"{i + 1}. {name}"))
        self.detail = self.label(f, "")
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)  # don't close mid-update
        self.run_bg(lambda: core.run_update(self.git, self.cfg, progress=self._progress), "done")

    def _progress(self, i, name, detail):
        self.q.put(("progress", (i, name, detail)))

    def on_message(self, tag, payload):
        if tag == "progress":
            i, _name, detail = payload
            self.bar["value"] = i + 1
            for j, lbl in enumerate(self.step_labels):
                prefix = "[done] " if j < i else ("[....] " if j == i else "       ")
                lbl.configure(text=f"{prefix}{j + 1}. {core.STEP_NAMES[j]}", fg=ACCENT if j == i else FG)
            self.detail.configure(text=detail)
        elif tag == "done":
            self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)
            self.show_result(payload)

    def show_result(self, result):
        f = self.clear()
        self.root.geometry("680x560")
        if result.ok:
            self.label(f, "Update complete", title=True)
            self.textbox(f, messages.whats_changed_text(result))
            self.buttons(f, [("Start app", self._finish)])
        else:
            self.label(f, "Update failed", title=True)
            self.textbox(f, messages.failure_text(result))
            self.buttons(f, [("Close", self._finish)])

    def _finish(self):
        from .selfcopy import start_launcher

        self.root.destroy()
        try:
            start_launcher(self.repo, "--skip-check")
        except OSError:
            pass

    def mainloop(self):
        self.root.mainloop()


def run_launcher(repo: Path, skip_check: bool = False, login_check: bool = False) -> int:
    LauncherWindow(repo, skip_check, login_check).mainloop()
    return 0


def run_apply(repo: Path) -> int:
    ApplyWindow(repo).mainloop()
    return 0
