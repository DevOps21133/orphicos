# OrphicOS Phase 0 environment check. Prints PASS/FAIL per check, exit 0 only if all pass.
$script:failCount = 0

function Report([string]$Name, [bool]$Ok, [string]$Detail) {
    if ($Ok) {
        Write-Host ("PASS  {0,-20} {1}" -f $Name, $Detail) -ForegroundColor Green
    } else {
        Write-Host ("FAIL  {0,-20} {1}" -f $Name, $Detail) -ForegroundColor Red
        $script:failCount++
    }
}

# Python 3.10 - 3.12
try {
    $pyOut = (& python --version) -join ' '
    $m = [regex]::Match($pyOut, '(\d+)\.(\d+)\.(\d+)')
    $ok = $m.Success -and ([int]$m.Groups[1].Value -eq 3) -and ([int]$m.Groups[2].Value -ge 10) -and ([int]$m.Groups[2].Value -le 12)
    Report 'Python 3.10-3.12' $ok $pyOut
} catch {
    Report 'Python 3.10-3.12' $false 'python not found on PATH'
}

# Git
try {
    $gitOut = (& git --version) -join ' '
    Report 'Git' ($gitOut -match 'git version') $gitOut
} catch {
    Report 'Git' $false 'git not found on PATH'
}

# GPU: RTX 5090 visible, CUDA >= 12
try {
    $gpuName = (& nvidia-smi --query-gpu=name --format=csv,noheader) -join '; '
    Report 'GPU RTX 5090' ($gpuName -match '5090') $gpuName

    $smiOut = (& nvidia-smi) -join "`n"
    $cm = [regex]::Match($smiOut, 'CUDA Version:\s*(\d+)\.(\d+)')
    $cudaOk = $cm.Success -and ([int]$cm.Groups[1].Value -ge 12)
    if ($cm.Success) { $cudaDetail = "CUDA $($cm.Groups[1].Value).$($cm.Groups[2].Value)" } else { $cudaDetail = 'CUDA version not detected' }
    Report 'CUDA >= 12' $cudaOk $cudaDetail
} catch {
    Report 'GPU RTX 5090' $false 'nvidia-smi not found on PATH'
    Report 'CUDA >= 12' $false 'nvidia-smi not found on PATH'
}

Write-Host ''
if ($script:failCount -eq 0) {
    Write-Host 'All checks PASS.' -ForegroundColor Green
    exit 0
} else {
    Write-Host "$script:failCount check(s) FAILED." -ForegroundColor Red
    exit 1
}
