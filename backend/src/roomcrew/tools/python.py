"""Agent 的 Python 脚本工具；输入输出只经过会话文件副本。"""

import asyncio
import json
import os
import shutil
import sys
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

from langchain_core.tools import BaseTool, StructuredTool

from roomcrew.contracts.errors import ExecutionError
from roomcrew.security.appcontainer import run_container
from roomcrew.security.paths import resolve_task_path


def python_runtime(cache: Path) -> Path:
    """因为执行脚本不能复用含模型配置的宿主解释器，需要定位并复制随包分发的标准库运行时。"""
    # 1、只接受固定资源目录，不搜索用户 PATH，不回退到 sys.executable 或系统 Python。
    bundle = getattr(sys, "_MEIPASS", None)
    project = Path(__file__).resolve().parents[4]
    source = Path(bundle) / "python-runtime" if bundle else project / ".cache/python-runtime"
    if os.name != "nt" or not (source / "python.exe").is_file():
        raise ExecutionError("PYTHON_UNAVAILABLE")
    # 2、用户可写副本用于 AppContainer 专属只读 ACL，不修改安装目录权限。
    target = cache / "python-runtime"
    if not (target / "runtime.json").is_file():
        shutil.copytree(source, target, dirs_exist_ok=True)
    return target / "python.exe"


def task_files(root: Path) -> list[Path]:
    """因为脚本副本与产物不能带出符号链接，需要在复制前检查文件类型、数量和总大小。"""
    # 1、禁止重解析点；工具只处理最多 256 个、合计 32 MB 的普通任务文件。
    files = []
    total = 0
    for path in root.rglob("*"):
        if path.is_symlink() or path.is_junction():
            raise ValueError("Python 输入输出不能包含符号链接或目录联接")
        if path.is_file() and ".roomcrew-output" not in path.relative_to(root).parts:
            total += path.stat().st_size
            files.append(path)
            if len(files) > 256 or total > 32 * 1024 * 1024:
                raise ValueError("Python 输入输出超过文件数量或大小限制")
    return files


def run_script(
    root: Path, cache: Path, script_path: str, timeout: int, cancelled: threading.Event
) -> dict[str, Any]:
    """因为生成代码可能读取宿主秘密，需要在专属 AppContainer 副本执行后验证并回收真实产物。"""
    # 1、只运行已写入会话的 Python 文件，脚本名不能指向应用私有目录。
    script = resolve_task_path(root, script_path)
    if script.suffix.lower() != ".py" or not script.is_file() or script.stat().st_size > 256000:
        raise ValueError("请先在任务目录写入不超过 256 KB 的 .py 脚本")
    executable = python_runtime(cache)
    work = cache / "script-runs" / uuid4().hex
    work.mkdir(parents=True)
    try:
        for path in task_files(root):
            destination = work / path.relative_to(root)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
        # 2、隔离进程不继承宿主环境或句柄；取消和超时会终止整个 Job。
        result = run_container(
            executable, work / script.relative_to(root), work, timeout, cancelled
        )
        changed = []
        if result["exit_code"] == 0 and not result["reason"]:
            for path in task_files(work):
                relative = path.relative_to(work)
                destination = resolve_task_path(root, "/" + relative.as_posix())
                if not destination.is_file() or destination.read_bytes() != path.read_bytes():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path, destination)
                    changed.append("/" + relative.as_posix())
        result["artifacts"] = changed
        return result
    finally:
        # 3、删除范围由固定缓存根与随机目录生成并再次校验，不跟随用户输入路径。
        if work.resolve().is_relative_to((cache / "script-runs").resolve()):
            shutil.rmtree(work, ignore_errors=True)


def python_tool(root: Path, cache: Path, lock: asyncio.Lock | None = None) -> BaseTool:
    """因为代码执行需要出现在真实工具循环中，需要创建有界且可取消的隔离 Python 工具。"""
    # 1、路径和缓存由可信组装点固定，模型只能选择会话内脚本和有限超时。
    slot = lock or asyncio.Lock()

    async def execute_python(script_path: str, timeout_seconds: int = 30) -> str:
        """因为计算任务需要真实执行生成代码，需要运行会话内 .py 脚本并返回标准输出和产物。"""
        # 1、限定超时，取消时通知原生 Job，不能留下后台继续执行的脚本。
        if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 120:
            raise ValueError("脚本超时必须是 1～120 秒整数")
        cancelled = threading.Event()
        async with slot:
            task = asyncio.create_task(
                asyncio.to_thread(run_script, root, cache, script_path, timeout_seconds, cancelled)
            )
            try:
                return json.dumps(await asyncio.shield(task), ensure_ascii=False)
            except asyncio.CancelledError:
                cancelled.set()
                await task
                raise

    return StructuredTool.from_function(
        coroutine=execute_python, name="execute_python", metadata={"roomcrew_tool_kind": "python"}
    )
