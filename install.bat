@echo off
rem lyric2resolve first-time install (run from inside the cloned folder).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
echo.
pause
