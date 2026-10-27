"""当前可开放的真实能力，不能由模型或 Skill 指令修改。"""

import os
from dataclasses import dataclass

from roomcrew.contracts.errors import ExecutionError


@dataclass(frozen=True)
class CapabilityPolicy:
    code_execution: bool = True
    mcp: bool = True

    def validate_release(self) -> None:
        """因为脚本执行依赖 Windows 隔离，需要拒绝其他平台的宿主执行回退。"""
        # 1、关闭 Python 后仍可运行普通文件与模型任务。
        if self.code_execution and os.name != "nt":
            raise ExecutionError("CAPABILITY_UNAVAILABLE")
