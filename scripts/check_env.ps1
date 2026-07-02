#Requires -Version 5.1
<#
    OrphicOS - Phase 0 environment & skeleton check.

    Prints [PASS] / [FAIL] / [INFO] per check. The SERVER_BASE reachability check
    is EXPECTED to fail until Phase 1 hosts the brain, so it is reported as [INFO]
    and does NOT fail this script.

    Exit code: 0 if all required checks PASS, 1 otherwise.

    Usage:
        powershell -ExecutionPolicy Bypass -File scripts\check_env.ps1
#>

$RepoRoot = Split-Path -Parent $PSScriptRoot
$script:Failures = 0

function Write-Check {
    param(
        [Parameter(Mandatory)] [string] $Name,
        [Parameter(Mandatory)] [ValidateSet('PASS', 'FAIL', 'INFO')] [string] $Status,
        [string] $Detail = ''
    )
    $color = @{ PASS = 'Green'; FAIL = 'Red'; INFO = 'Yellow' }[$Status]
    Write-Host ('[{0}]' -f $Status) -ForegroundColor $color -NoNewline
    Write-Host (' {0}' -f $Name) -NoNewline
    if ($Detail) {
        Write-Host ('  ->  {0}' -f $Detail) -ForegroundColor DarkGray
    } else {
        Write-Host ''
    }
    if ($Status -eq 'FAIL') { $script:Failures++ }
}

Write-Host ''
Write-Host 'OrphicOS - environment & skeleton check (Phase 0)' -ForegroundColor Cyan
Write-Host ('Repo: {0}' -f $RepoRoot) -ForegroundColor DarkGray
Write-Host ''

# --- 1. Python 3.10-3.12 ---------------------------------------------------
$pythonOk = $false
$pythonDetail = 'no python interpreter found (tried: python, py)'
foreach ($exe in @('python', 'py')) {
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
    $verRaw = (& $exe --version 2>$null | Out-String).Trim()
    if ($verRaw -match '(\d+)\.(\d+)\.(\d+)') {
        $maj = [int]$Matches[1]; $min = [int]$Matches[2]
        if ($maj -eq 3 -and $min -ge 10 -and $min -le 12) {
            $pythonOk = $true
            $pythonDetail = ('{0}  (via "{1}")' -f $verRaw, $exe)
            break
        }
        $pythonDetail = ('{0} outside supported range 3.10-3.12 (via "{1}")' -f $verRaw, $exe)
    }
}
Write-Check 'Python 3.10-3.12' $(if ($pythonOk) { 'PASS' } else { 'FAIL' }) $pythonDetail

# --- 2. git present --------------------------------------------------------
$gitPresent = [bool](Get-Command git -ErrorAction SilentlyContinue)
if ($gitPresent) {
    $gitVer = (& git --version 2>$null | Out-String).Trim()
    Write-Check 'git present' 'PASS' $gitVer
} else {
    Write-Check 'git present' 'FAIL' 'git not found on PATH'
}

# --- 3. .gitignore ignores every .env --------------------------------------
$giPath = Join-Path $RepoRoot '.gitignore'
if (-not (Test-Path $giPath)) {
    Write-Check '.gitignore ignores .env' 'FAIL' '.gitignore missing'
} elseif ($gitPresent) {
    # Authoritative: ask git itself whether representative .env paths are ignored.
    $probes = @('server/.env', 'client/.env', '.env')
    $notIgnored = @()
    foreach ($p in $probes) {
        & git -C $RepoRoot check-ignore --quiet -- $p 2>$null
        if ($LASTEXITCODE -ne 0) { $notIgnored += $p }
    }
    if ($notIgnored.Count -eq 0) {
        Write-Check '.gitignore ignores .env' 'PASS' 'git ignores server/.env, client/.env, .env'
    } else {
        Write-Check '.gitignore ignores .env' 'FAIL' ('not ignored: {0}' -f ($notIgnored -join ', '))
    }
} else {
    $giText = Get-Content $giPath -Raw
    if ($giText -match '(?m)^\s*\*\*/\.env\s*$' -or $giText -match '(?m)^\s*\.env\s*$') {
        Write-Check '.gitignore ignores .env' 'PASS' 'pattern **/.env present (git not available to confirm)'
    } else {
        Write-Check '.gitignore ignores .env' 'FAIL' 'no .env ignore pattern found'
    }
}

