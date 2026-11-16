# Installing lyric2resolve on a Mac (Apple Silicon: M1/M2/M3/M4)

You do this **once**. After that, the app updates itself (launcher → **Update now**), from the Mac release channel
`mac-release` (it only gets changes that passed the Mac tests).

## 1. Prerequisites
- **Python 3.12** from https://www.python.org/downloads/macos/ ("macOS 64-bit universal2 installer"). It includes
  Tkinter, which the launcher window needs. (Homebrew Python works too: `brew install python@3.12 python-tk@3.12`.)
- **git**: comes with Apple's command line tools. If it is missing, the installer asks macOS to install them.
- **ffmpeg** (audio conversion, videos): install [Homebrew](https://brew.sh), then in Terminal: `brew install ffmpeg`.
- Optional: **Blender** (visuals) from https://www.blender.org/download/ → drag it to Applications.
- Optional: **Claude Code** for the Assistant: `curl -fsSL https://claude.ai/install.sh | bash`, then run `claude` once and log in.

## 2. Get the code with git (not a ZIP)
Open **Terminal** (Applications → Utilities), go to where you want the app folder, e.g. your home folder, and run:
```
git clone https://github.com/Gbom2009/lyric2resolve.git
```
Private repository? macOS asks for your GitHub login; use a *fine-grained personal access token* with read-only
"Contents" access as the password (Keychain remembers it). A ZIP download cannot update itself.

## 3. Run the installer
In Finder, open the `lyric2resolve` folder and **double-click `install.command`**. (If macOS says it can't verify the
developer: right-click → **Open** → **Open**. Or in Terminal: `bash ~/lyric2resolve/install.command`.)
It checks git and Python, switches to the Mac release channel, creates `.venv`, makes **lyric2resolve.app** in
Applications (or `~/Applications` when you are not an admin), and offers to add it to the Dock.

## 4. Start + first-time setup
Open **lyric2resolve** from Applications/the Dock. The first time: right-click → **Open** → **Open** (the app is not
signed by Apple). Click **Run setup** in the launcher: a Terminal window installs PyTorch (Metal), Whisper (MLX) and the
rest (several GB, takes a while). Then **Start editor**.

## Your Mac (MacBook Air base model, 8 GB)
- Whisper uses **large-v3-turbo** by default (fast on M chips, fits in 8 GB).
- Visuals: start with **Preview**/**Draft** quality; long Standard renders get slow on a fanless Air.
- Close other heavy apps while transcribing or rendering.

## Troubleshooting
- Moved the `lyric2resolve` folder? Run `install.command` again (it remakes the app).
- Launcher error details: `~/Library/Application Support/lyric2resolve/logs/launcher.log`.
- "Update refused: files modified locally": in Terminal `cd ~/lyric2resolve && git checkout -- .` (only code, never your data).
