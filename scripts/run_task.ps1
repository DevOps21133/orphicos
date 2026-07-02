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

if (-not $env:LOCAL_MODEL_BASE) {
    Write-Error 'LOCAL_MODEL_BASE is empty - set it in .env.'
    exit 1
}
# Brain scripts serve the model under this fixed alias; override in .env only if serving differently.
if (-not $env:LOCAL_MODEL_NAME) { $env:LOCAL_MODEL_NAME = 'ui-tars-1.5-7b' }

# Health-check the brain endpoint before launching.
try {
    $models = Invoke-RestMethod -Uri "$env:LOCAL_MODEL_BASE/models" -TimeoutSec 5
    Write-Host "Brain online: $(($models.data | ForEach-Object id) -join ', ')"
} catch {
    Write-Error "Brain endpoint $env:LOCAL_MODEL_BASE is not responding - start it first: brain\scripts\brain_up.ps1"
    exit 1
}

Write-Host "OrphicOS: launching task '$Task' against $env:LOCAL_MODEL_BASE ($env:LOCAL_MODEL_NAME)"
Push-Location $EngineDir
try {
    & $Python -m ufo --task $Task
} finally {
    Pop-Location
}
