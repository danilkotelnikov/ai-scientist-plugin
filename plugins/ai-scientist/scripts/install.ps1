# install.ps1 — one-time setup for ai-scientist plugin
$ErrorActionPreference = "Stop"
$PluginRoot = Split-Path -Parent $PSScriptRoot

Write-Host "AI-Scientist plugin install starting..." -ForegroundColor Cyan

# 1. Probe Python
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Error "Python not found in PATH. Install Python 3.11+ and re-run."
    exit 1
}
$pyver = & python --version 2>&1
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

# 6. Ensure ~/.ai-scientist/ exists
$aiHome = "$env:USERPROFILE\.ai-scientist"
if (-not (Test-Path $aiHome)) {
    New-Item -ItemType Directory -Path $aiHome | Out-Null
    Write-Host "  Created $aiHome"
} else {
    Write-Host "  Found existing $aiHome"
}

# 7. Pip-install MCP dependencies (user-site)
Write-Host "Installing MCP requirements..." -ForegroundColor Cyan
& python -m pip install --user -r "$PluginRoot\mcp\requirements.txt"

# 7a. Install third-party literature MCP servers
Write-Host "Installing third-party literature MCP servers..." -ForegroundColor Cyan

# OpenAlex (drAbreu/alex-mcp) — installed on demand by uvx; just probe uvx.
$uvx = Get-Command uvx -ErrorAction SilentlyContinue
if (-not $uvx) {
    Write-Warning "  uvx not found. OpenAlex MCP requires uvx. Install:"
    Write-Warning "    pip install --user uv  # or  winget install astral-sh.uv"
} else {
    Write-Host "  uvx: $($uvx.Source) — alex-mcp will be auto-installed on first MCP start"
}

# Semantic Scholar (JackKuo666/semanticscholar-MCP-Server) — clone + pip-install deps
$ssExternal = "$aiHome\external\semanticscholar-MCP-Server"
if (-not (Test-Path "$aiHome\external")) {
    New-Item -ItemType Directory -Path "$aiHome\external" | Out-Null
}
if (-not (Test-Path $ssExternal)) {
    Write-Host "  Cloning JackKuo666/semanticscholar-MCP-Server..."
    & git clone --depth=1 "https://github.com/JackKuo666/semanticscholar-MCP-Server.git" $ssExternal 2>&1 | Out-Null
    if (-not (Test-Path "$ssExternal\semantic_scholar_server.py")) {
        Write-Warning "  semanticscholar MCP clone failed; the source will be unavailable until you re-run install.ps1 or clone manually."
    } else {
        & python -m pip install --user -r "$ssExternal\requirements.txt" 2>&1 | Select-Object -Last 2
        Write-Host "  semanticscholar MCP cloned + deps installed"
    }
} else {
    Write-Host "  semanticscholar MCP already cloned at $ssExternal"
    & python -m pip install --user -q -r "$ssExternal\requirements.txt" 2>&1 | Out-Null
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
$selftest = & python "$PluginRoot\mcp\server.py" --selftest 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error "MCP selftest failed:`n$selftest"
    exit 1
}
Write-Host "  $selftest"

# 9. Knowledge DB stats
$dbPath = "$aiHome\knowledge.db"
if (Test-Path $dbPath) {
    $size = [math]::Round((Get-Item $dbPath).Length / 1KB, 1)
    Write-Host "  knowledge.db: $size KB"
}

Write-Host ""
Write-Host "Install complete." -ForegroundColor Green
Write-Host "Next: run scripts\migrate-from-skill.ps1 to archive the old skill, then add the marketplace:"
Write-Host "  /plugin marketplace add danilkotelnikov/ai-scientist-plugin"
Write-Host "  /plugin install ai-scientist@ai-scientist-plugin"
