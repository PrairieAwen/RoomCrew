"""MCP 独立能力入口；仅由可信配置接入 HTTP 工具。"""

import asyncio
from typing import Any

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from roomcrew.contracts.errors import ExecutionError


async def configured_mcp_tools(servers: list[dict[str, Any]]) -> list[BaseTool]:
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
    # 2、发现与执行均有期限；工具来源取自可信注册，不按模型文字推测。
    try:
        async with asyncio.timeout(20):
            client = MultiServerMCPClient(connections, tool_name_prefix=True)
            tools = await client.get_tools()
        if len(tools) > 64:
            raise ValueError("MCP 工具数量超过限制")
        for tool in tools:
            tool.metadata = {"roomcrew_tool_kind": "mcp"}
        return tools
    except asyncio.CancelledError:
        raise
    except Exception:
        raise ExecutionError("MCP_CONNECTION") from None
