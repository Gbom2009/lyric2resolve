# lyric2resolve - full dependency setup (Windows). Safe to run again at any time.
param([switch]$DryRun)
$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPy = Join-Path $Repo ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPy)) {
    Write-Host "No .venv found - running install.ps1 first." -ForegroundColor Yellow
    & (Join-Path $Repo "install.ps1")
    if ($LASTEXITCODE -ne 0) { exit 1 }
}
$argsList = @((Join-Path $Repo "scripts\setup_update.py"), "--full")
if ($DryRun) { $argsList += "--dry-run" }
& $VenvPy @argsList
if ($LASTEXITCODE -ne 0) {
    Write-Host "Setup failed. Copy the messages above into the Claude session." -ForegroundColor Red
    exit 1
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host "Tip: install ffmpeg with:  winget install Gyan.FFmpeg" -ForegroundColor Yellow
}
Write-Host "Setup complete. Next: .venv\Scripts\python.exe scripts\verify_local.py" -ForegroundColor Green
