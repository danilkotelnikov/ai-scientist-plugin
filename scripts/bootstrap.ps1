# scripts/bootstrap.ps1 -- one-command installer for vedix plugin (v3.0+).
#
# Usage (interactive):
#   $r="$env:USERPROFILE\.vedix\repo"; if(Test-Path "$r\.git"){ git -C $r pull --rebase }else{ git clone https://github.com/danilkotelnikov/vedix.git $r }; & "$r\scripts\bootstrap.ps1"
#
# Usage (non-interactive, scripted -- pick exact hosts):
#   $env:AISP_HOSTS = "claude,codex"   # or "all", "none", "claude", "codex", "gemini"
#   & "$r\scripts\bootstrap.ps1"
#
# Detects Claude Code / Codex CLI / Gemini CLI in ~/.{claude,codex,gemini}/.
# By default prompts the user to choose which detected hosts to register.
# Idempotent: re-runs are safe.
#
# Pure ASCII so non-UTF-8 PowerShell sessions parse it correctly.

$ErrorActionPreference = "Continue"

$RepoUrl   = "https://github.com/danilkotelnikov/vedix.git"
$Branch    = "master"
$RepoDir   = "$env:USERPROFILE\.vedix\repo"
$AiHome    = "$env:USERPROFILE\.vedix"
$PalaceDir = "$AiHome\palace"

# Per-host install timeout (seconds). Gemini's extension install in particular
# is known to hang; keep this generous but bounded so the bootstrap always
# returns control to the user.
$PerHostTimeoutSec = 90

function Step([string]$msg) { Write-Host "  $msg" -ForegroundColor Cyan }
function Ok([string]$msg)   { Write-Host "  [OK]   $msg" -ForegroundColor Green }
function Note([string]$msg) { Write-Host "  [NOTE] $msg" -ForegroundColor Yellow }
function Fail([string]$msg) { Write-Host "  [FAIL] $msg" -ForegroundColor Red }

function Invoke-Native {
    param([Parameter(Mandatory)][scriptblock]$Script,
          [string]$Description = "command",
          [switch]$IgnoreExitCode)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $Script
        $code = $LASTEXITCODE
        if (-not $IgnoreExitCode -and $code -ne 0) {
            throw "$Description failed (exit $code)"
        }
        return $code
    } finally { $ErrorActionPreference = $prev }
}

# Run a native command with a hard wall-clock timeout. The command runs in a
# background Job; if it doesn't finish within $TimeoutSec, the job is killed
# and the function returns "timeout". This prevents `gemini extensions
# install` (and similar long-runners) from hanging the bootstrap.
function Invoke-WithTimeout {
    param(
        [Parameter(Mandatory)][scriptblock]$Script,
        [int]$TimeoutSec = 90,
        [string]$Description = "command"
    )
    $job = Start-Job -ScriptBlock $Script
    $finished = Wait-Job -Job $job -Timeout $TimeoutSec
    if ($finished) {
        $output = Receive-Job -Job $job -ErrorAction SilentlyContinue
        Remove-Job -Job $job -Force | Out-Null
        return @{ status = "ok"; output = $output }
    }
    Stop-Job -Job $job -ErrorAction SilentlyContinue
    Remove-Job -Job $job -Force -ErrorAction SilentlyContinue | Out-Null
    return @{ status = "timeout"; output = "$Description exceeded $TimeoutSec seconds and was killed" }
}

# Detect installed CLI hosts. Returns a hashtable of present-on-disk flags.
function Detect-Hosts {
    return @{
        claude = (Test-Path "$env:USERPROFILE\.claude")
        codex  = (Test-Path "$env:USERPROFILE\.codex")
        gemini = (Test-Path "$env:USERPROFILE\.gemini")
    }
}

