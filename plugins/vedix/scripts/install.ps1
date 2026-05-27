# install.ps1 -- one-time setup for vedix plugin (Windows).
# Pure ASCII so non-UTF-8 PowerShell sessions (e.g. cp1251) parse it correctly.
$ErrorActionPreference = "Stop"
$PluginRoot = Split-Path -Parent $PSScriptRoot

# --- Helper: invoke a native command (python/pip/git/etc.) without letting
# its stderr writes become fatal under $ErrorActionPreference='Stop'.
# Native tools routinely write progress / notices to stderr even on success
# (e.g. pip's "[notice] A new release of pip is available"); under Stop mode
# PowerShell wraps that stream in a NativeCommandError and aborts the script
# even though the underlying exit code was 0. We locally relax the policy,
# run the command, then fault only when the real exit code says we should.
function Invoke-Native {
    param(
        [Parameter(Mandatory)][scriptblock]$Script,
        [string]$Description = "command",
        [switch]$IgnoreExitCode
    )
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Script
        $code = $LASTEXITCODE
        if (-not $IgnoreExitCode -and $code -ne 0) {
            throw "$Description failed (exit code $code)"
        }
        return $code
    } finally {
        $ErrorActionPreference = $previous
    }
}

Write-Host "Vedix plugin install starting..." -ForegroundColor Cyan

# 1. Probe Python
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Error "Python not found in PATH. Install Python 3.11+ and re-run."
    exit 1
}
$pyver = (& python --version 2>&1) -join " "
Write-Host "  Python: $pyver"

# 2. Probe Pandoc
$pandoc = Get-Command pandoc -ErrorAction SilentlyContinue
if (-not $pandoc) {
    Write-Warning "  Pandoc not found. Word export will fall back to anthropic-skills:docx."
    Write-Warning "  Optional: winget install --id JohnMacFarlane.Pandoc"
} else {
    Write-Host "  Pandoc: $(& pandoc --version | Select-Object -First 1)"
}

# 3. Probe LibreOffice (for Word -> PDF rendering for visual validation)
$libreoffice = Get-Command soffice -ErrorAction SilentlyContinue
if (-not $libreoffice) {
    Write-Warning "  LibreOffice not found. Visual validation of .docx will be skipped."
    Write-Warning "  Optional: winget install --id TheDocumentFoundation.LibreOffice"
} else {
    Write-Host "  LibreOffice: $($libreoffice.Source)"
}

# 4. Probe pdflatex
$pdflatex = Get-Command pdflatex -ErrorAction SilentlyContinue
if (-not $pdflatex) {
    Write-Warning "  pdflatex not found. LaTeX compile will be skipped (manuscript.tex still produced)."
    Write-Warning "  Install MiKTeX: winget install --id MiKTeX.MiKTeX"
} else {
    Write-Host "  pdflatex: $($pdflatex.Source)"
}

# 5. Probe pdftoppm (poppler) for visual validation
$pdftoppm = Get-Command pdftoppm -ErrorAction SilentlyContinue
if (-not $pdftoppm) {
    Write-Warning "  pdftoppm not found. PDF -> PNG rendering for visual validation will be skipped."
    Write-Warning "  Install poppler: winget install --id oschwartz10612.Poppler"
}

# 6. Ensure ~/.vedix/ exists (VEDIX_HOME preferred; legacy AI_SCIENTIST_HOME respected)
$vedixHome = if ($env:VEDIX_HOME) { $env:VEDIX_HOME } `
             elseif ($env:AI_SCIENTIST_HOME) { $env:AI_SCIENTIST_HOME } `
             else { "$env:USERPROFILE\.vedix" }
if (-not (Test-Path $vedixHome)) {
    New-Item -ItemType Directory -Path $vedixHome | Out-Null
    Write-Host "  Created $vedixHome"
} else {
    Write-Host "  Found existing $vedixHome"
}

# 7. Pip-install MCP dependencies (user-site)
Write-Host "Installing MCP requirements..." -ForegroundColor Cyan
Invoke-Native -Description "pip install -r mcp/requirements.txt" -Script {
    python -m pip install --user --quiet -r "$PluginRoot\mcp\requirements.txt"
}
Write-Host "  MCP requirements OK"

# 7a-bis. Install MemPalace (per-project memory DB MCP)
Write-Host "Installing MemPalace MCP server..." -ForegroundColor Cyan
Invoke-Native -Description "pip install mempalace" -Script {
    python -m pip install --user --quiet mempalace
}
Write-Host "  mempalace package OK"
$mempalacePath = "$vedixHome\palace"
if (-not (Test-Path $mempalacePath)) {
    New-Item -ItemType Directory -Path $mempalacePath -Force | Out-Null
}
$mempalaceCmd = Get-Command mempalace -ErrorAction SilentlyContinue
if ($mempalaceCmd) {
    Write-Host "  mempalace: $($mempalaceCmd.Source)"
    Invoke-Native -IgnoreExitCode -Description "mempalace init" -Script {
        mempalace init "$mempalacePath" *>&1 | Out-Null
    }
    Write-Host "  Per-project palace root: $mempalacePath"
} else {
    Write-Warning "  mempalace command not on PATH after install. Re-open shell and re-run, or set %PATH% manually."
}

