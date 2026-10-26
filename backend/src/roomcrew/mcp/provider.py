"""MCP 独立能力入口；当前发行版不创建任何连接或子进程。"""

from dataclasses import dataclass

from langchain_core.tools import BaseTool

from roomcrew.contracts.errors import ExecutionError


@dataclass(frozen=True)
class McpPolicy:
    enabled: bool = False


def mcp_tools(policy: McpPolicy) -> list[BaseTool]:
    """因为 MCP 的连接生命周期需要独立接入，需要明确关闭行为并拒绝尚未验收的启用请求。"""
    # 1、关闭时不导入客户端、不访问网络、不启动服务；启用不能返回假工具或静默忽略。
    if policy.enabled:
        raise ExecutionError("CAPABILITY_UNAVAILABLE")
    return []
