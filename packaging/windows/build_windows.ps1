# Build BabelAgent.exe with PyInstaller. Run on Windows (PowerShell).
#   powershell -ExecutionPolicy Bypass -File packaging\windows\build_windows.ps1

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root
$Version = if ($env:VERSION) { $env:VERSION } else { "0.3.0" }

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt pyinstaller

# PortAudio: sounddevice wheels on Windows usually bundle it.

Remove-Item -Recurse -Force dist\BabelAgent, build -ErrorAction SilentlyContinue
pyinstaller --noconfirm --clean packaging\babel-agent.spec

Write-Host "Built: dist\BabelAgent\BabelAgent.exe"
Write-Host "Zip that folder for distribution, or wrap with Inno Setup / NSIS."
Write-Host "Version: $Version"