# 7b. Install third-party literature MCP servers
Write-Host "Installing third-party literature MCP servers..." -ForegroundColor Cyan

# OpenAlex (drAbreu/alex-mcp) -- installed on demand by uvx; just probe uvx.
$uvx = Get-Command uvx -ErrorAction SilentlyContinue
if (-not $uvx) {
    Write-Warning "  uvx not found. OpenAlex MCP requires uvx. Install:"
    Write-Warning "    pip install --user uv  # or  winget install astral-sh.uv"
} else {
    Write-Host "  uvx: $($uvx.Source) -- alex-mcp will be auto-installed on first MCP start"
}

# Clone helper
function Install-GitMcp {
    param([string]$RepoUrl, [string]$DirName, [string]$EntryFile)
    $target = "$vedixHome\external\$DirName"
    if (-not (Test-Path $target)) {
        Write-Host "  Cloning $RepoUrl..."
        Invoke-Native -Description "git clone $RepoUrl" -Script {
            git clone --depth=1 $RepoUrl $target *>&1 | Out-Null
        }
    } else {
        Write-Host "  $DirName already cloned at $target"
    }
    if (-not (Test-Path "$target\$EntryFile")) {
        Write-Warning "  $DirName clone failed or missing entry $EntryFile; re-run install.ps1 or clone manually."
        return
    }
    if (Test-Path "$target\requirements.txt") {
        Invoke-Native -IgnoreExitCode -Description "pip install $DirName requirements" -Script {
            python -m pip install --user --quiet -r "$target\requirements.txt" *>&1 | Out-Null
        }
    }
    Write-Host "  $DirName deps installed"
}

# Ensure ~/.vedix/external/ exists
if (-not (Test-Path "$vedixHome\external")) {
    New-Item -ItemType Directory -Path "$vedixHome\external" | Out-Null
}

# Semantic Scholar MCP
Install-GitMcp `
    -RepoUrl "https://github.com/JackKuo666/semanticscholar-MCP-Server.git" `
    -DirName "semanticscholar-MCP-Server" `
    -EntryFile "semantic_scholar_server.py"

# bioRxiv MCP
Install-GitMcp `
    -RepoUrl "https://github.com/JackKuo666/bioRxiv-MCP-Server.git" `
    -DirName "bioRxiv-MCP-Server" `
    -EntryFile "biorxiv_server.py"

# Sci-Hub MCP -- complements Anna's Archive for paywalled-content fetching.
# Different mirror rotation, no fast-download quota, different rate-limit
# behavior. The literature-searcher tries scihub when annas returns 429.
Install-GitMcp `
    -RepoUrl "https://github.com/JackKuo666/Sci-Hub-MCP-Server.git" `
    -DirName "Sci-Hub-MCP-Server" `
    -EntryFile "sci_hub_server.py"

# Patch Sci-Hub MCP's mirror list. Upstream ships dead mirrors; override
# with live ones. Idempotent via patch-marker check.
Invoke-Native -IgnoreExitCode -Description "patch scihub mirrors" -Script {
    python "$PluginRoot\scripts\patch_scihub_mirrors.py" 2>&1
}

# Reminder about required env vars for the literature MCPs
if (-not $env:OPENALEX_EMAIL) {
    Write-Warning "  OPENALEX_EMAIL is not set. Polite-pool throttle (1 req/s instead of 10) will apply."
    Write-Warning "  Set: setx OPENALEX_EMAIL `"your-email@example.com`""
}
if (-not $env:SEMANTIC_SCHOLAR_KEY) {
    Write-Warning "  SEMANTIC_SCHOLAR_KEY is not set. Semantic Scholar /search will be skipped."
    Write-Warning "  Get a key: https://www.semanticscholar.org/product/api"
    Write-Warning "  Set: setx SEMANTIC_SCHOLAR_KEY `"your-key`""
}

# 8. MCP self-test
Write-Host "Running MCP self-test..." -ForegroundColor Cyan
$selftest = $null
try {
    $previousEAP = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $selftest = (& python "$PluginRoot\mcp\server.py" --selftest 2>&1) -join "`n"
    $selftestCode = $LASTEXITCODE
    $ErrorActionPreference = $previousEAP
    if ($selftestCode -ne 0) {
        Write-Error "MCP selftest failed (exit $selftestCode):`n$selftest"
        exit 1
    }
} catch {
    Write-Error "MCP selftest threw: $_`n$selftest"
    exit 1
}
Write-Host "  $selftest"

# 9. Knowledge DB stats
$dbPath = "$vedixHome\knowledge.db"
if (Test-Path $dbPath) {
    $size = [math]::Round((Get-Item $dbPath).Length / 1KB, 1)
    Write-Host "  knowledge.db: $size KB"
}

Write-Host ""
Write-Host "Install complete." -ForegroundColor Green
Write-Host "Next: add the marketplace and install the plugin:"
Write-Host "  /plugin marketplace add danilkotelnikov/vedix"
Write-Host "  /plugin install vedix@vedix"
