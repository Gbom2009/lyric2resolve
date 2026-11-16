#!/bin/bash
# lyric2resolve - full dependency setup on a Mac (Apple Silicon). Safe to run again at any time.
cd "$(dirname "$0")" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"
if [ ! -x .venv/bin/python3 ]; then
  echo "No .venv found - running install.command first."
  bash install.command --yes --no-dock || exit 1
fi
.venv/bin/python3 scripts/setup_update.py --full "$@"
code=$?
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo ""
  echo "Tip: install ffmpeg with Homebrew:  brew install ffmpeg   (Homebrew: https://brew.sh)"
fi
if [ $code -eq 0 ]; then
  echo ""; echo "Setup complete. Next (optional): .venv/bin/python3 scripts/verify_local.py"
else
  echo ""; echo "Setup failed. Copy the messages above into the Claude session."
fi
read -r -p "Press Enter to close." _
exit $code
