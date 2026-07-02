# Bring the OrphicOS brain up: launches the vLLM server inside WSL2 in its own window.
# First run performs one-time setup + model weight download (~16 GB).
$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$Drive = $Root.Substring(0, 1).ToLower()
$WslServe = "/mnt/$Drive" + ($Root.Substring(2) -replace '\\', '/') + '/server/scripts/vllm_serve.sh'

Write-Host "OrphicOS brain starting (vLLM in WSL2): $WslServe"
Start-Process wsl -ArgumentList '-e', 'bash', $WslServe
Write-Host 'Server window launched. Health-check with brain_health.ps1 (model load takes a minute; first run downloads weights).'
