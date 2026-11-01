# 用法: .\install.ps1 [-Dest 目标技能目录] [-Names ai-profile,profile-start,...]
param(
    [string]$Dest = (Join-Path $HOME '.claude\skills'),
    [string[]]$Names = @('ai-profile', 'profile-start', 'profile-stop', 'profile-mark', 'profile-gui')
)
$ErrorActionPreference = 'Stop'
$src = Join-Path $PSScriptRoot 'skills'
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
foreach ($n in $Names) {
    $from = Join-Path $src $n
    if (-not (Test-Path -LiteralPath $from)) { throw "未找到技能: $n" }
    $to = Join-Path $Dest $n
    if (Test-Path -LiteralPath $to) { Remove-Item -LiteralPath $to -Recurse -Force }
    Copy-Item -LiteralPath $from -Destination $to -Recurse
    Get-ChildItem -LiteralPath $to -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
    Write-Host "已安装 $n -> $to"
}
