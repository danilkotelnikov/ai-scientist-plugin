$ErrorActionPreference = "Stop"
$PluginRoot = Split-Path -Parent $PSScriptRoot
$OldSkill = "$env:USERPROFILE\.claude\skills\ai-scientist"
$BackupRoot = "$env:USERPROFILE\.claude\backups"
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"

if (-not (Test-Path $OldSkill)) {
    Write-Host "No legacy skill found at $OldSkill. Nothing to migrate." -ForegroundColor Yellow
    exit 0
}

# 1. Archive old skill
if (-not (Test-Path $BackupRoot)) {
    New-Item -ItemType Directory -Path $BackupRoot | Out-Null
}
$BackupDir = "$BackupRoot\ai-scientist-skill-$Timestamp"
Move-Item -Path $OldSkill -Destination $BackupDir
Write-Host "Archived $OldSkill -> $BackupDir" -ForegroundColor Green

# 2. Verify plugin assets
$RequiredFiles = @(
    "$PluginRoot\.claude-plugin\plugin.json",
    "$PluginRoot\skills\ai-scientist\SKILL.md",
    "$PluginRoot\mcp\server.py",
    "$PluginRoot\mcp\.mcp.json"
)
foreach ($f in $RequiredFiles) {
    if (-not (Test-Path $f)) {
        Write-Error "Missing required plugin file: $f"
        exit 1
    }
}
Write-Host "Plugin assets verified."

# 3. MCP selftest
$selftest = & python "$PluginRoot\mcp\server.py" --selftest 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error "MCP selftest failed after migration:`n$selftest"
    Write-Error "Restoring backup..."
    Move-Item -Path $BackupDir -Destination $OldSkill
    exit 1
}

# 4. Knowledge DB sanity
$dbPath = "$env:USERPROFILE\.ai-scientist\knowledge.db"
if (Test-Path $dbPath) {
    $size = [math]::Round((Get-Item $dbPath).Length / 1KB, 1)
    $jobsPath = "$env:USERPROFILE\.ai-scientist\jobs.json"
    $jobCount = 0
    if (Test-Path $jobsPath) {
        $jobs = Get-Content $jobsPath | ConvertFrom-Json
        $jobCount = ($jobs | Get-Member -MemberType NoteProperty).Count
    }
    Write-Host "  knowledge.db: $size KB, jobs registered: $jobCount" -ForegroundColor Green
}

Write-Host ""
Write-Host "Migration complete." -ForegroundColor Green
Write-Host "  Backup: $BackupDir"
Write-Host "  Test: /ai-scientist-list"
Write-Host "  Rollback: scripts\rollback.ps1 $Timestamp"
