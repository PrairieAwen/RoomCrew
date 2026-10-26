"""产物与技能使用同一套任务路径约束，不代表 OS 沙箱。"""

from pathlib import Path, PurePosixPath


def resolve_task_path(root: Path, virtual_path: str) -> Path:
    """因为界面或技能来源可能给出越界路径，需要校验虚拟路径并验证实际解析结果。"""
    # 1、禁止盘符、反斜杠和父目录；统一采用 / 开头的任务路径。
    if not virtual_path.startswith("/") or "\\" in virtual_path or ":" in virtual_path:
        raise ValueError("需要使用会话内的虚拟路径")
    if ".." in PurePosixPath(virtual_path).parts:
        raise ValueError("路径不能离开会话目录")
    # 2、解析链接后的真实目标仍须位于根目录下，不只比较字符串前缀。
    path = (root / virtual_path.lstrip("/")).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("路径不能离开会话目录")
    return path
