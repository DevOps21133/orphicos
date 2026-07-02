#Requires -Version 5.1
<#
  OrphicOS thin-client launcher (Phase 2, text path).

  Health-checks the OrphicOS brain, then runs one command against the LIVE DESKTOP
  through the client venv. A human runs this and watches the live log; Ctrl+C stops
  it at any time (CLAUDE.md Rule 7). This script never runs itself.

  Usage:
    $env:ORPHIC_TOKEN = "<your OrphicOS token>"
    .\scripts\run_client.ps1 Open Notepad and type: the machine works.
#>
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Command
)

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
    Write-Host "FAIL: brain not reachable at $serverBase/health ($($_.Exception.Message))." -ForegroundColor Red
    Write-Host "Start the brain first, then re-run." -ForegroundColor Yellow
    exit 1
}

if (-not $Command -or $Command.Count -eq 0) {
    Write-Host "Usage: .\scripts\run_client.ps1 <what should the machine do>" -ForegroundColor Yellow
    exit 2
}

$commandText = ($Command -join " ")
Write-Host "Running against the LIVE DESKTOP. Press Ctrl+C to stop." -ForegroundColor Magenta
& $python -m client $commandText
exit $LASTEXITCODE