# Parse a comma-separated list of host names ("claude,codex", "all", "none")
# against the detected hosts. Returns hashtable of {claude,codex,gemini} -> bool.
function Parse-HostSelection {
    param([string]$Spec, [hashtable]$Detected)
    $out = @{ claude = $false; codex = $false; gemini = $false }
    if ([string]::IsNullOrWhiteSpace($Spec)) { return $out }
    $s = $Spec.Trim().ToLower()
    if ($s -eq "none") { return $out }
    if ($s -eq "all" -or $s -eq "*") {
        foreach ($k in @("claude","codex","gemini")) {
            if ($Detected[$k]) { $out[$k] = $true }
        }
        return $out
    }
    foreach ($tok in $s -split "[,\s]+") {
        $t = $tok.Trim()
        if (-not $t) { continue }
        # Map numeric / abbreviated forms.
        switch -Regex ($t) {
            "^(1|c|cl|claude|claude.code|claude_code)$" { if ($Detected.claude) { $out.claude = $true } }
            "^(2|x|cx|codex|codex.cli)$"               { if ($Detected.codex)  { $out.codex  = $true } }
            "^(3|g|ge|gem|gemini|gemini.cli)$"         { if ($Detected.gemini) { $out.gemini = $true } }
            default { Note "Unknown host token: '$t' (ignored)" }
        }
    }
    return $out
}

# Interactive picker. Lists detected hosts; prompts for a selection.
function Prompt-HostSelection {
    param([hashtable]$Detected)
    $any = $Detected.claude -or $Detected.codex -or $Detected.gemini
    if (-not $any) {
        Note "No CLI hosts detected (~/.claude, ~/.codex, ~/.gemini all absent)."
        Note "The bootstrap will install Python deps + run --selftest only."
        return @{ claude = $false; codex = $false; gemini = $false }
    }
    Write-Host ""
    Write-Host "Detected agent CLI hosts on this machine:" -ForegroundColor Magenta
    if ($Detected.claude) { Write-Host "  [1] Claude Code (~/.claude/)" }
    if ($Detected.codex)  { Write-Host "  [2] Codex CLI    (~/.codex/)" }
    if ($Detected.gemini) { Write-Host "  [3] Gemini CLI   (~/.gemini/)" }
    Write-Host ""
    Write-Host "Which hosts should I install vedix into?"
    Write-Host "  - Enter numbers separated by spaces or commas (e.g. '1 2', '1,3')"
    Write-Host "  - 'all' or empty (Enter): every detected host"
    Write-Host "  - 'none': skip all host registration (just install Python deps)"
    Write-Host ""
    $answer = Read-Host "  Your choice"
    if ([string]::IsNullOrWhiteSpace($answer)) { $answer = "all" }
    return (Parse-HostSelection -Spec $answer -Detected $Detected)
}

# ============================================================================

Write-Host ""
Write-Host "AI-Scientist Plugin -- one-command bootstrap" -ForegroundColor Magenta
Write-Host ""

# 1. Probe prerequisites
Step "Probing prerequisites"
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Fail "Python 3.11+ not found in PATH. Install: winget install --id Python.Python.3.11"
    exit 1
}
$git = Get-Command git -ErrorAction SilentlyContinue
if (-not $git) {
    Fail "git not found. Install: winget install --id Git.Git"
    exit 1
}
Ok "python: $((& python --version 2>&1) -join ' ')"
Ok "git:    $((& git --version 2>&1) -join ' ')"

# 2. Detect hosts and decide selection (env override > interactive prompt)
$detected = Detect-Hosts
if ($env:AISP_HOSTS) {
    $selected = Parse-HostSelection -Spec $env:AISP_HOSTS -Detected $detected
    Step "Host selection from `$env:AISP_HOSTS = '$($env:AISP_HOSTS)'"
    foreach ($k in @("claude","codex","gemini")) {
        if ($selected[$k]) { Ok "$k -- selected" }
        elseif ($detected[$k]) { Note "$k -- detected but not selected" }
    }
} else {
    $selected = Prompt-HostSelection -Detected $detected
}

