"""首版本地工具与文件后端的唯一组装位置。"""

from pathlib import Path

from deepagents.backends import CompositeBackend, FilesystemBackend
from deepagents.backends.protocol import BackendProtocol, EditResult, WriteResult
from langchain_core.tools import BaseTool

from roomcrew.security.capabilities import CapabilityPolicy
from roomcrew.tools.clock import get_local_time
from roomcrew.tools.human import ask_user


def local_tools(policy: CapabilityPolicy) -> list[BaseTool]:
    """因为工具开放范围不应写死在 Loop 中，需要独立注册真实可用工具并校验版本能力。"""
    # 1、复制已注册模板，避免某次装配修改元数据后污染其他 Agent / Run。
    policy.validate_release()
    return [
        item.model_copy(deep=True, update={"metadata": {"roomcrew_tool_kind": kind}})
        for item, kind in ((get_local_time, "tool"), (ask_user, "human"))
    ]


def file_backend(root: Path, skill_home: Path | None = None) -> BackendProtocol:
    """因为所有文件能力必须使用相同的会话根，需要统一建立不提供 execute 的文件后端。"""
    # 1、固定虚拟路径语义和文件检索大小，不允许配置回退为任意宿主路径。
    backend = FilesystemBackend(root, virtual_mode=True, max_file_size_mb=1)
    if skill_home is None:
        return backend
    return CompositeBackend(
        backend,
        routes={
            "/skills/configured/": ReadOnlySkills(skill_home, virtual_mode=True, max_file_size_mb=1)
        },
    )


class ReadOnlySkills(FilesystemBackend):
    def write(self, file_path: str, content: str) -> WriteResult:
        """因为用户保存的技能是运行快照，需要禁止 Agent 通过文件工具改写挂载包。"""
        # 1、保持 SDK 标准返回类型，不执行任何文件写入。
        return WriteResult(
            error="Skills are read-only. Write scripts under the task directory instead."
        )

    def edit(
        self, file_path: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> EditResult:
        """因为技能正文不能在执行中被悄悄替换，需要拒绝编辑只读技能挂载。"""
        # 1、修改技能只能走可信配置入口并生成新版本。
        return EditResult(error="Skills are read-only.")
