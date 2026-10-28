"""MCP 独立能力入口；仅由可信配置接入 HTTP 工具。"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.interceptors import MCPToolCallRequest, MCPToolCallResult
from mcp.types import CallToolResult

from roomcrew.contracts.errors import ExecutionError


class MCPResponseFilter:
    def __init__(self, redact: Callable[[Any], Any]) -> None:
        """因为外部服务可能回显认证内容，需要在结果进入模型和 checkpoint 之前脱敏。"""
        # 1、脱敏函数由可信装配点提供，不让 MCP 适配器读取凭据文件。
        self._redact = redact

    async def __call__(
        self,
        request: MCPToolCallRequest,
        handler: Callable[[MCPToolCallRequest], Awaitable[MCPToolCallResult]],
    ) -> MCPToolCallResult:
        """因为网络异常可能携带 Header，需要限制单次调用并只抛出稳定错误码，禁止自动重试。"""
        # 1、官方客户端创建和关闭会话；服务错误内容也在转换为 ToolMessage 前过滤。
        try:
            async with asyncio.timeout(60):
                result = await handler(request)
            if not isinstance(result, CallToolResult):
                raise ValueError("未知 MCP 结果")
            return CallToolResult.model_validate(self._redact(result.model_dump()))
        except asyncio.CancelledError:
            raise
        except Exception:
            raise ExecutionError("MCP_TOOL") from None


async def configured_mcp_tools(
    servers: list[dict[str, Any]],
    keys: dict[str, str] | None = None,
    redact: Callable[[Any], Any] | None = None,
) -> list[BaseTool]:
    """因为 Agent 能力定义需要真实 MCP 工具，需要通过官方 HTTP 适配器发现并绑定受限调用。"""
    # 1、没有配置就不连接；每次调用由官方适配器管理短生命周期会话。
    connections: dict[str, Any] = {
        server["name"]: {
            "transport": "streamable_http",
            "url": server["url"],
            "timeout": 15,
            "sse_read_timeout": 45,
        }
        for server in servers
        if server["enabled"]
    }
    if not connections:
        return []
    for name, key in (keys or {}).items():
        if name in connections and key:
            connections[name]["headers"] = {"Authorization": f"Bearer {key}"}
    # 2、发现与执行均有期限；工具来源取自可信注册，不按模型文字推测。
    try:
        async with asyncio.timeout(20):
            client = MultiServerMCPClient(
                connections,
                tool_name_prefix=True,
                tool_interceptors=[MCPResponseFilter(redact)] if redact else [],
            )
            tools = await client.get_tools()
        if len(tools) > 64:
            raise ValueError("MCP 工具数量超过限制")
        for tool in tools:
            schema = tool.args_schema
            public = {"name": tool.name, "description": tool.description, "schema": schema}
            if redact and redact(public) != public:
                raise ValueError("MCP 工具目录包含认证回显")
            tool.metadata = {"roomcrew_tool_kind": "mcp"}
        return tools
    except asyncio.CancelledError:
        raise
    except Exception:
        raise ExecutionError("MCP_CONNECTION") from None