# 3. Clone or update the canonical repo
Step "Syncing canonical repo at $RepoDir"
New-Item -ItemType Directory -Force -Path $AiHome | Out-Null
if (Test-Path "$RepoDir\.git") {
    Push-Location $RepoDir
    Invoke-Native -IgnoreExitCode -Description "git stash" -Script {
        git stash push --include-untracked -m "auto-stash by bootstrap.ps1 $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" *>&1 | Out-Null
    }
    Invoke-Native -IgnoreExitCode -Description "git fetch" -Script {
        git fetch --quiet origin $Branch
    }
    Invoke-Native -IgnoreExitCode -Description "git reset" -Script {
        git reset --hard "origin/$Branch" --quiet
    }
    Pop-Location
    Ok "Updated existing clone (any local changes saved as a stash)"
} else {
    Invoke-Native -Description "git clone" -Script {
        git clone --quiet --branch $Branch $RepoUrl $RepoDir
    }
    Ok "Cloned fresh"
}

$Plug = "$RepoDir\plugins\vedix"

# 4. Install Python dependencies (idempotent, --user)
Step "Installing Python dependencies (user-site)"
Invoke-Native -IgnoreExitCode -Description "pip install requirements" -Script {
    python -m pip install --user --quiet -r "$Plug\mcp\requirements.txt" 2>&1 | Out-Null
}
Ok "MCP requirements present"

Invoke-Native -IgnoreExitCode -Description "pip install mempalace" -Script {
    python -m pip install --user --quiet mempalace 2>&1 | Out-Null
}
Ok "mempalace package present"

if (-not (Test-Path $PalaceDir)) {
    New-Item -ItemType Directory -Path $PalaceDir -Force | Out-Null
}
$mempalaceCmd = Get-Command mempalace -ErrorAction SilentlyContinue
if ($mempalaceCmd) {
    Invoke-Native -IgnoreExitCode -Description "mempalace init" -Script {
        mempalace init "$PalaceDir" *>&1 | Out-Null
    }
    Ok "MemPalace initialized at $PalaceDir"
} else {
    Note "mempalace CLI not on PATH yet; reopen the shell or set %PATH%"
}

# 4d. Run the plugin's own install.ps1 so the two cloned MCPs
# (semanticscholar-MCP-Server + bioRxiv-MCP-Server) get cloned into
# ~/.vedix/external/. The bootstrap previously skipped this,
# leaving those two MCPs broken on first use.
Step "Running plugin install.ps1 (provisions semanticscholar + biorxiv git clones)"
Invoke-Native -IgnoreExitCode -Description "plugin install.ps1" -Script {
    & "$Plug\scripts\install.ps1" 2>&1 | Out-Host
}
Ok "Plugin install.ps1 completed (see output above)"

