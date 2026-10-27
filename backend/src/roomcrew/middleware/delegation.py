"""本轮配置名单和成员并发租约，不改变 Deep Agents 调度循环。"""

import threading
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from roomcrew.contracts.agents import AgentSpec


class ConfiguredDelegationMiddleware(AgentMiddleware[Any, Any, Any]):
    def __init__(self, workers: Sequence[AgentSpec]) -> None:
        """因为配置人数应限制实际唤起人数，需要固定本 Run 名单并为每个成员维护单一执行租约。"""
        # 1、名单来自当前空间快照，既不读取其他空间，也不按共享定义合并不同人物。
        self._members = {spec.tool_name: spec.actor.member_id for spec in workers}
        self._busy: set[str] = set()
        self._lock = threading.Lock()

    def _claim(self, request: ToolCallRequest) -> tuple[str | None, ToolMessage | None]:
        """因为模型可能猜测目标或重复并发派工，需要在进入真正 task 工具前做确定性校验。"""
        # 1、普通工具原样通过；非法目标与忙碌成员返回普通工具错误供模型调整计划。
        if request.tool_call["name"] != "task":
            return None, None
        target = request.tool_call.get("args", {}).get("subagent_type")
        member = self._members.get(target) if isinstance(target, str) else None
        reason = "只能委派本工作空间已配置且启用的 Agent，请使用 list_agents 查询。"
        with self._lock:
            if member is not None and member not in self._busy:
                self._busy.add(member)
                return member, None
            if member is not None:
                reason = "该 Agent 已在执行子任务，请顺序安排，不能并发克隆同一成员。"
        return None, ToolMessage(
            content=reason, tool_call_id=request.tool_call["id"], name="task", status="error"
        )

    def _release(self, member: str | None) -> None:
        """因为异常、中断和取消也必须释放成员，需要在工具退出时统一回收本次租约。"""
        # 1、只释放已成功获取的成员，不改变任务结果或人工请求状态。
        if member is not None:
            with self._lock:
                self._busy.discard(member)

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        """因为同步工具入口也可能被使用，需要与异步入口执行相同名单和并发约束。"""
        # 1、校验成功后只调用一次原工具，失败或退出都不盲目重试。
        member, error = self._claim(request)
        if error is not None:
            return error
        try:
            return handler(request)
        finally:
            self._release(member)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        """因为主循环会并行执行工具，需要用短租约阻止同一配置成员同时产生多个活跃实例。"""
        # 1、锁不跨 await；成员租约覆盖真实执行，最终释放包含取消与人工中断路径。
        member, error = self._claim(request)
        if error is not None:
            return error
        try:
            return await handler(request)
        finally:
            self._release(member)
