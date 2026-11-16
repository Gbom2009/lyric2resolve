@echo off
rem lyric2resolve full setup: torch + CUDA, Whisper, audio libs, ffmpeg check.
rem Run install.bat first (it creates .venv and the shortcuts).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_windows.ps1" %*
echo.
pause