# 5. Codex CLI -- auto-merge config + create junctions  (only if selected)
if ($selected.codex) {
    Write-Host ""
    Step "Registering plugin into Codex CLI"

    $codexClone = "$env:USERPROFILE\.codex\vedix"
    if (-not (Test-Path $codexClone)) {
        cmd /c mklink /J "$codexClone" "$RepoDir" 2>&1 | Out-Null
        Ok "Junctioned ~/.codex/vedix -> $RepoDir"
    } else {
        Ok "~/.codex/vedix already present"
    }

    New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.agents\skills" | Out-Null
    New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.agents\agents" | Out-Null
    foreach ($pair in @(
        @("$env:USERPROFILE\.agents\skills\vedix", "$Plug\skills\ai-scientist"),
        @("$env:USERPROFILE\.agents\agents\vedix", "$Plug\agents")
    )) {
        $linkPath, $target = $pair
        if (Test-Path $linkPath) { cmd /c rmdir "$linkPath" 2>&1 | Out-Null }
        cmd /c mklink /J "$linkPath" "$target" 2>&1 | Out-Null
    }
    Ok "Junctioned skill + agents into ~/.agents/"

    $configToml = "$env:USERPROFILE\.codex\config.toml"
    Invoke-Native -Description "merge codex config.toml" -Script {
        python "$RepoDir\scripts\_merge_codex_config.py" `
            --user "$configToml" `
            --example "$Plug\codex-config.toml.example" `
            --quiet
    }
    Ok "config.toml merged (sentinel-bracketed; idempotent)"
} elseif ($detected.codex) {
    Note "Codex CLI present but not selected -- skipping"
}

# 6. Gemini CLI -- run extension install with timeout (only if selected)
if ($selected.gemini) {
    Write-Host ""
    Step "Registering plugin into Gemini CLI (timeout: ${PerHostTimeoutSec}s)"
    $gemini = Get-Command gemini -ErrorAction SilentlyContinue
    if ($gemini) {
        $url = $RepoUrl
        $r = Invoke-WithTimeout -TimeoutSec $PerHostTimeoutSec -Description "gemini extensions install" -Script {
            param() & gemini extensions install $using:url 2>&1
        }
        if ($r.status -eq "ok") {
            Ok "Gemini extension installed"
        } else {
            Note "Gemini install timed out or hung -- skipping. Re-run later with: gemini extensions install $url"
        }
    } else {
        Note "gemini CLI not on PATH; install Gemini CLI then re-run this bootstrap"
    }
} elseif ($detected.gemini) {
    Note "Gemini CLI present but not selected -- skipping"
}

# 7. Claude Code -- print the two slash commands (only if selected)
if ($selected.claude) {
    Write-Host ""
    Step "Claude Code selected"
    Note "Open a Claude Code session and paste these two slash commands:"
    Write-Host "      /plugin marketplace add danilkotelnikov/vedix" -ForegroundColor White
    Write-Host "      /plugin install vedix@vedix"                                   -ForegroundColor White
    Note "Slash commands cannot be issued from outside the agent session."
} elseif ($detected.claude) {
    Note "Claude Code present but not selected -- skipping"
}

# 8. MCP self-test
Write-Host ""
Step "Running MCP self-test"
$prev = $ErrorActionPreference; $ErrorActionPreference = "Continue"
$selftest = (& python "$Plug\mcp\server.py" --selftest 2>&1) -join "`n"
$selftestCode = $LASTEXITCODE
$ErrorActionPreference = $prev
if ($selftestCode -eq 0 -and $selftest -match "selftest: OK") {
    Ok ($selftest -replace "`n", "; ")
} else {
    Note "self-test exit $selftestCode; output: $selftest"
}

# 9. Probe required env var
Write-Host ""
Step "Environment variables"
if (-not $env:OPENALEX_EMAIL) {
    Note "OPENALEX_EMAIL is not set. Set it once via:"
    Write-Host "      [Environment]::SetEnvironmentVariable('OPENALEX_EMAIL', 'you@example.com', 'User')" -ForegroundColor White
    Note "(close + reopen the shell after setting; required since 2026-02-13 for OpenAlex)"
} else {
    Ok "OPENALEX_EMAIL = $env:OPENALEX_EMAIL"
}
foreach ($v in @("SEMANTIC_SCHOLAR_KEY", "ANNAS_BASE_URL", "ANNAS_DOWNLOAD_PATH", "ANNAS_SECRET_KEY")) {
    $val = [Environment]::GetEnvironmentVariable($v, "Process")
    if ($val) { Ok "$v = (set)" } else { Note "$v not set (optional)" }
}

# 9b. B1: v2 -> v3 migration (Vedix rename)
$v2Dir = Join-Path $env:USERPROFILE ".ai-scientist"
$v3Dir = Join-Path $env:USERPROFILE ".vedix"
if ((Test-Path $v2Dir) -and -not (Test-Path $v3Dir)) {
    Write-Host ""
    Step "Detected v2.x install at $v2Dir -- running migration helper"
    Invoke-Native -IgnoreExitCode -Description "migrate_v2_to_v3.py" -Script {
        & python (Join-Path $RepoDir "scripts\migrate_v2_to_v3.py")
    }
}

# 10. Summary
Write-Host ""
Write-Host "Bootstrap complete." -ForegroundColor Green
Write-Host "  - canonical repo: $RepoDir"
Write-Host "  - re-run anytime: same one-liner (idempotent)"
Write-Host "  - skip the prompt next time: `$env:AISP_HOSTS = 'claude,codex' (or 'all' / 'none')"
Write-Host ""
