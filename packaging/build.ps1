# 因为 Windows 用户需要完整独立程序，需要先在缓存构建，成功后再发布完整发行目录。
$ErrorActionPreference = 'Stop'
$roomcrewRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$roomcrewPython = Join-Path $roomcrewRoot '.venv/Scripts/python.exe'
$roomcrewStage = Join-Path $roomcrewRoot ('.cache/release-build-' + [guid]::NewGuid().ToString('N'))

# 1、PyInstaller 只操作新的缓存目录，构建失败不会删除用户正在使用的 dist。
Push-Location -LiteralPath $roomcrewRoot
try {
    & $roomcrewPython -X utf8 packaging/prepare_python_runtime.py
    if ($LASTEXITCODE -ne 0) { throw '随包 Python 运行时准备失败' }
    & $roomcrewPython -m PyInstaller packaging/RoomCrew.spec --distpath $roomcrewStage --workpath .cache/pyinstaller --noconfirm
    if ($LASTEXITCODE -ne 0) { throw 'Windows 程序构建失败，原发行目录未改动' }
    # 2、完整候选交给统一发布入口，运行中拒绝替换并保留候选，不结束用户任务。
    & (Join-Path $PSScriptRoot 'publish.ps1') -Candidate (Join-Path $roomcrewStage 'RoomCrew')
} finally {
    Pop-Location
}
