"""当前可开放的真实能力，不能由模型或 Skill 指令修改。"""

from dataclasses import dataclass

from roomcrew.contracts.errors import ExecutionError


@dataclass(frozen=True)
class CapabilityPolicy:
    code_execution: bool = False
    mcp: bool = False

    def validate_release(self) -> None:
        """因为首版尚未验收代码执行和 MCP，需要在构图前拒绝误开启而不是降级为宿主执行。"""
        # 1、能力配置来自可信程序，仍不能让尚未实现的执行路径伪装成可用。
        if self.code_execution or self.mcp:
            raise ExecutionError("CAPABILITY_UNAVAILABLE")
