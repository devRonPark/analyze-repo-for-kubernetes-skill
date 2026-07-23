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

Write-Host "설치 완료: $TargetDir"
Write-Host "스킬이 자동으로 표시되지 않으면 Codex를 다시 시작하세요."
