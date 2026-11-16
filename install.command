#!/bin/bash
# lyric2resolve - first-time install on a Mac (Apple Silicon). Double-click this file in Finder.
# (First time macOS may say it cannot verify the developer: right-click > Open, or run: bash install.command)
# Options: --no-dock (do not offer the Dock), --dest DIR (where lyric2resolve.app goes), --yes (no questions)
set -u
cd "$(dirname "$0")" || exit 1
REPO="$(pwd)"
DOCK=1; ASK=1; DEST=""
while [ $# -gt 0 ]; do
  case "$1" in
    --no-dock) DOCK=0 ;;
    --yes) ASK=0 ;;
    --dest) DEST="$2"; shift ;;
  esac
  shift
done
step() { printf "\n\033[1;36m== %s\033[0m\n" "$1"; }
fail() { printf "\n\033[1;31mERROR: %s\033[0m\n" "$1"; [ $ASK = 1 ] && read -r -p "Press Enter to close." _; exit 1; }
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"

step "Checking git (Apple command line tools)"
if ! git --version >/dev/null 2>&1; then
  xcode-select --install 2>/dev/null
  fail "git is missing. macOS is now offering to install the 'command line developer tools' - accept, wait until it is done, then double-click install.command again."
fi
git -C "$REPO" rev-parse --is-inside-work-tree >/dev/null 2>&1 || fail "This folder is not a git clone. Use: git clone https://github.com/Gbom2009/lyric2resolve.git (see INSTALL_MAC.md). A ZIP download cannot update itself."
echo "OK: $(git --version)"

step "Looking for Python 3.10+ with Tkinter"
PY=""
for c in python3.12 python3.13 python3.11 python3 /Library/Frameworks/Python.framework/Versions/3.12/bin/python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c "import sys, tkinter; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null; then
    PY="$c"; break
  fi
done
[ -n "$PY" ] || fail "No Python 3.10+ with Tkinter found. Install Python 3.12 from https://www.python.org/downloads/macos/ (the 'macOS 64-bit universal2 installer'), then run install.command again. (Homebrew Python works too after: brew install python-tk@3.12)"
echo "Using: $PY ($("$PY" --version))"

step "Switching to the Mac release channel (mac-release)"
if git -C "$REPO" fetch --quiet origin mac-release 2>/dev/null; then
  if [ -z "$(git -C "$REPO" status --porcelain --untracked-files=no)" ]; then
    git -C "$REPO" checkout --quiet -B mac-release origin/mac-release && echo "OK: on mac-release"
  else
    echo "Local changes found - staying on the current branch."
  fi
else
  echo "mac-release not reachable (offline or not created yet) - staying on $(git -C "$REPO" branch --show-current)."
fi

step "Creating the virtual environment (.venv)"
if [ ! -x "$REPO/.venv/bin/python3" ]; then
  "$PY" -m venv "$REPO/.venv" || fail "Could not create the virtual environment."
else
  echo ".venv already exists - reusing it."
fi
"$REPO/.venv/bin/python3" -m pip install --disable-pip-version-check -q -r "$REPO/requirements/launcher.txt" || fail "pip install failed."

step "Self-check"
"$REPO/.venv/bin/python3" -c "import sys; sys.path.insert(0, '$REPO/src'); import lyric2resolve.updater.core, tkinter; from lyric2resolve import paths; print('data folder:', paths.ensure_data_dir())" || fail "Self-check failed."

step "Making lyric2resolve.app"
ARGS=(--repo "$REPO")
[ -n "$DEST" ] && ARGS+=(--dest "$DEST")
APP="$(PYTHONPATH="$REPO/src" "$REPO/.venv/bin/python3" -m lyric2resolve.macapp "${ARGS[@]}")" || fail "Could not make the app."
echo "Made: $APP"

if [ $DOCK = 1 ] && [ $ASK = 1 ]; then
  read -r -p "Add lyric2resolve to the Dock? [Y/n] " ans
  if [ -z "$ans" ] || [ "$ans" = "y" ] || [ "$ans" = "Y" ]; then
    defaults write com.apple.dock persistent-apps -array-add "<dict><key>tile-data</key><dict><key>file-data</key><dict><key>_CFURLString</key><string>$APP</string><key>_CFURLStringType</key><integer>0</integer></dict></dict></dict>" && killall Dock
  fi
fi

printf "\n\033[1;32mDone!\033[0m Open lyric2resolve from Applications (or the Dock). The first time macOS may ask:\n"
echo "right-click the app > Open > Open. Then click 'Run setup' in the launcher (installs Whisper, PyTorch, ...)."
[ $ASK = 1 ] && read -r -p "Press Enter to close." _
exit 0
