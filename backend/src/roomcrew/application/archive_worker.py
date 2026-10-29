"""后台会话封存、可恢复摘要和本地向量索引，不参与 Agent Loop 调度。"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from roomcrew.application.archive_snapshot import snapshot
from roomcrew.application.runtime import Runtime
from roomcrew.archive.embeddings import LocalEmbeddings
from roomcrew.archive.summary import PROMPT, parse_summary
from roomcrew.archive.text import fragments, summary_parts
from roomcrew.middleware.limits import ModelCallBudget
from roomcrew.models.factory import model_session
from roomcrew.storage.archives import ArchiveRepository


class ArchiveWorker:
    def __init__(
        self,
        repository: ArchiveRepository,
        embeddings: LocalEmbeddings,
        root: Path,
        runtime_for: Callable[[str], Awaitable[Runtime]],
        spaces: Callable[[], list[dict[str, Any]]],
        busy: Callable[[], bool],
    ) -> None:
        """因为静默归档应独立于用户定时任务，需要注入空间目录和资源门面并保持单作业执行。"""
        # 1、真实时钟与一小时阈值固定为生产默认，精确边界测试可只替换本实例的时钟。
        self.repository, self.embeddings, self.root = repository, embeddings, root
        self.runtime_for, self.spaces, self.busy = runtime_for, spaces, busy
        self.now: Callable[[], float] = time.time
        self.quiet_seconds = 3600.0
        self.task: asyncio.Task[None] | None = None
        self.failed_spaces: list[str] = []
        self.root.mkdir(parents=True, exist_ok=True)

    async def poll(self) -> None:
        """因为前台交互优先且轮询不能重入，需要只在空闲时筛选会话并唤起一个归档工作批次。"""
        # 1、上一批仍在网络或 CPU 处理时不新建第二个任务，也不消耗重复模型额度。
        if (self.task is not None and not self.task.done()) or self.busy():
            return
        self.failed_spaces = []
        for space in self.spaces():
            try:
                runtime = await self.runtime_for(space["id"])
                for source in runtime.store.memory.candidates(self.now(), self.quiet_seconds):
                    if runtime.store.memory.seal(source["id"], source["activity"]):
                        self.repository.begin(space["id"], source)
            except Exception:
                self.failed_spaces.append(space["id"])
        jobs = self.repository.jobs(self.now())
        if jobs:
            self.task = asyncio.create_task(self._process(jobs[0]))

    async def request(self, workspace_id: str, conversation_id: str) -> dict[str, Any]:
        """因为用户完成工作后可主动落库，需要提供不降低自动一小时阈值的显式归档入口。"""
        # 1、与自动归档共用受理检查；活动和待答复会话仍无法封存。
        runtime = await self.runtime_for(workspace_id)
        source = runtime.store.memory.source(conversation_id)
        if source["lifecycle"] == "archived":
            return self.repository.get(self.repository.identifier(workspace_id, conversation_id))
        if not runtime.store.memory.seal(conversation_id, source["activity"]):
            raise ValueError("会话刚有新写入，请稍后重试归档")
        result = self.repository.begin(workspace_id, source)
        await self.poll()
        return result

    async def _process(self, record: dict[str, Any]) -> None:
        """因为文件、模型和向量各阶段都可能中断，需要保留已提交结果并在稳定错误下有界重试。"""
        # 1、快照完整落地后才推进会话为已归档；新对话不等待摘要网络请求完成。
        identifier, stage = record["id"], record["state"]
        try:
            runtime = await self.runtime_for(record["workspace_id"])
            if stage != "snapshot":
                runtime.store.memory.archived(record["conversation_id"])
            if stage == "snapshot":
                messages, manifest = await asyncio.to_thread(
                    snapshot, runtime.paths.data / "sessions.sqlite", self.root / identifier, record
                )
                documents = [
                    {
                        "kind": "message",
                        "text": text,
                        "first_position": message["position"],
                        "last_position": message["position"],
                        "member_id": message["member_id"],
                        "agent_id": message["agent_id"],
                        "at": message["at"],
                    }
                    for message in messages
                    for text in fragments(message["text"])
                ]
                try:
                    window = runtime.config.require_profile().context_window
                except ValueError:
                    window = 4096
                self.repository.snapshot(
                    identifier,
                    messages,
                    summary_parts(messages, min(10000, max(600, int(window * 0.45)))),
                    documents,
                    manifest,
                )
                runtime.store.memory.archived(record["conversation_id"])
                stage = "indexing_raw"
            if stage in {"indexing_raw", "indexing"}:
                if self.embeddings.available:
                    pending = self.repository.pending_vectors(
                        identifier, model=self.embeddings.identity
                    )
                    if pending:
                        vectors = await self.embeddings.embed([item["text"] for item in pending])
                        self.repository.save_vectors(
                            [
                                (vector, self.embeddings.identity, item["id"])
                                for vector, item in zip(vectors, pending, strict=True)
                            ]
                        )
                    if self.repository.pending_vectors(identifier, 1, self.embeddings.identity):
                        return
                if stage == "indexing_raw":
                    self.repository.state(identifier, "summarizing")
                    return
                self.repository.state(
                    identifier, "ready" if self.embeddings.available else "ready_text"
                )
                return
            # 2、每批最多两次摘要调用，每段成功即提交；新前台任务到来后不再开启下一段。
            if stage == "summarizing":
                async with model_session(
                    runtime.config.require_profile(), ModelCallBudget(2)
                ) as model:
                    for _ in range(2):
                        part = self.repository.next_part(identifier)
                        if part is None:
                            self.repository.finish_summary(identifier)
                            stage = "indexing"
                            break
                        if self.busy():
                            return
                        if not self.repository.consume_model_call(time.time()):
                            return
                        async with asyncio.timeout(90):
                            reply = await model.ainvoke(
                                PROMPT + "\n\n" + part["text"], max_tokens=1800
                            )
                        result = parse_summary(reply.content, part["positions"])
                        self.repository.save_part(identifier, part["position"], result)
        except asyncio.CancelledError:
            raise
        except Exception:
            self.repository.state(identifier, stage, "ARCHIVE_STAGE_FAILED", self.now() + 600)

    async def close(self) -> None:
        """因为退出不能留下归档网络请求或正在使用的向量资源，需要取消并等待自己的工作协程。"""
        # 1、成功分片已经持久化，取消不会删除原始历史或重新执行用户工具。
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None
