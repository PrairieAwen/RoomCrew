"""Run 受理、组件组装与终态；不实现模型—工具循环。"""

import asyncio
from typing import Any

from roomcrew.agent_loop.engine import DeepAgentsLoop
from roomcrew.application.options import RunOptions
from roomcrew.config.schema import ModelProfile
from roomcrew.config.store import ConfigStore
from roomcrew.contracts.errors import ERROR_MESSAGES, ExecutionError
from roomcrew.mcp.provider import mcp_tools
from roomcrew.middleware.limits import ModelCallBudget
from roomcrew.middleware.stack import build_middleware
from roomcrew.models.factory import create_model
from roomcrew.platform.paths import AppPaths
from roomcrew.skills.registry import resolve_skill_sources
from roomcrew.storage.checkpoints import CheckpointStore
from roomcrew.storage.sessions import SessionStore
from roomcrew.tools.registry import file_backend, local_tools


class ExecutionService:
    def __init__(
        self,
        *,
        paths: AppPaths,
        config: ConfigStore,
        store: SessionStore,
        checkpoints: CheckpointStore,
        options: RunOptions,
    ) -> None:
        """因为运行控制需要统一协调状态和资源，需要注入职责明确的模块，而不把实现堆回门面。"""
        # 1、一次应用宿主持有一个调度服务，每轮仍创建独立模型、图、额度和事件适配器。
        self.paths, self.config, self.store = paths, config, store
        self.checkpoints, self.options = checkpoints, options
        self.active: dict[str, asyncio.Task[None]] = {}

    async def submit(self, conversation_id: str, text: str, request_id: str) -> dict[str, Any]:
        """因为重复点击或线程并发会重复执行工具，需要检查幂等和固定模型绑定后受理任务。"""
        # 1、请求幂等优先于新配置读取，历史请求重发只返回已有状态。
        text = text.strip()
        if not text or len(text) > 32000 or not 8 <= len(request_id) <= 100:
            raise ValueError("请输入 1～32000 字的任务，并使用有效请求标识")
        existing = self.store.run_by_request(request_id)
        if existing:
            if existing["conversation_id"] != conversation_id or existing["input"] != text:
                raise ValueError("请求标识已被其他任务使用")
            return {"run_id": existing["id"], "status": existing["status"]}
        if self.active:
            raise ValueError("首版同时执行一个会话，请先完成或停止当前任务")
        # 2、继续会话需要同一配置引用且上一轮成功，不能自动重放未知副作用。
        conversation = self.store.conversation(conversation_id)
        profile = self.config.require_profile()
        if conversation["profile_ref"] != profile.reference:
            raise ValueError("模型配置已更新，请新建会话后继续")
        if self.store.latest_status(conversation_id) in {"failed", "cancelled", "interrupted"}:
            raise ValueError("本会话上轮已中断或失败，请新建会话继续；历史仍可查看")
        run_id = self.store.begin(conversation_id, text, request_id)
        # 3、先持久化请求，再建立协程；界面通过独立查询读取进展。
        self.active[run_id] = asyncio.create_task(
            self._execute(conversation_id, run_id, text, profile)
        )
        return {"run_id": run_id, "status": "running"}

    async def _execute(
        self, conversation_id: str, run_id: str, text: str, profile: ModelProfile
    ) -> None:
        """因为任务结果必须来自真实框架，需要组装独立组件、消费产品事件并可靠记录终态。"""
        # 1、所有模块按同一份不可变策略装配；模型调用额度在请求发出前共享预占。
        model = None
        budget = ModelCallBudget(self.options.limits.model_calls)
        try:
            self.options.capabilities.validate_release()
            extra_tools = local_tools(self.options.capabilities) + mcp_tools(self.options.mcp)
            root = self.paths.session_files(conversation_id)
            sources = resolve_skill_sources(root, self.options.skills)
            model = create_model(profile, budget)
            backend = file_backend(root)
            loop = DeepAgentsLoop(
                model=model,
                backend=backend,
                tools=extra_tools,
                middleware=build_middleware(model, backend, self.options.compression),
                worker_middleware=build_middleware(model, backend, self.options.compression),
                skills=sources,
                checkpointer=self.checkpoints.saver,
                limits=self.options.limits,
                redact=model.redact,
            )
            # 2、应用层只消费普通轨迹合同，Loop 不直接操作产品数据库。
            async with asyncio.timeout(self.options.limits.total_seconds):
                async for event in loop.stream(conversation_id, text):
                    self.store.append(
                        conversation_id,
                        run_id,
                        event.kind,
                        event.actor,
                        event.scope,
                        **event.payload,
                    )
            self.store.finish(run_id, "completed", {"model_calls": budget.calls})
        # 3、取消、超时和稳定异常分别处理，不把原始 SDK 异常或配置写入轨迹。
        except asyncio.CancelledError:
            self.store.finish(
                run_id, "cancelled", {"message": "已停止继续执行。已完成的文件操作仍保留。"}
            )
        except TimeoutError:
            self._fail(run_id, "RUN_TIMEOUT")
        except Exception as error:
            code = error.code if isinstance(error, ExecutionError) else "RUN_ERROR"
            if type(error).__name__ == "GraphRecursionError":
                code = "RUN_LIMIT"
            self._fail(run_id, code)
        finally:
            # 4、连接和任务登记共同释放，后续任务不会复用仍在关闭的本轮资源。
            try:
                if model is not None:
                    await model.close()
            finally:
                self.active.pop(run_id, None)

    def _fail(self, run_id: str, code: str) -> None:
        """因为运行失败的公开语义必须一致，需要用稳定错误码更新状态和对应终态事件。"""
        # 1、产品存储在一个事务中写终态，不保存底层堆栈。
        self.store.finish(run_id, "failed", {"code": code, "message": ERROR_MESSAGES[code]})

    async def stop(self, run_id: str) -> dict[str, Any]:
        """因为用户需要停止指定 Run，需要取消并等待执行确认，而不是只改变界面状态。"""
        # 1、本地取消不承诺撤销服务商已接收的请求或已完成文件操作。
        task = self.active.get(run_id)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        return {"stopped": True}

    async def close(self) -> None:
        """因为关闭应用前必须停止运行，需要先等所有执行协程记录终态并释放模型连接。"""
        # 1、不在此处关闭数据库，数据库由应用生命周期层在任务结束后关闭。
        tasks = list(self.active.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
