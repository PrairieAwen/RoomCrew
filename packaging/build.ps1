# 因为 Windows 用户需要完整独立程序，需要从锁定依赖构建并打包整个发行目录。
$ErrorActionPreference = 'Stop'
$roomcrewRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$roomcrewPython = Join-Path $roomcrewRoot '.venv/Scripts/python.exe'
$roomcrewDist = Join-Path $roomcrewRoot 'dist'

# 1、从明确的项目根运行，避免路径变化影响界面资源和打包目录。
Push-Location -LiteralPath $roomcrewRoot
try {
    & $roomcrewPython -m PyInstaller packaging/RoomCrew.spec --distpath dist --workpath .cache/pyinstaller --noconfirm
    if ($LASTEXITCODE -ne 0) { throw 'Windows 程序构建失败' }
    # 2、使用说明随应用分发，用户无需打开源码寻找运行步骤。
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot '使用说明.txt') -Destination (Join-Path $roomcrewDist 'RoomCrew/使用说明.txt') -Force
    # 3、压缩整个目录，保留 exe 所需运行库；版本包属于构建产物，不提交 Git。
    $roomcrewArchive = Join-Path $roomcrewDist 'RoomCrew-0.1.0-windows-x64.zip'
    Compress-Archive -LiteralPath (Join-Path $roomcrewDist 'RoomCrew') -DestinationPath $roomcrewArchive -Force
    Get-FileHash -LiteralPath $roomcrewArchive -Algorithm SHA256
} finally {
    Pop-Location
}
