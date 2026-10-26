"""首版本地工具与文件后端的唯一组装位置。"""

from pathlib import Path

from deepagents.backends import FilesystemBackend
from langchain_core.tools import BaseTool

from roomcrew.security.capabilities import CapabilityPolicy
from roomcrew.tools.clock import get_local_time
from roomcrew.tools.human import ask_user


def local_tools(policy: CapabilityPolicy) -> list[BaseTool]:
    """因为工具开放范围不应写死在 Loop 中，需要独立注册真实可用工具并校验版本能力。"""
    # 1、注册时间与真实人工询问；文件工具、task 和规划工具由 SDK 根据后端注入。
    policy.validate_release()
    return [get_local_time, ask_user]


def file_backend(root: Path) -> FilesystemBackend:
    """因为所有文件能力必须使用相同的会话根，需要统一建立不提供 execute 的文件后端。"""
    # 1、固定虚拟路径语义和文件检索大小，不允许配置回退为任意宿主路径。
    return FilesystemBackend(root, virtual_mode=True, max_file_size_mb=1)
