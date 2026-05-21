$ErrorActionPreference = "Stop"
$PluginRoot = Split-Path -Parent $PSScriptRoot

Write-Host "=== Static checks ===" -ForegroundColor Cyan
& python -m pytest "$PluginRoot\tests\test_static_checks.py" -v
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host ""
Write-Host "=== MCP smoke test ===" -ForegroundColor Cyan
& python "$PluginRoot\mcp\server.py" --selftest
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host ""
Write-Host "=== Routing tests ===" -ForegroundColor Cyan
& python -m pytest "$PluginRoot\tests\test_routing.py" -v
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host ""
Write-Host "=== Settings schema validation ===" -ForegroundColor Cyan
& python -c "import json, jsonschema; jsonschema.validate(json.load(open(r'$PluginRoot\settings\default-settings.json')), json.load(open(r'$PluginRoot\settings\settings.schema.json')))"
if ($LASTEXITCODE -ne 0) { exit 1 }
Write-Host "  default-settings.json validates against schema. OK"

Write-Host ""
Write-Host "All checks passed." -ForegroundColor Green
