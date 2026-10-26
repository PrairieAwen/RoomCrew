"""唯一生产 Loop 适配；工具、策略和持久化由外层注入。"""

from collections.abc import AsyncIterator, Callable, Sequence
from typing import Any

from deepagents import create_deep_agent
from deepagents.backends.protocol import BackendProtocol
from deepagents.middleware.subagents import SubAgent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.exceptions import ContextOverflowError
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command

from roomcrew.agent_loop.event_adapter import EventAdapter
from roomcrew.agent_loop.prompts import SYSTEM_PROMPT
from roomcrew.contracts.agents import ActorRef, AgentSpec
from roomcrew.contracts.errors import ExecutionError
from roomcrew.contracts.limits import RunLimits
from roomcrew.tracing.events import TraceEvent


class DeepAgentsLoop:
    def __init__(
        self,
        *,
        model: BaseChatModel,
        backend: BackendProtocol,
        tools: Sequence[BaseTool],
        middleware: Sequence[AgentMiddleware[Any, Any, Any]],
        worker_middleware: Sequence[AgentMiddleware[Any, Any, Any]],
        skills: list[str],
        checkpointer: BaseCheckpointSaver[Any] | None,
        limits: RunLimits,
        redact: Callable[[Any], Any],
        main: AgentSpec | None = None,
        workers: Sequence[AgentSpec] | None = None,
    ) -> None:
        """因为图框架不能承担配置和产品存储职责，需要通过公开参数注入本轮已组装好的组件。"""
        # 1、主子 Agent 使用同一类底座；显式声明 worker，避免自定义策略只作用于主 Agent。
        main = main or AgentSpec(ActorRef(), "main", "通用助手", "")
        workers = (
            list(workers)
            if workers is not None
            else [AgentSpec(main.actor, "general-purpose", "执行通用子任务", "")]
        )
        subagents: list[SubAgent] = [
            {
                "name": spec.tool_name,
                "description": spec.description,
                "system_prompt": SYSTEM_PROMPT + "\n人员配置：" + spec.prompt,
                "model": model,
                "tools": list(tools),
                "middleware": list(worker_middleware),
                "skills": skills,
            }
            for spec in workers
        ]
        self._graph = create_deep_agent(
            model=model,
            tools=tools,
            backend=backend,
            middleware=middleware,
            skills=skills or None,
            system_prompt=SYSTEM_PROMPT + "\n人员配置：" + main.prompt,
            subagents=subagents,
            checkpointer=checkpointer,
            name="roomcrew-assistant",
        )
        # 2、每个图有独立事件适配器；Loop 不知道配置文件、Key 或 SQLite 产品表。
        self._events = EventAdapter(
            redact, main.actor, {item.tool_name: item.actor for item in workers}
        )
        self._limits = limits
        self._member_id = main.actor.member_id

    async def stream(
        self, conversation_id: str, text: str, resume: dict[str, str] | None = None
    ) -> AsyncIterator[TraceEvent]:
        """因为产品只需要统一轨迹，需要运行真实 SDK Loop 并把公开事件转换成稳定产品合同。"""
        # 1、同一会话中不同人物的主线程隔离；默认助手保留原有 checkpoint 标识兼容历史。
        thread_id = (
            conversation_id
            if self._member_id == "assistant"
            else conversation_id + "::" + self._member_id
        )
        config: RunnableConfig = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": self._limits.graph_steps,
        }
        # 2、保留 SDK 的模型—工具调度，不在这里实现第二套执行循环。
        try:
            async for event in self._graph.astream_events(
                Command(resume=resume)
                if resume is not None
                else {"messages": [HumanMessage(text)]},
                config=config,
                version="v2",
            ):
                for projected in self._events.project(dict(event)):
                    yield projected
            snapshot = await self._graph.aget_state(config)
            for pending in snapshot.interrupts:
                if isinstance(pending.value, dict) and pending.value.get("kind") == "question":
                    yield self._events.human_request(pending.id, pending.value)
        except ContextOverflowError:
            # 3、SDK 有界压缩后仍无法满足窗口时，转换为不含框架私有细节的产品错误。
            raise ExecutionError("CONTEXT_LIMIT") from None
