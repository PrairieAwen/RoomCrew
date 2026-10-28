<# 因为多个独立发行目录会导致不同会话启动不同程序，需要只按项目启动清单解析同一程序和数据目录。 #>
param(
    [switch]$Check,
    [string]$DataDir
)
$ErrorActionPreference = 'Stop'

# 1、清单使用固定位置，不根据目录名字、修改时间或历史聊天猜测当前版本。
$roomcrewRoot = $PSScriptRoot
$roomcrewManifestPath = Join-Path $roomcrewRoot 'packaging/active-release.json'
$roomcrewManifest = Get-Content -LiteralPath $roomcrewManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($roomcrewManifest.schema_version -ne 1 -or [string]::IsNullOrWhiteSpace($roomcrewManifest.release_id)) {
    throw 'RoomCrew 启动清单格式无效'
}

# 2、发行入口必须位于项目 dist 内且保留完整运行目录；缺失时不回退启动旧版本。
$roomcrewExeRelative = [string]$roomcrewManifest.executable
if ([string]::IsNullOrWhiteSpace($roomcrewExeRelative) -or [IO.Path]::IsPathRooted($roomcrewExeRelative)) {
    throw '启动清单必须指定项目内的发行入口'
}
$roomcrewExe = [IO.Path]::GetFullPath((Join-Path $roomcrewRoot $roomcrewExeRelative))
$roomcrewDistPrefix = [IO.Path]::GetFullPath((Join-Path $roomcrewRoot 'dist')).TrimEnd('\') + '\'
if (-not $roomcrewExe.StartsWith($roomcrewDistPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'RoomCrew 发行入口越界'
}
$roomcrewProgram = [IO.Path]::GetDirectoryName($roomcrewExe)
foreach ($roomcrewRequired in @($roomcrewExe, (Join-Path $roomcrewProgram '_internal/python313.dll'), (Join-Path $roomcrewProgram '_internal/desktop/ui/index.html'))) {
    if (-not (Test-Path -LiteralPath $roomcrewRequired -PathType Leaf)) {
        throw ('当前发行不完整，请构建或修正启动清单；不会自动改用历史版本：' + $roomcrewRequired)
    }
}

# 3、数据目录和程序版本分别声明；显式覆盖只影响这次启动，不复制密钥、数据库或修改清单。
$roomcrewConfiguredData = [string]$roomcrewManifest.data_directory
if ($DataDir) {
    $roomcrewData = [IO.Path]::GetFullPath($DataDir)
} elseif ($roomcrewConfiguredData) {
    if ([IO.Path]::IsPathRooted($roomcrewConfiguredData)) { throw '清单数据目录必须相对项目保存' }
    $roomcrewData = [IO.Path]::GetFullPath((Join-Path $roomcrewRoot $roomcrewConfiguredData))
    if (-not $roomcrewData.StartsWith($roomcrewRoot.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw '清单数据目录越界'
    }
} else {
    $roomcrewData = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'RoomCrew'))
}
if ($roomcrewData.Contains('"')) { throw '数据目录包含无效引号' }
$roomcrewInfo = [ordered]@{
    release_id = $roomcrewManifest.release_id
    executable = $roomcrewExe
    data_directory = $roomcrewData
}

# 4、只检查模式不启动窗口；各会话先读取这份实际选择，再复用对应窗口或启动。
if ($Check) {
    [pscustomobject]$roomcrewInfo
    return
}
# 5、参数作为路径传递，不拼接 shell 命令；由应用现有数据根锁保护同一数据目录。
Start-Process -FilePath $roomcrewExe -ArgumentList @('--data-dir', ('"' + $roomcrewData + '"')) -WorkingDirectory $roomcrewProgram -WindowStyle Hidden | Out-Null
[pscustomobject]$roomcrewInfo
