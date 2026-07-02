# Health-check the OrphicOS brain endpoint. Exit 0 if serving, 1 if not.
$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$EnvFile = Join-Path $Root '.env'
$Base = 'http://localhost:8000/v1'
if (Test-Path $EnvFile) {
    foreach ($line in Get-Content $EnvFile) {
        if ($line -match '^\s*LOCAL_MODEL_BASE\s*=\s*(.+)$') { $Base = $Matches[1].Trim() }
    }
}

try {
    $models = Invoke-RestMethod -Uri "$Base/models" -TimeoutSec 5
    Write-Host "PASS  Brain serving at $Base : $(($models.data | ForEach-Object id) -join ', ')" -ForegroundColor Green
    exit 0
} catch {
    Write-Host "FAIL  Brain not responding at $Base" -ForegroundColor Red
    exit 1
}
