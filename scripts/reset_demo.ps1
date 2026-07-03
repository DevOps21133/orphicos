# Reset the OrphicOS demo inputs to a clean, identical state before each take.
# Wipes C:\OrphicDemo\invoices and regenerates the five fixed PDFs, so every
# recording of the Phase 4 flagship starts from the exact same folder.
$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo ".venv\Scripts\python.exe"
$invoices = "C:\OrphicDemo\invoices"

if (-not (Test-Path $python)) {
    Write-Error "venv python not found at $python — run scripts\setup.ps1 first."
    exit 1
}

if (Test-Path $invoices) {
    Remove-Item -Path $invoices -Recurse -Force
    Write-Host "Cleared $invoices"
}

& $python (Join-Path $repo "demo\make_invoices.py")
Write-Host "Demo reset complete."
