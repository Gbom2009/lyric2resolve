# Installing lyric2resolve (first time, Windows)

You do this **once**. After that, the launcher updates the app for you (Update button).

## 1. Prerequisites
- **Git for Windows**: https://git-scm.com/download/win (defaults are fine; it includes Git Credential Manager).
- **Python 3.12** (3.10–3.13 work): https://www.python.org/downloads/windows/
  During setup tick **"py launcher"** and, under *Optional features*, **"tcl/tk and IDLE"** (needed for the launcher window).

## 2. Get the code with git (not a ZIP)
Open *PowerShell* or *Command Prompt* in the folder where you want the app (e.g. `C:\Apps`) and run:
```
git clone https://github.com/Gbom2009/lyric2resolve.git
```
> A ZIP download from GitHub **cannot update itself** (it has no git history). Always use `git clone`.

**Private repository?** Git will open a GitHub sign-in window (Git Credential Manager) the first time and remember it.
If you prefer a token: create a *fine-grained personal access token* with **read-only "Contents"** access to this repo only, and paste it when Git asks for a password. Never put a token in a file in the app folder.

## 3. Run the installer
Double-click **`install.bat`** in the `lyric2resolve` folder. It:
1. checks Git and Python (with Tkinter),
2. creates a virtual environment in `lyric2resolve\.venv`,
3. installs the launcher requirements (currently nothing heavy),
4. creates the data folder `%LOCALAPPDATA%\lyric2resolve`,
5. creates a **lyric2resolve** shortcut on the Desktop and in the Start menu.

## 3b. Full setup (heavy dependencies)
Double-click **`setup_windows.bat`**: installs PyTorch (CUDA build matching your NVIDIA driver), Whisper and audio libraries (~3-5 GB, takes a while). The launcher also runs this automatically when an update changes requirements.
Install ffmpeg if it says it is missing: `winget install Gyan.FFmpeg`.
Then check everything: `.venv\Scripts\python.exe scripts\verify_local.py` → paste `REPORT_LOCAL.md` into the Claude session.

## 4. Start
Double-click the **lyric2resolve** shortcut. The launcher checks for updates and shows its window.

## Options (config file)
`%LOCALAPPDATA%\lyric2resolve\settings\updater.json` (created when you change something; defaults otherwise):
```json
{ "remote": "origin", "branch": "main", "repo_url": "", "check_at_launch": true,
  "check_at_login": false, "fetch_timeout_s": 20, "keep_rollback_tags": 5 }
```
- Check for updates at Windows login (off by default):
  `.venv\Scripts\python.exe launcher.pyw login-check on` (or `off`). It stays invisible unless an update is available.
- Console commands: `.venv\Scripts\python.exe launcher.pyw check-update | update | rollback | version`.

## Troubleshooting
- *"Git could not log in to GitHub"*: run `git fetch` once in the app folder and sign in when asked.
- *Update refused: files modified locally*: you (or an editor) changed a code file. Run `git checkout -- .` in the app folder (this only resets code, never your data folder) and update again.
- *Launcher error dialog*: details are in `%LOCALAPPDATA%\lyric2resolve\logs\launcher.log`.
- Moving the app folder: run `install.bat` again to recreate the shortcuts (delete `.venv` first).
