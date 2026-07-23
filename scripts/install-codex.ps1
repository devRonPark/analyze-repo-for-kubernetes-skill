param(
    [string]$TargetRoot = "$HOME\.agents\skills"
)

$ErrorActionPreference = "Stop"
$SourceDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$TargetDir = Join-Path $TargetRoot "analyze-repo-for-kubernetes"

New-Item -ItemType Directory -Force -Path $TargetRoot | Out-Null
if (Test-Path $TargetDir) {
    Remove-Item -Recurse -Force $TargetDir
}
Copy-Item -Recurse -Force $SourceDir $TargetDir

Write-Host "Installed: $TargetDir"
Write-Host "Restart Codex if the skill does not appear automatically."
