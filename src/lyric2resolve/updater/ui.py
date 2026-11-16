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
    def __init__(self, repo: Path, skip_check: bool = False, login_check: bool = False, master=None):
        super().__init__("lyric2resolve", master)
        self.repo, self.git, self.cfg = repo, Git(repo), load_config()
        self.login_check = login_check
        self.version = core.version_label(self.git)
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
        elif tag == "rollback":
            self.messagebox.showinfo("Roll back", messages.rollback_text(payload), parent=self.root)
            self.version = core.version_label(self.git)
            self.check_now()

    def show_status(self, status):
        f = self.clear()
        self.label(f, "lyric2resolve", title=True)
        self.label(f, messages.status_line(status, self.version))
        self.buttons(f, [("Check now", self.check_now), ("Roll back", self.do_rollback),
                         ("Open data folder", lambda: open_folder(paths.ensure_data_dir()))])

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

        start_apply_process(core_pkg, self.repo)
        self.root.destroy()

    def do_rollback(self):
        if self.messagebox.askyesno("Roll back", "Go back to the previous version of the app?\n"
                                    "Your projects and settings are not touched.", parent=self.root):
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
            # No app interface yet (Phase 7 adds the editor): "Close" reopens the launcher status window.
            self.buttons(f, [("Close", self._finish)])
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