# --- 4a. no .env secret is committed to git (Rule 6) -----------------------
# A real .env MAY exist locally (server/.env holds the live key), but it must be
# gitignored AND untracked so the key never enters the repo. A gitignored,
# untracked server/.env is the EXPECTED, correct state -- not a failure.
$envFiles = @(
    Get-ChildItem -Path $RepoRoot -Recurse -File -Force -Filter '.env' -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -eq '.env' -and $_.FullName -notmatch '\\\.git\\' }
)
if (-not $gitPresent) {
    Write-Check 'no .env secret in git' 'INFO' 'git unavailable; cannot confirm tracking'
} else {
    $tracked = @()   # tracked .env == secret already in the repo
    $exposed = @()   # un-ignored .env == would be committed on next `git add`
    foreach ($f in $envFiles) {
        $rel = ($f.FullName.Substring($RepoRoot.Length + 1)) -replace '\\', '/'
        & git -C $RepoRoot ls-files --error-unmatch -- $rel 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $tracked += $rel }
        & git -C $RepoRoot check-ignore --quiet -- $rel 2>$null
        if ($LASTEXITCODE -ne 0) { $exposed += $rel }
    }
    if ($tracked.Count -eq 0 -and $exposed.Count -eq 0) {
        $detail = if ($envFiles.Count -gt 0) {
            ('{0} local .env present; gitignored & untracked (OK)' -f $envFiles.Count)
        } else {
            'none present'
        }
        Write-Check 'no .env secret in git' 'PASS' $detail
    } else {
        $msgs = @()
        if ($tracked.Count -gt 0) { $msgs += ('TRACKED in git: {0}' -f ($tracked -join ', ')) }
        if ($exposed.Count -gt 0) { $msgs += ('not gitignored: {0}' -f ($exposed -join ', ')) }
        Write-Check 'no .env secret in git' 'FAIL' ($msgs -join '; ')
    }
}

# --- 4b. example env carries no filled-in secret ---------------------------
$exPath = Join-Path $RepoRoot 'server\.env.example'
if (-not (Test-Path $exPath)) {
    Write-Check 'server/.env.example has no secret' 'FAIL' 'server/.env.example missing'
} else {
    $filled = @()
    foreach ($line in (Get-Content $exPath)) {
        if ($line -match '^\s*(LLM_API_KEY|LLM_MODEL)\s*=\s*(\S.*)$') { $filled += $Matches[1] }
    }
    if ($filled.Count -eq 0) {
        Write-Check 'server/.env.example has no secret' 'PASS' 'LLM_API_KEY / LLM_MODEL empty'
    } else {
        Write-Check 'server/.env.example has no secret' 'FAIL' ('non-empty: {0}' -f ($filled -join ', '))
    }
}

# --- 5. client/server wall exists and is clean -----------------------------
$clientDir = Join-Path $RepoRoot 'client'
$serverDir = Join-Path $RepoRoot 'server'
$wallOk = $true
$wallDetail = @()

if ((Test-Path $clientDir) -and (Test-Path $serverDir)) {
    $wallDetail += 'client/ and server/ present'
} else {
    $wallOk = $false
    $wallDetail += 'missing client/ or server/'
}

# Rule 1/6: no LLM key material anywhere under client/.
if (Test-Path $clientDir) {
    $clientFiles = Get-ChildItem -Path $clientDir -Recurse -File -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch '\\\.git\\' }
    $leaks = @()
    foreach ($f in $clientFiles) {
        $hit = Select-String -Path $f.FullName -Pattern 'LLM_API_KEY\s*=\s*\S', 'sk-[A-Za-z0-9]{16,}' -ErrorAction SilentlyContinue
        if ($hit) { $leaks += $f.FullName.Substring($RepoRoot.Length + 1) }
    }
    if ($leaks.Count -eq 0) {
        $wallDetail += 'no LLM key material under client/'
    } else {
        $wallOk = $false
        $wallDetail += ('key material leaked into client/: {0}' -f (($leaks | Select-Object -Unique) -join ', '))
    }
}
Write-Check 'client/server wall clean' $(if ($wallOk) { 'PASS' } else { 'FAIL' }) ($wallDetail -join '; ')

# --- 6. SERVER_BASE reachability (expected FAIL until Phase 1) --------------
$cfg = Join-Path $RepoRoot 'client\config.toml'
if (-not (Test-Path $cfg)) { $cfg = Join-Path $RepoRoot 'client\config.example.toml' }
$serverBase = $null
if (Test-Path $cfg) {
    foreach ($line in (Get-Content $cfg)) {
        if ($line -match '^\s*SERVER_BASE\s*=\s*"?([^"#]+?)"?\s*$') { $serverBase = $Matches[1].Trim() }
    }
}
if (-not $serverBase) {
    Write-Check 'SERVER_BASE reachable' 'INFO' 'SERVER_BASE not set yet (expected until Phase 1)'
} else {
    try {
        $resp = Invoke-WebRequest -Uri $serverBase -Method Head -TimeoutSec 4 -UseBasicParsing -ErrorAction Stop
        Write-Check 'SERVER_BASE reachable' 'PASS' ('{0} -> HTTP {1}' -f $serverBase, [int]$resp.StatusCode)
    } catch {
        Write-Check 'SERVER_BASE reachable' 'INFO' ('{0} unreachable (expected FAIL until Phase 1)' -f $serverBase)
    }
}

# --- summary ---------------------------------------------------------------
Write-Host ''
if ($script:Failures -eq 0) {
    Write-Host 'RESULT: all required checks PASS.' -ForegroundColor Green
    exit 0
} else {
    Write-Host ('RESULT: {0} required check(s) FAILED.' -f $script:Failures) -ForegroundColor Red
    exit 1
}
