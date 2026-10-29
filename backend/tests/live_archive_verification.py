"""显式启用的真实模型档案验收；新建合成数据空间，不复制或输出用户密钥。"""

import argparse
import asyncio
import json
import msvcrt
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from roomcrew.application.archive_access import ArchiveAccess
from roomcrew.application.archive_worker import ArchiveWorker
from roomcrew.application.options import RunOptions
from roomcrew.application.runtime import Runtime
from roomcrew.archive.embeddings import LocalEmbeddings
from roomcrew.contracts.limits import RunLimits
from roomcrew.platform.paths import AppPaths
from roomcrew.storage.archives import ArchiveRepository
from roomcrew.storage.workspaces import WorkspaceRepository


async def finish(runtime: Runtime, conversation_id: str) -> list[dict[str, Any]]:
    """因为提交只代表受理，需要等待真实 Loop 并检查完成状态，不接受模型口头成功替代执行。"""
    # 1、每轮有固定预算；失败不无限重发，也不更改数据库来制造成功结果。
    async with asyncio.timeout(170):
        while runtime.active:
            await asyncio.sleep(0.2)
    if runtime.store.latest_status(conversation_id) != "completed":
        raise AssertionError("LIVE_ARCHIVE_RUN_FAILED")
    return await runtime.events(conversation_id)


class VerificationSpace:
    def __init__(self, identifier: str, runtime: Runtime) -> None:
        """因为真实验证不应批量压缩其他用户历史，需要只向正式归档器提供本次独立空间。"""
        # 1、这是测试组合根，仍使用正式 Runtime、归档器和服务，不模拟任何执行行为。
        self.identifier, self.runtime = identifier, runtime

    async def runtime_for(self, identifier: str) -> Runtime:
        """因为归档必须精确绑定来源空间，需要拒绝本次验证以外的路由请求。"""
        # 1、不自动打开其他会议室或读取其他用户会话。
        if identifier != self.identifier:
            raise ValueError("验证仅允许本次测试空间")
        return self.runtime

    def spaces(self) -> list[dict[str, Any]]:
        """因为后台检查器应只处理验收数据，需要返回本次明确创建的空间。"""
        # 1、不降低生产一小时阈值，真实验收通过用户同款立即归档服务执行。
        return [{"id": self.identifier, "name": "档案验收（合成数据）"}]

    def busy(self) -> bool:
        """因为前台执行应优先，需要读取真实活动任务而不是伪造空闲。"""
        # 1、模型未完成时正式归档器会暂缓处理。
        return bool(self.runtime.active)


async def verify(root: Path, evidence: Path) -> None:
    """因为验证要使用用户真实配置又不改原历史，需要独占原数据根并创建明确标记的测试空间。"""
    # 1、密钥只由可信工厂在原保护目录加载，不读取回显、不复制到测试目录。
    if not (root / "private/model-config.dpapi").is_file():
        raise ValueError("请先在应用中配置真实模型")
    paths = AppPaths.create(root)
    lock = (paths.private / "instance.lock").open("a+b")
    lock.seek(0)
    lock.write(b"0")
    lock.flush()
    lock.seek(0)
    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    repository: ArchiveRepository | None = None
    spaces: WorkspaceRepository | None = None
    runtime: Runtime | None = None
    worker: ArchiveWorker | None = None
    embeddings = LocalEmbeddings(paths.resources)
    report: dict[str, Any] = {
        "test_data": "explicit_synthetic_workspace",
        "clock": "real_system_clock",
    }
    try:
        spaces = WorkspaceRepository(paths.data / "workspaces.sqlite")
        space = spaces.create("档案验收（合成数据）")
        runtime = Runtime(
            paths.for_workspace(space["id"]),
            RunOptions(
                limits=RunLimits(
                    model_calls=10,
                    total_seconds=150,
                )
            ),
        )
        repository = ArchiveRepository(paths.data / "archives.sqlite")
        access = ArchiveAccess(space["id"], repository, embeddings, spaces.list)
        runtime.attach_archives(access)
        await runtime.start()
        target = VerificationSpace(space["id"], runtime)
        worker = ArchiveWorker(
            repository,
            embeddings,
            paths.data / "archive-blobs",
            target.runtime_for,
            target.spaces,
            target.busy,
        )
        # 2、用真实 Agent 接收一条明确合成的工作信息，再通过同款服务主动封存而非加速时钟。
        initial = await runtime.submit_chat(
            "assistant",
            "这是合成验收数据，不是我的真实偏好："
            "本次项目代号为蓝杉47，下一步是周五下午检查报告。请只简短确认收到，不联网、不写文件。",
            uuid4().hex,
        )
        await finish(runtime, initial["conversation"]["id"])
        record = await worker.request(space["id"], initial["conversation"]["id"])
        for _ in range(15):
            await worker.poll()
            if worker.task:
                await worker.task
            record = repository.get(record["id"])
            if record["error"]:
                raise AssertionError("LIVE_SUMMARY_STAGE_FAILED")
            if record["state"] == "ready":
                break
        else:
            raise AssertionError("LIVE_ARCHIVE_NOT_READY")
        assert "蓝杉47" in record["summary"]
        assert (await access.read(record["id"]))["messages"][0]["text"].startswith(
            "这是合成验收数据"
        )
        semantic = await access.search(
            "assistant", {"query": "之前给项目起的名字和接下来的安排", "mode": "vector"}
        )
        assert semantic["results"] and semantic["results"][0]["archive_id"] == record["id"]
        # 3、新对话真实调用档案搜索和原文工具，历史摘要只作为有日期的背景，不冒充工具结果。
        follow = await runtime.submit_chat(
            "assistant",
            "请实际使用 search_archive 查询我之前的合成验收项目，"
            "再调用 read_archive_messages 阅读原文，告诉我项目代号和下一步工作。"
            "不要联网或读任务文件。",
            uuid4().hex,
        )
        events = await finish(runtime, follow["conversation"]["id"])
        names = [item["payload"].get("name") for item in events if item["kind"] == "tool.completed"]
        assert "search_archive" in names and "read_archive_messages" in names
        assert follow["conversation"]["id"] != initial["conversation"]["id"]
        responses = "\n".join(
            item["payload"].get("text", "")
            for item in events
            if item["kind"] == "assistant.message"
        )
        assert "蓝杉47" in responses and "周五" in responses
        report.update(
            passed=True,
            workspace_id=space["id"],
            archive_id=record["id"],
            archived_conversation=initial["conversation"]["id"],
            continuation_conversation=follow["conversation"]["id"],
            archive_state=record["state"],
            archive_tools=names,
            finished_at=datetime.now().astimezone().isoformat(),
        )
    finally:
        # 4、只停止本次模型和作业，保留明确标记的验收空间供用户在界面复查，不改变原活动空间。
        if worker is not None:
            await worker.close()
        if runtime is not None:
            await runtime.close()
        embeddings.close()
        if repository is not None:
            repository.close()
        if spaces is not None:
            spaces.close()
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        lock.close()
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
        print(json.dumps(report, ensure_ascii=False), flush=True)


def main() -> None:
    """因为真实模型验收会花费额度，需要显式 opt-in 且不纳入普通 pytest 自动运行。"""
    # 1、未提供允许标志与数据根时不打开真实保护配置。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-live", action="store_true", required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(verify(args.data_dir.resolve(), args.evidence))


if __name__ == "__main__":
    main()
