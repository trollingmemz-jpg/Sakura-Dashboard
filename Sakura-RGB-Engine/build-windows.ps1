$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
py -3 -m venv .venv
if ($LASTEXITCODE) { exit $LASTEXITCODE }
$python = '.\.venv\Scripts\python.exe'
& $python -m pip install -r requirements.txt 'pyinstaller>=6,<7'
if ($LASTEXITCODE) { exit $LASTEXITCODE }
& $python -m unittest discover -v
if ($LASTEXITCODE) { exit $LASTEXITCODE }
$branding = @()
if (Test-Path 'assets\sakura.ico') { $branding += @('--icon','assets\sakura.ico') }
if (Test-Path 'assets') { $branding += @('--add-data','assets;assets') }
& $python -m PyInstaller @branding --noconfirm --clean --onefile --windowed --name Sakura-RGB-Engine --collect-all hid app.py
exit $LASTEXITCODE
