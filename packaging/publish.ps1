# 因为构建失败不能破坏正在使用的程序，需要先验证完整候选，再以目录替换发布。
param([Parameter(Mandatory = $true)][string]$Candidate)
$ErrorActionPreference = 'Stop'
$roomcrewRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$roomcrewPrefix = $roomcrewRoot.TrimEnd('\') + '\'
$roomcrewCache = Join-Path $roomcrewRoot '.cache'
$roomcrewCandidate = (Resolve-Path -LiteralPath $Candidate).Path
$roomcrewDist = Join-Path $roomcrewRoot 'dist/RoomCrew'
$roomcrewBackup = Join-Path $roomcrewCache ('release-backup-' + [guid]::NewGuid().ToString('N'))
$roomcrewZip = Join-Path $roomcrewRoot 'dist/RoomCrew-0.1.0-windows-x64.zip'
$roomcrewZipStage = Join-Path $roomcrewCache ('release-' + [guid]::NewGuid().ToString('N') + '.zip')

# 1、递归移动和清理只允许发生在已核实的项目范围，候选必须来自本项目缓存。
foreach ($roomcrewPath in @($roomcrewCandidate, $roomcrewDist, $roomcrewBackup, $roomcrewZipStage, $roomcrewZip)) {
    if (-not [IO.Path]::GetFullPath($roomcrewPath).StartsWith($roomcrewPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw '发行操作路径超出项目目录'
    }
}
if (-not $roomcrewCandidate.StartsWith($roomcrewCache + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw '候选程序必须位于项目 .cache 目录'
}
foreach ($roomcrewRequired in @('RoomCrew.exe', '_internal/python313.dll', '_internal/desktop/ui/index.html')) {
    if (-not (Test-Path -LiteralPath (Join-Path $roomcrewCandidate $roomcrewRequired) -PathType Leaf)) {
        throw ('候选程序不完整：' + $roomcrewRequired)
    }
}

# 2、程序仍在运行时不移动任何文件；完整候选保留，便于关闭后直接再次发布。
$roomcrewLiveExe = Join-Path $roomcrewDist 'RoomCrew.exe'
foreach ($roomcrewProcess in @(Get-Process -Name RoomCrew -ErrorAction SilentlyContinue)) {
    if ($roomcrewProcess.Path -eq $roomcrewLiveExe) {
        throw ('请先关闭当前 RoomCrew；本次完整候选已保留在 ' + $roomcrewCandidate)
    }
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot '使用说明.txt') -Destination (Join-Path $roomcrewCandidate '使用说明.txt') -Force
New-Item -ItemType Directory -Path (Join-Path $roomcrewRoot 'dist') -Force | Out-Null

# 3、先移出旧目录再安放完整候选；安放失败时恢复旧目录，避免逐文件删除或半覆盖。
$roomcrewHadOld = Test-Path -LiteralPath $roomcrewDist
try {
    if ($roomcrewHadOld) { Move-Item -LiteralPath $roomcrewDist -Destination $roomcrewBackup }
    Move-Item -LiteralPath $roomcrewCandidate -Destination $roomcrewDist
} catch {
    if ((Test-Path -LiteralPath $roomcrewBackup) -and -not (Test-Path -LiteralPath $roomcrewDist)) {
        Move-Item -LiteralPath $roomcrewBackup -Destination $roomcrewDist
    }
    throw
}

# 4、压缩先写独立文件，完整生成后才替换原 ZIP；成功后清理旧程序缓存。
Compress-Archive -LiteralPath $roomcrewDist -DestinationPath $roomcrewZipStage
Move-Item -LiteralPath $roomcrewZipStage -Destination $roomcrewZip -Force
if (Test-Path -LiteralPath $roomcrewBackup) {
    Remove-Item -LiteralPath $roomcrewBackup -Recurse -Force
}
Get-FileHash -LiteralPath $roomcrewZip -Algorithm SHA256
