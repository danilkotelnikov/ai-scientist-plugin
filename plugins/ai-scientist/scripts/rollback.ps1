param(
    [Parameter(Mandatory=$true)] [string]$Timestamp
)
$ErrorActionPreference = "Stop"
$BackupDir = "$env:USERPROFILE\.claude\backups\ai-scientist-skill-$Timestamp"
$Restore = "$env:USERPROFILE\.claude\skills\ai-scientist"

if (-not (Test-Path $BackupDir)) {
    Write-Error "No backup at $BackupDir"
    exit 1
}
if (Test-Path $Restore) {
    Write-Error "$Restore already exists. Move it aside first."
    exit 1
}
Move-Item -Path $BackupDir -Destination $Restore
Write-Host "Restored $BackupDir -> $Restore" -ForegroundColor Green
Write-Host "Note: plugin still installed. To uninstall, run: /plugin uninstall ai-scientist"
