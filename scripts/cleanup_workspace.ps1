param(
    [switch]$Apply,
    [switch]$IncludeDist
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ProjectRootPrefix = $ProjectRoot.TrimEnd([char]92) + [string]([char]92)
$Targets = @()

function Test-InProject {
    param([string]$Path)
    return $Path.StartsWith($ProjectRootPrefix, [System.StringComparison]::OrdinalIgnoreCase)
}

function Add-Target {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    $resolved = (Resolve-Path -LiteralPath $Path).Path
    if (-not (Test-InProject $resolved)) {
        throw "拒绝处理项目目录外路径: $resolved"
    }

    if ($script:Targets -notcontains $resolved) {
        $script:Targets += $resolved
    }
}

function Get-DirectorySize {
    param([string]$Path)
    $size = 0
    $files = Get-ChildItem -LiteralPath $Path -Force -Recurse -File -ErrorAction SilentlyContinue
    foreach ($file in $files) {
        $size += $file.Length
    }
    return $size
}

$KnownGenerated = @(
    ".pytest_cache",
    ".pytest-tmp",
    ".tmp",
    "build",
    ".venv\pytest-tmp-final"
)

foreach ($relative in $KnownGenerated) {
    Add-Target (Join-Path $ProjectRoot $relative)
}

$pytestDirs = Get-ChildItem -LiteralPath $ProjectRoot -Force -Directory -Filter ".pytest-*" -ErrorAction SilentlyContinue
foreach ($dir in $pytestDirs) {
    Add-Target $dir.FullName
}

$pytestCacheDirs = Get-ChildItem -LiteralPath $ProjectRoot -Force -Directory -Filter "pytest-cache-files-*" -ErrorAction SilentlyContinue
foreach ($dir in $pytestCacheDirs) {
    Add-Target $dir.FullName
}

foreach ($rootName in @("src", "tests")) {
    $rootPath = Join-Path $ProjectRoot $rootName
    if (Test-Path -LiteralPath $rootPath) {
        $cacheDirs = Get-ChildItem -LiteralPath $rootPath -Force -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue
        foreach ($dir in $cacheDirs) {
            Add-Target $dir.FullName
        }
    }
}

if ($IncludeDist) {
    Add-Target (Join-Path $ProjectRoot "dist")
}

if ($Targets.Count -eq 0) {
    Write-Host "未发现需要清理的生成文件。"
    exit 0
}

Write-Host "将清理以下生成文件/目录："
foreach ($target in $Targets) {
    $sizeMb = [Math]::Round((Get-DirectorySize $target) / 1MB, 2)
    Write-Host ("- {0} ({1} MB)" -f $target, $sizeMb)
}

if (-not $Apply) {
    Write-Host ""
    Write-Host "当前为预览模式，未删除任何文件。确认无误后，加 -Apply 执行删除。"
    Write-Host "如需同时清理本地 dist 构建产物，额外加 -IncludeDist。"
    exit 0
}

foreach ($target in $Targets) {
    Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction Stop
    Write-Host "已删除: $target"
}