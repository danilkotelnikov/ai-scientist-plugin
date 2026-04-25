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
