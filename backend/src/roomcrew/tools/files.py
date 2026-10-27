"""补足 SDK 文本工具之外的通用会话文件操作。"""

import json
import shutil
from pathlib import Path

from langchain_core.tools import BaseTool, StructuredTool

from roomcrew.security.paths import resolve_task_path


def file_tools(root: Path) -> list[BaseTool]:
    """因为所有 Agent 都需要完整管理任务文件，需要统一注册与具体任务格式无关的补充工具。"""
    # 1、路径固定在当前会话；SDK 继续提供文本读写、替换、搜索，不重复实现同名能力。

    def file_info(path: str) -> str:
        """因为模型需要先确认文件是否存在和大小，需要查询会话路径的元信息而不读取文件正文。"""
        # 1、缺失路径返回 exists=false，目录与任意格式文件均可查询。
        target = resolve_task_path(root, path)
        if not target.exists():
            return json.dumps({"path": path, "exists": False})
        stat = target.stat()
        return json.dumps(
            {
                "path": path,
                "exists": True,
                "kind": "directory" if target.is_dir() else "file",
                "bytes": stat.st_size if target.is_file() else None,
                "modified_ns": stat.st_mtime_ns,
            }
        )

    def make_directory(path: str) -> str:
        """因为交付物经常需要分层目录，需要创建任务目录并允许已存在的目录保持原样。"""
        # 1、父目录按需建立；同名文件会明确失败，不能把它误当目录。
        target = resolve_task_path(root, path)
        target.mkdir(parents=True, exist_ok=True)
        return json.dumps({"path": path, "created": True})

    def copy_file(source: str, destination: str) -> str:
        """因为资料可能是文本或二进制文件，需要按原始字节复制而不让模型重新编码内容。"""
        # 1、拒绝覆盖已存在产物；复制新版本时由 Agent 明确选择另一个路径。
        src, dst = file_pair(root, source, destination)
        dst.parent.mkdir(parents=True, exist_ok=True)
        with src.open("rb") as incoming, dst.open("xb") as outgoing:
            shutil.copyfileobj(incoming, outgoing)
        return json.dumps({"source": source, "destination": destination, "copied": True})

    def move_file(source: str, destination: str) -> str:
        """因为任务文件需要重命名或归档，需要移动单个文件并保留原始内容。"""
        # 1、只操作普通文件，目标存在时拒绝；不提供目录递归移动。
        src, dst = file_pair(root, source, destination)
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        return json.dumps({"source": source, "destination": destination, "moved": True})

    def delete_file(path: str) -> str:
        """因为临时产物需要清理，需要删除指定单文件或空目录并返回真实结果。"""
        # 1、禁止删除整个会话根和递归目录；缺失文件返回 deleted=false，便于明确判断结果。
        target = resolve_task_path(root, path)
        if target == root.resolve():
            raise ValueError("不能删除会话根目录")
        if not target.exists():
            return json.dumps({"path": path, "deleted": False})
        if target.is_dir():
            target.rmdir()
        else:
            target.unlink()
        return json.dumps({"path": path, "deleted": True})

    # 2、每次装配创建独立闭包，主子 Agent 使用同一工具合同，不共享可变任务状态。
    return [
        StructuredTool.from_function(function, metadata={"roomcrew_tool_kind": "tool"})
        for function in (file_info, make_directory, copy_file, move_file, delete_file)
    ]


def file_pair(root: Path, source: str, destination: str) -> tuple[Path, Path]:
    """因为复制和移动需要一致的语义，需要统一校验源文件存在、目标为空且两者不同。"""
    # 1、所有格式均按普通文件处理，不把虚拟 Skills 挂载当作可修改任务目录。
    src, dst = resolve_task_path(root, source), resolve_task_path(root, destination)
    if not src.is_file():
        raise ValueError("源路径不是已存在的任务文件")
    if src == dst or dst.exists():
        raise ValueError("目标路径已经存在，请选择新路径")
    return src, dst
