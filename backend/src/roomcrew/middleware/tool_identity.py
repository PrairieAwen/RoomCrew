"""通过公开中间件把模型工具 ID 关联到官方工具执行事件。"""

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import Command


class ToolIdentityMiddleware(AgentMiddleware[Any, Any, Any]):
    def _request(self, request: ToolCallRequest) -> ToolCallRequest:
        """因为 SDK 调用 ID 与模型工具 ID 不同，需要把真实模型调用身份写入本次工具副本的元数据。"""
        # 1、复制工具而不修改共享实例；模型参数和原始凭据不进入元数据。
        if request.tool is None:
            return request
        metadata = {
            **(request.tool.metadata or {}),
            "roomcrew_tool_call_id": request.tool_call.get("id"),
        }
        return request.override(tool=request.tool.model_copy(update={"metadata": metadata}))

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        """因为同步执行也需要完整关联，需要在官方调用前注入工具身份并保持原返回与异常。"""
        # 1、不重试、不代替授权、不改变工具参数。
        return handler(self._request(request))

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        """因为主子 Agent 通常异步调用工具，需要为每次实际执行保留模型调用与 SDK 身份的对应。"""
        # 1、原样等待执行；interrupt 和取消仍交给框架处理。
        return await handler(self._request(request))
