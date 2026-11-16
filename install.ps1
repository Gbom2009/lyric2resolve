# lyric2resolve - first-time install for Windows (PowerShell 5.1+).
# Run from inside the git clone:  install.bat   (or: powershell -ExecutionPolicy Bypass -File install.ps1)
# Creates .venv, installs the (tiny) launcher requirements, creates Desktop + Start-menu shortcuts.
# Never stores or logs credentials.
param(
    [switch]$NoShortcuts
)
# "Continue": native commands (git, python) report errors via $LASTEXITCODE, checked explicitly.
$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Repo

function Step($msg) { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }
function Fail($msg) { Write-Host ""; Write-Host "ERROR: $msg" -ForegroundColor Red; exit 1 }

Step "Checking Git"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Fail "Git is not installed. Install 'Git for Windows' from https://git-scm.com/download/win and run install.bat again."
}
git -C $Repo rev-parse --is-inside-work-tree 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Fail "This folder is not a git clone. A ZIP download cannot update itself. Use: git clone https://github.com/Gbom2009/lyric2resolve.git (see INSTALL.md)."
}

Step "Looking for Python 3.10+ with Tkinter"
$candidates = @(@("py", "-3.12"), @("py", "-3.11"), @("py", "-3.13"), @("py", "-3"), @("python"))
$Py = $null
foreach ($c in $candidates) {
    $exe = $c[0]
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
    $pyArgs = @()
    if ($c.Count -gt 1) { $pyArgs = $c[1..($c.Count - 1)] }
    $out = & $exe @pyArgs -c "import sys, tkinter; print(sys.version_info >= (3, 10))" 2>$null
    if ($LASTEXITCODE -eq 0 -and "$out".Trim() -eq "True") { $Py = $c; break }
}
if (-not $Py) {
    Fail "No suitable Python found. Install Python 3.12 from https://www.python.org/downloads/windows/ (tick 'tcl/tk and IDLE' and 'py launcher'), then run install.bat again."
}
Write-Host ("Using: " + ($Py -join " "))

Step "Creating the virtual environment (.venv)"
$VenvPy = Join-Path $Repo ".venv\Scripts\python.exe"
$VenvPyw = Join-Path $Repo ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $VenvPy)) {
    $exe = $Py[0]; $pyArgs = @()
    if ($Py.Count -gt 1) { $pyArgs = $Py[1..($Py.Count - 1)] }
    & $exe @pyArgs -m venv (Join-Path $Repo ".venv")
    if ($LASTEXITCODE -ne 0) { Fail "Could not create the virtual environment." }
} else { Write-Host ".venv already exists - reusing it." }

Step "Installing launcher requirements (standard library only for now)"
& $VenvPy -m pip install --disable-pip-version-check -q -r (Join-Path $Repo "requirements\launcher.txt")
if ($LASTEXITCODE -ne 0) { Fail "pip install failed (see messages above)." }

Step "Self-check"
& $VenvPy -c "import sys; sys.path.insert(0, r'$Repo\src'); import lyric2resolve.updater.core, tkinter; from lyric2resolve import paths; print('data folder:', paths.ensure_data_dir())"
if ($LASTEXITCODE -ne 0) { Fail "Self-check failed." }

Step "Checking access to GitHub (git fetch)"
git -C $Repo fetch --quiet origin 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "WARNING: git fetch failed. If the repository is private: run 'git fetch' in this folder once;" -ForegroundColor Yellow
    Write-Host "Git Credential Manager will ask you to sign in to GitHub and remember it (or use a fine-grained read-only token as password)." -ForegroundColor Yellow
    Write-Host "Offline is fine too - the launcher simply skips the update check." -ForegroundColor Yellow
} else { Write-Host "OK" }

if (-not $NoShortcuts) {
    Step "Creating shortcuts (Desktop + Start menu)"
    $shell = New-Object -ComObject WScript.Shell
    $targets = @(
        (Join-Path ([Environment]::GetFolderPath("Desktop")) "lyric2resolve.lnk"),
        (Join-Path ([Environment]::GetFolderPath("Programs")) "lyric2resolve.lnk")
    )
    foreach ($lnkPath in $targets) {
        $lnk = $shell.CreateShortcut($lnkPath)
        $lnk.TargetPath = $VenvPyw
        $lnk.Arguments = '"' + (Join-Path $Repo "launcher.pyw") + '"'
        $lnk.WorkingDirectory = $Repo
        $lnk.IconLocation = "$VenvPyw,0"
        $lnk.Description = "lyric2resolve launcher (checks for updates)"
        $lnk.Save()
        Write-Host "Created $lnkPath"
    }
}

Write-Host ""
Write-Host "Done! Start lyric2resolve with the 'lyric2resolve' shortcut on your Desktop or in the Start menu." -ForegroundColor Green
