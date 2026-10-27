"""从项目锁定的 CPython 制作独立脚本解释器，随桌面包分发。"""

import json
import shutil
import sys
import zipfile
from pathlib import Path


def prepare_runtime() -> Path:
    """因为用户未安装 Python 也应执行脚本，需要把可信解释器和标准库装配为独立资源。"""
    # 1、只从当前锁定 Python 复制，不打包开发依赖、模型库或用户配置。
    root = Path(__file__).resolve().parents[1]
    destination = root / ".cache/python-runtime"
    base = Path(sys.base_prefix)
    marker = destination / "runtime.json"
    if marker.is_file() and json.loads(marker.read_text("utf-8")).get("version") == sys.version:
        return destination
    destination.mkdir(parents=True, exist_ok=True)
    for name in (
        "python.exe",
        "python3.dll",
        "python313.dll",
        "vcruntime140.dll",
        "vcruntime140_1.dll",
        "LICENSE.txt",
    ):
        source = base / name
        if source.is_file():
            shutil.copy2(source, destination / name)
    # 2、扩展模块仅来自 CPython 标准 DLLs；标准库压缩成可直接导入的 zip。
    for source in (base / "DLLs").iterdir():
        if source.suffix.lower() in {".pyd", ".dll"}:
            shutil.copy2(source, destination / source.name)
    excluded = {
        "site-packages",
        "__pycache__",
        "test",
        "tests",
        "idlelib",
        "tkinter",
        "ensurepip",
        "turtledemo",
    }
    with zipfile.ZipFile(destination / "python313.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for source in (base / "Lib").rglob("*.py"):
            relative = source.relative_to(base / "Lib")
            if not set(relative.parts) & excluded:
                archive.write(source, relative.as_posix())
    # 3、独立搜索路径不加载用户 site、环境变量或应用自身的依赖与密钥工厂。
    (destination / "python313._pth").write_text("python313.zip\n.\n", encoding="utf-8")
    marker.write_text(json.dumps({"version": sys.version, "stdlib_only": True}), encoding="utf-8")
    if not (destination / "python.exe").is_file() or not (destination / "python313.dll").is_file():
        raise RuntimeError("未找到可分发的 CPython 解释器")
    return destination


if __name__ == "__main__":
    print(prepare_runtime())
