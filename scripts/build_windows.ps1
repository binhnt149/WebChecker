$ErrorActionPreference = "Stop"

Set-Location (Split-Path -Parent $PSScriptRoot)

$python = $env:PYTHON_BIN
if (-not $python) {
    $python = "python"
}

& $python -m pip install -r requirements.txt -r requirements-build.txt

if (Test-Path build) {
    Remove-Item build -Recurse -Force
}
if (Test-Path dist) {
    Remove-Item dist -Recurse -Force
}

$env:PYINSTALLER_CONFIG_DIR = Join-Path (Get-Location) "build\pyinstaller-config"
New-Item -ItemType Directory -Force -Path $env:PYINSTALLER_CONFIG_DIR | Out-Null

& $python -m PyInstaller --noconfirm packaging/sitesentry_windows.spec

$exePath = "dist\SiteSentry Desktop.exe"
if (-not (Test-Path $exePath)) {
    throw "Build completed but $exePath was not created."
}

Compress-Archive -Path $exePath -DestinationPath "dist\SiteSentry-Desktop-Windows.zip" -Force
Write-Host "Created $exePath"
Write-Host "Created dist\SiteSentry-Desktop-Windows.zip"
