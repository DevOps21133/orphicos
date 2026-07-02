# Launch a UFO task with the OrphicOS local-brain configuration.
# Usage: .\scripts\run_task.ps1 -Task <name>
param(
    [Parameter(Mandatory = $true)][string]$Task
)

$Root = Split-Path $PSScriptRoot -Parent
$EngineDir = Join-Path $Root 'engine\UFO'
$Python = Join-Path $Root '.venv\Scripts\python.exe'
$EnvFile = Join-Path $Root '.env'

if (-not (Test-Path $Python)) { Write-Error "venv not found at $Python - run Phase 1 setup."; exit 1 }
if (-not (Test-Path $EnvFile)) { Write-Error ".env not found - copy .env.example to .env and fill it in."; exit 1 }

# Deploy the canonical agent config into the engine (engine dir is gitignored).
Copy-Item (Join-Path $Root 'orphicos\config\agents.yaml') (Join-Path $EngineDir 'config\ufo\agents.yaml') -Force

# Load .env into process environment; the engine's config loader expands ${VAR}.
Get-Content $EnvFile | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
        [System.Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim())
    }
}

foreach ($required in 'LOCAL_MODEL_BASE', 'LOCAL_MODEL_NAME') {
    if (-not [System.Environment]::GetEnvironmentVariable($required)) {
        Write-Error "$required is empty - set it in .env (local model server must be running)."
        exit 1
    }
}

Write-Host "OrphicOS: launching task '$Task' against $env:LOCAL_MODEL_BASE ($env:LOCAL_MODEL_NAME)"
Push-Location $EngineDir
try {
    & $Python -m ufo --task $Task
} finally {
    Pop-Location
}
