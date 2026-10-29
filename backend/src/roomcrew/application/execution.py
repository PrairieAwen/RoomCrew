"""Run 受理、组件组装与终态；不实现模型—工具循环。"""

import asyncio
import time
from typing import Any

from roomcrew.accounts.service import AccountService
from roomcrew.application.components import AgentLoopFactory
from roomcrew.application.options import RunOptions
from roomcrew.config.schema import ModelProfile
from roomcrew.config.store import ConfigStore
from roomcrew.contracts.agents import AgentSpec
from roomcrew.contracts.archives import ArchiveQueries
from roomcrew.contracts.errors import ERROR_MESSAGES, ExecutionError
from roomcrew.contracts.schedules import ScheduleCommands
from roomcrew.middleware.limits import ModelCallBudget
from roomcrew.models.factory import create_model
from roomcrew.platform.paths import AppPaths
from roomcrew.storage.checkpoints import CheckpointStore
from roomcrew.storage.run_state import RunStateStore
from roomcrew.storage.sessions import SessionStore


class ExecutionService:
    def __init__(
        self,
        *,
        paths: AppPaths,
        config: ConfigStore,
        store: SessionStore,
        checkpoints: CheckpointStore,
        options: RunOptions,
        accounts: AccountService,
    ) -> None:
        """因为运行控制需要统一协调状态和资源，需要注入职责明确的模块，而不把实现堆回门面。"""
        # 1、一次应用宿主持有一个调度服务，每轮仍创建独立模型、图、额度和事件适配器。
        self.paths, self.config, self.store = paths, config, store
        self.checkpoints, self.options = checkpoints, options
        self.accounts = accounts
        self.state = RunStateStore(store)
        self.active: dict[str, asyncio.Task[None]] = {}
        self.schedules: ScheduleCommands | None = None
        self.archives: ArchiveQueries | None = None

    def capacity(self, conversation_id: str) -> None:
        """因为同一 Agent 可处理独立并行任务，需要仅阻止同线程重入并限制每空间活动数。"""
        # 1、不同会话各有模型、文件和 checkpoint，四个活动 Run 是当前空间的上限。
        if len(self.active) >= 4:
            raise ValueError("当前工作空间最多同时执行四个会话")
        if self.store.connection.execute(
            "SELECT 1 FROM runs WHERE conversation_id=? AND status='running' LIMIT 1",
            (conversation_id,),
        ).fetchone():
            raise ValueError("此会话仍在执行，请等待完成或新建独立会话")

    async def submit(
        self,
        conversation_id: str,
        text: str,
        request_id: str,
        member_id: str = "assistant",
        *,
        source: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """因为重复点击或线程并发会重复执行工具，需要检查幂等和固定模型绑定后受理任务。"""
        # 1、请求幂等优先于新配置读取，历史请求重发只返回已有状态。
        text = text.strip()
        if not text or len(text) > 32000 or not 8 <= len(request_id) <= 100:
            raise ValueError("请输入 1～32000 字的任务，并使用有效请求标识")
        existing = self.store.run_by_request(request_id)
        if existing:
            if existing["conversation_id"] != conversation_id or existing["input"] != text:
                raise ValueError("请求标识已被其他任务使用")
            if (
                self.state.context(existing["id"])["binding"]["main"]["actor"]["member_id"]
                != member_id
            ):
                raise ValueError("请求标识已用于其他接单成员")
            return {"run_id": existing["id"], "status": existing["status"]}
        self.capacity(conversation_id)
        # 2、继续会话需要同一配置引用且上一轮成功，不能自动重放未知副作用。
        conversation = self.store.conversation(conversation_id)
        profile = self.config.require_profile()
        if conversation["profile_ref"] != profile.reference:
            raise ValueError("模型配置已更新，请新建会话后继续")
        if self.store.latest_status(conversation_id) == "waiting_user":
            raise ValueError("请先回答或取消本会话的待处理问题")
        if self.store.latest_status(conversation_id) in {"failed", "cancelled", "interrupted"}:
            raise ValueError("本会话上轮已中断或失败，请新建会话继续；历史仍可查看")
        binding = self.accounts.binding(member_id)
        binding["source"] = source or {"kind": "user"}
        if (
            self.archives is not None
            and self.store.latest_status(conversation_id) is None
            and self.store.memory.get(conversation_id)["inherit_memory"]
            and binding["source"]["kind"] != "schedule"
        ):
            binding["archive_context"] = await self.archives.recent(member_id)
        elif self.archives is not None and binding["source"]["kind"] != "schedule":
            binding["archive_context"] = self.state.initial_archive_context(
                conversation_id, member_id
            )
        main = AgentSpec.restore(binding["main"])
        run_id = self.store.begin(
            conversation_id,
            text,
            request_id,
            main.actor.name,
            main.actor.agent_id,
            main.actor.member_id,
            binding=binding,
        )
        # 3、先持久化请求，再建立协程；界面通过独立查询读取进展。
        self.active[run_id] = asyncio.create_task(
            self._execute(conversation_id, run_id, text, profile)
        )
        return {"run_id": run_id, "status": "running"}

    async def _execute(
        self,
        conversation_id: str,
        run_id: str,
        text: str,
        profile: ModelProfile,
        resume: dict[str, str] | None = None,
    ) -> None:
        """因为任务结果必须来自真实框架，需要组装独立组件、消费产品事件并可靠记录终态。"""
        # 1、所有模块按同一份不可变策略装配；模型调用额度在请求发出前共享预占。
        model = None
        saved = self.state.context(run_id)
        budget = ModelCallBudget(self.options.limits.model_calls, saved["model_calls"])
        started = time.monotonic()
        waiting = False
        try:
            factory = AgentLoopFactory(
                self.paths, conversation_id, self.options, self.schedules, self.archives
            )
            model = create_model(profile, budget)
            loop = await factory.build(saved["binding"], model, self.checkpoints)
            # 2、应用层只消费普通轨迹合同，Loop 不直接操作产品数据库。
            remaining = (
                self.options.limits.total_seconds - saved["spent"] - (time.monotonic() - started)
            )
            if remaining <= 0:
                raise TimeoutError
            async with asyncio.timeout(remaining):
                async for event in loop.stream(conversation_id, text, resume):
                    if event.kind == "human.requested":
                        waiting = True
                        if not self.state.request(
                            conversation_id,
                            run_id,
                            event.actor,
                            event.scope,
                            event.agent_id or "agent_assistant",
                            event.member_id or "assistant",
                            event.payload,
                        ):
                            continue
                    self.store.append(
                        conversation_id,
                        run_id,
                        event.kind,
                        event.actor,
                        event.scope,
                        agent_id=event.agent_id,
                        member_id=event.member_id,
                        **event.payload,
                    )
            if waiting:
                self.state.wait(run_id)
                main_actor = AgentSpec.restore(saved["binding"]["main"]).actor
                self.store.append(
                    conversation_id,
                    run_id,
                    "run.waiting_user",
                    main_actor.name,
                    agent_id=main_actor.agent_id,
                    member_id=main_actor.member_id,
                )
            else:
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
                self.state.usage(run_id, budget.calls, time.monotonic() - started)
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
        else:
            self.state.cancel(run_id)
            self.store.finish(run_id, "cancelled", {"message": "已取消等待，旧问题不能继续执行。"})
        return {"stopped": True}

    async def respond(self, request_id: str, answer: str, command_id: str) -> dict[str, Any]:
        """因为人工回答必须恢复原线程，需要验证问题状态、配置引用与幂等后提交真实 Command。"""
        # 1、重复提交只返回既有受理结果，不再次进入框架。
        answer = answer.strip()
        if not answer or len(answer) > 4000 or not 8 <= len(command_id) <= 100:
            raise ValueError("请填写有效回答与命令标识")
        duplicate = self.state.duplicate(command_id, request_id, answer)
        if duplicate:
            return {"run_id": duplicate["run_id"], "accepted": True}
        profile = self.config.require_profile()
        candidate = self.store.connection.execute(
            "SELECT h.conversation_id FROM human_requests h WHERE h.id=?", (request_id,)
        ).fetchone()
        if (
            candidate is None
            or self.store.conversation(candidate[0])["profile_ref"] != profile.reference
        ):
            raise ValueError("问题不存在或原模型绑定已经变化")
        self.capacity(candidate["conversation_id"])
        # 2、领取回答后恢复同一 Run，不创建新用户消息或重新执行整段任务。
        question = self.state.answer(request_id, answer, command_id)
        run_id, conversation_id = question["run_id"], question["conversation_id"]
        self.store.append(
            conversation_id,
            run_id,
            "human.responded",
            question["actor"],
            question["scope"],
            agent_id=question["agent_id"],
            member_id=question["member_id"],
            request_id=request_id,
            answer=answer,
        )
        main = AgentSpec.restore(self.state.context(run_id)["binding"]["main"]).actor
        self.store.append(
            conversation_id,
            run_id,
            "run.resumed",
            main.name,
            agent_id=main.agent_id,
            member_id=main.member_id,
        )
        self.active[run_id] = asyncio.create_task(
            self._execute(conversation_id, run_id, "", profile, {request_id: answer})
        )
        return {"run_id": run_id, "accepted": True}

    async def close(self) -> None:
        """因为关闭应用前必须停止运行，需要先等所有执行协程记录终态并释放模型连接。"""
        # 1、不在此处关闭数据库，数据库由应用生命周期层在任务结束后关闭。
        tasks = list(self.active.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
