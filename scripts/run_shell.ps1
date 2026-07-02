#Requires -Version 5.1
<#
  OrphicOS shell launcher (Phase 5 — the product skin).

  Health-checks the OrphicOS brain, then starts the local dark UI. The shell drives the
  LIVE DESKTOP from commands a human types in the browser; each step streams into the log
  and Ctrl+Alt+Space (or the red STOP button) halts it instantly (CLAUDE.md Rule 7 & §9).
  The browser opens automatically. Ctrl+C here shuts the shell down. This script never
  sends a command itself.

  Usage:
    $env:ORPHIC_TOKEN = "<your OrphicOS token>"
    .\scripts\run_shell.ps1
#>
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$python = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "FAIL: client venv not found at .venv. Create it, then: .venv\Scripts\pip install -r client\requirements.txt" -ForegroundColor Red
    exit 1
}

$config = Join-Path $repo "client\config.toml"
if (-not (Test-Path $config)) {
    Write-Host "FAIL: client\config.toml not found. Copy client\config.example.toml to client\config.toml and set SERVER_BASE." -ForegroundColor Red
    exit 1
}

if (-not $env:ORPHIC_TOKEN) {
    Write-Host "FAIL: ORPHIC_TOKEN is not set. Issue one on the brain (python -m server.auth issue <user>), then:" -ForegroundColor Red
    Write-Host '       $env:ORPHIC_TOKEN = "<token>"' -ForegroundColor Yellow
    exit 1
}

$match = Select-String -Path $config -Pattern '^\s*SERVER_BASE\s*=\s*"(.+?)"' | Select-Object -First 1
if (-not $match) {
    Write-Host "FAIL: SERVER_BASE not set in client\config.toml." -ForegroundColor Red
    exit 1
}
$serverBase = $match.Matches[0].Groups[1].Value.TrimEnd('/')

Write-Host "Checking OrphicOS brain at $serverBase ..." -ForegroundColor Cyan
try {
    $resp = Invoke-WebRequest -Uri "$serverBase/health" -TimeoutSec 5 -UseBasicParsing
    if ($resp.StatusCode -ne 200) { throw "HTTP $($resp.StatusCode)" }
    Write-Host "OK: brain reachable." -ForegroundColor Green
} catch {
    Write-Host "WARN: brain not reachable at $serverBase/health ($($_.Exception.Message))." -ForegroundColor Yellow
    Write-Host "The shell will still start and show a 'brain unreachable' status until it comes up." -ForegroundColor Yellow
}

Write-Host "Starting the OrphicOS shell. It drives the LIVE DESKTOP from your commands." -ForegroundColor Magenta
Write-Host "The browser opens automatically. Press Ctrl+Alt+Space or the red STOP to halt; Ctrl+C here to quit." -ForegroundColor Magenta
& $python -m client.shell
exit $LASTEXITCODE
