"""档案静默封存、完整历史、语义检索、权限与无感并行对话验证。"""

import asyncio
import gzip
import hashlib
import json
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from test_runtime import TEST_KEY, TEST_MODEL, model_server, tool_message, wait_finished

from roomcrew.application.archive_access import ArchiveAccess
from roomcrew.application.archive_snapshot import snapshot
from roomcrew.application.workspaces import WorkspaceHub
from roomcrew.archive.embeddings import LocalEmbeddings
from roomcrew.archive.summary import parse_summary
from roomcrew.archive.text import fragments, summary_parts
from roomcrew.platform.paths import AppPaths
from roomcrew.storage.archives import ArchiveRepository

SUMMARY = json.dumps(
    {
        "summary": "用户养了一只金毛犬，并约定周五交付报告。",
        "notes": [{"text": "用户的宠物是金毛犬。", "positions": [0]}],
    },
    ensure_ascii=False,
)


class Clock:
    def __init__(self, value: float) -> None:
        """因为静默边界测试不应真实等待一小时，需要注入仅属于本测试协调器的时钟。"""
        # 1、不改变系统、模型、时间工具或真实生产默认阈值。
        self.value = value

    def __call__(self) -> float:
        """因为后台归档接收时间戳，需要提供确定的测试时刻。"""
        # 1、该入口只用于精确测试封存条件。
        return self.value


async def archive_hub(root: Path, endpoint: str | None = None) -> WorkspaceHub:
    """因为各项验证不能干扰真实档案，需要使用独立目录、正式宿主和可控检查入口。"""
    # 1、暂停测试自己的滴答避免竞争；模型、工具、数据库和后台作业均为正式实现。
    hub = WorkspaceHub(AppPaths.create(root))
    await hub.start()
    await hub._schedule_timer.close()
    await hub._archive_timer.close()
    hub._embeddings.path = root / "missing-test-embedding-model"
    if endpoint:
        await hub.current.save_configuration(
            {
                "base_url": endpoint,
                "model": TEST_MODEL,
                "api_key": TEST_KEY,
            }
        )
    return hub


async def finish_archive(hub: WorkspaceHub, identifier: str) -> dict[str, Any]:
    """因为归档分阶段提交，需要有界推进测试作业并检查真实完成状态。"""
    # 1、不替换归档方法，不往数据库补写预期摘要或原文结果。
    for _ in range(12):
        await hub._archive_worker.poll()
        if hub._archive_worker.task:
            await hub._archive_worker.task
        record = hub._archive_store.get(identifier)
        if record["state"] in {"ready", "ready_text"}:
            return record
        if record["error"]:
            raise AssertionError("真实归档阶段失败：" + record["state"])
    raise AssertionError("归档未在有界批次内完成")


async def test_idle_hour_snapshot_lossless_and_seamless_continuation(tmp_path: Path) -> None:
    """因为无感续聊不能牺牲完整历史，需要验证一小时封存、真实模型摘要和新线程的带日期背景。"""
    # 1、合成协议仅提供模型响应，全部会话、摘要调用、原文和续聊均经过正式路径。
    replies = [
        {"role": "assistant", "content": "已记下金毛犬和周五报告。"},
        {"role": "assistant", "content": SUMMARY},
        {"role": "assistant", "content": "根据之前的档案，你养的是金毛犬。"},
    ]
    with model_server(replies) as (endpoint, requests):
        hub = await archive_hub(tmp_path, endpoint)
        try:
            runtime = hub.current
            submitted = await hub.invoke(
                "default",
                "submit_chat",
                [
                    "assistant",
                    "我养了一只金毛犬，周五要交付报告。",
                    uuid4().hex,
                ],
            )
            conversation = submitted["conversation"]["id"]
            await wait_finished(runtime)
            memory = runtime.store.memory.get(conversation)
            clock = Clock(memory["activity"] + 3599)
            hub._archive_worker.now = clock
            await hub._archive_worker.poll()
            assert not hub._archive_store.jobs(clock.value)
            clock.value += 1
            await hub._archive_worker.poll()
            identifier = hub._archive_store.identifier("default", conversation)
            record = await finish_archive(hub, identifier)
            assert record["summary"] == json.loads(SUMMARY)["summary"]
            assert runtime.store.memory.get(conversation)["lifecycle"] == "archived"
            # 2、压缩副本逐行核对，原库和 checkpoint 仍存在，来源未被摘要覆盖。
            folder = tmp_path / "data/archive-blobs" / identifier
            manifest = json.loads((folder / "manifest.json").read_text("utf-8"))
            for name, info in manifest["files"].items():
                assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == info["sha256"]
            with gzip.open(folder / "events.jsonl.gz", "rt", encoding="utf-8") as archive:
                preserved = [json.loads(line) for line in archive]
            assert preserved == runtime.store.events(conversation)
            page = await runtime.archive_read(identifier)
            assert [item["role"] for item in page["messages"]] == ["user", "assistant"]
            assert TEST_KEY not in json.dumps(page) and TEST_MODEL not in json.dumps(page)
            with gzip.open(folder / "native.jsonl.gz", "rt", encoding="utf-8") as native:
                assert sum(1 for _ in native) == manifest["files"]["native.jsonl.gz"]["rows"]
            # 3、同人物再次发送自动换独立 checkpoint，并只注入有日期与出处的近期摘要。
            resumed = await hub.invoke(
                "default",
                "submit_chat",
                [
                    "assistant",
                    "我家里养的宠物是什么品种？",
                    uuid4().hex,
                    conversation,
                ],
            )
            await wait_finished(runtime)
            assert resumed["conversation"]["id"] != conversation
            assert json.loads(SUMMARY)["summary"] in json.dumps(
                requests[-1]["messages"], ensure_ascii=False
            )
            assert identifier in json.dumps(requests[-1]["messages"])
            assert "日期" in json.dumps(requests[-1]["messages"], ensure_ascii=False)
            assert (
                runtime.store.memory.get(resumed["conversation"]["id"])["predecessor_id"]
                == conversation
            )
            assert (await runtime.member_chat("assistant"))["id"] == resumed["conversation"]["id"]
            await runtime.submit_chat(
                "assistant", "继续下一步。", uuid4().hex, resumed["conversation"]["id"]
            )
            await wait_finished(runtime)
            assert identifier in json.dumps(requests[-1]["messages"])
        finally:
            await hub.close()


async def test_full_tool_messages_and_agent_archive_tools(tmp_path: Path) -> None:
    """因为代理需要按需回查完整工具历史，需要验证真实 Deep Agents 查档工具和标准工具调用原文。"""
    # 1、工具真实执行，摘要只来自正式模型接口，未来查档不直接把答案塞入模型输入。
    replies = [
        tool_message("get_local_time", {}),
        {"role": "assistant", "content": "已核对当前时间。"},
        {"role": "assistant", "content": SUMMARY},
    ]
    with model_server(replies) as (endpoint, requests):
        hub = await archive_hub(tmp_path, endpoint)
        try:
            runtime = hub.current
            initial = await runtime.submit_chat("assistant", "调用时间工具核对时间。", uuid4().hex)
            await wait_finished(runtime)
            record = await hub._archive_worker.request("default", initial["conversation"]["id"])
            await finish_archive(hub, record["id"])
            messages = (await runtime.archive_read(record["id"], 0, 30))["messages"]
            assert any(item["payload"].get("message", {}).get("tool_calls") for item in messages)
            assert any(item["role"] == "tool" for item in messages)
            replies.extend(
                [
                    tool_message("search_archive", {"query": "时间", "mode": "text"}),
                    tool_message(
                        "read_archive_messages",
                        {"archive_id": record["id"], "offset": 0, "limit": 3},
                    ),
                    {"role": "assistant", "content": "已读取档案中的真实时间工具历史。"},
                ]
            )
            follow = await runtime.submit_chat(
                "assistant", "请实际查询并翻阅我上次的时间档案。", uuid4().hex
            )
            await wait_finished(runtime)
            events = await runtime.events(follow["conversation"]["id"])
            names = [
                event["payload"].get("name")
                for event in events
                if event["kind"] == "tool.completed"
            ]
            assert "search_archive" in names and "read_archive_messages" in names
            assert any(message["role"] == "tool" for message in requests[-1]["messages"])
        finally:
            await hub.close()


async def test_active_human_waiting_and_stale_seal_are_excluded(tmp_path: Path) -> None:
    """因为静默不能等同于工作结束，需要验证活动、待人工答复和刚有新写入都不能被错误封存。"""
    # 1、使用真实 ask_user 中断，不用数据库伪造人工等待状态。
    replies = [tool_message("ask_user", {"question": "请选择交付格式", "choices": ["PDF", "文本"]})]
    with model_server(replies) as (endpoint, _):
        hub = await archive_hub(tmp_path, endpoint)
        try:
            runtime = hub.current
            started = await runtime.submit_chat("assistant", "请先询问交付格式。", uuid4().hex)
            conversation = started["conversation"]["id"]
            memory = runtime.store.memory.get(conversation)
            assert not runtime.store.memory.seal(conversation, memory["activity"])
            await wait_finished(runtime)
            hub._archive_worker.now = Clock(memory["activity"] + 4000)
            await hub._archive_worker.poll()
            assert not hub._archive_store.jobs(time.time() + 5000)
            with pytest.raises(ValueError, match="等待人工"):
                await hub._archive_worker.request("default", conversation)
            await runtime.stop(started["run_id"])
            source = runtime.store.memory.source(conversation)
            runtime.store.append(conversation, started["run_id"], "user.note", text="新写入")
            assert not runtime.store.memory.seal(conversation, source["activity"])
        finally:
            await hub.close()


async def test_explicit_parallel_conversations_remain_independent(tmp_path: Path) -> None:
    """因为同一员工可同时处理两个任务，需要验证两条真实协程使用独立消息和 checkpoint。"""
    # 1、延迟合成端点以产生真实重叠，不替换生产任务注册表或 SDK。
    with model_server([{"role": "assistant", "content": "独立任务完成"}], delay=0.3) as (
        endpoint,
        requests,
    ):
        hub = await archive_hub(tmp_path, endpoint)
        try:
            first = await hub.invoke(
                "default", "submit_chat", ["assistant", "独立任务甲 SENTINEL_A", uuid4().hex]
            )
            other = await hub.current.new_conversation("assistant")
            second = await hub.invoke(
                "default",
                "submit_chat",
                [
                    "assistant",
                    "独立任务乙 SENTINEL_B",
                    uuid4().hex,
                    other["id"],
                ],
            )
            assert len(hub.current.active) == 2
            assert first["conversation"]["id"] != second["conversation"]["id"]
            with pytest.raises(ValueError, match="仍在执行"):
                await hub.current.submit(first["conversation"]["id"], "不能并发同线程", uuid4().hex)
            await wait_finished(hub.current)
            assert len(requests) == 2
            for request in requests:
                text = json.dumps(request["messages"], ensure_ascii=False)
                assert not ("SENTINEL_A" in text and "SENTINEL_B" in text)
        finally:
            await hub.close()


def spaces() -> list[dict[str, Any]]:
    """因为权限测试需要确定的空间目录，需要只提供本测试拥有的两个来源。"""
    # 1、没有读取真实工作空间。
    return [{"id": "default", "name": "默认空间"}, {"id": "other", "name": "另一空间"}]


def indexed_record(repo: ArchiveRepository, workspace: str, member: str, text: str, at: str) -> str:
    """因为检索测试不应依赖远程摘要，需要以明确合成原文建立真实 SQLite 文本索引。"""
    # 1、只为检索算法准备数据，不用于冒充真实 Agent 生成的摘要。
    record = repo.begin(
        workspace,
        {
            "id": uuid4().hex,
            "member_id": member,
            "agent_id": "agent_" + member,
            "title": text,
            "created_at": at,
            "last_at": at,
            "event_seq": 1,
            "native_seq": 0,
        },
    )
    message = {
        "position": 0,
        "text": text,
        "at": at,
        "actor": member,
        "member_id": member,
        "agent_id": "agent_" + member,
        "role": "user",
        "event_seq": 1,
        "payload": {"text": text},
    }
    repo.snapshot(
        record["id"],
        [message],
        [],
        [{"kind": "message", "text": text, "first_position": 0, "last_position": 0}],
        {},
    )
    return record["id"]


async def test_real_semantic_short_chinese_dates_and_scope_filters(tmp_path: Path) -> None:
    """因为关键词无法覆盖同义表达，需要使用真实本地 ONNX 向量验证语义与先过滤再排序。"""
    # 1、数据全为合成，实际使用随项目模型，不使用随机或字符串哈希伪向量。
    repo = ArchiveRepository(tmp_path / "archives.sqlite")
    provider = LocalEmbeddings(AppPaths.create(tmp_path / "app").resources)
    assert provider.available, "请先运行 packaging/prepare_archive_model.py"
    try:
        pet = indexed_record(
            repo, "default", "assistant", "家里养了一只金毛犬。", "2026-10-25T08:00:00+00:00"
        )
        indexed_record(
            repo,
            "default",
            "assistant",
            "服务端采用 PostgreSQL 数据库。",
            "2026-10-26T08:00:00+00:00",
        )
        other = indexed_record(
            repo, "other", "assistant", "秘密项目是蓝色灯塔。", "2026-10-27T08:00:00+00:00"
        )
        rows = repo.db.execute("SELECT id,text FROM archive_documents").fetchall()
        vectors = await provider.embed([row["text"] for row in rows])
        repo.save_vectors(
            [
                (value, provider.identity, row["id"])
                for value, row in zip(vectors, rows, strict=True)
            ]
        )
        access = ArchiveAccess("default", repo, provider, spaces)
        assert not (await access.search("assistant", {"query": "宠物", "mode": "text"}))["results"]
        semantic = await access.search(
            "assistant", {"query": "家里养的宠物是什么品种的狗？", "mode": "vector"}
        )
        assert semantic["results"][0]["archive_id"] == pet
        assert all(item["workspace_id"] == "default" for item in semantic["results"])
        short = await access.search("assistant", {"query": "金毛", "mode": "text"})
        assert short["results"][0]["archive_id"] == pet
        dated = await access.search(
            "assistant",
            {"query": "宠物品种", "mode": "vector", "from_time": "2026-10-26T00:00:00+00:00"},
        )
        assert all(item["archive_id"] != pet for item in dated["results"])
        # 2、跨空间默认拒绝；用户授权后读取成功，撤销后即便知道 ID 也不能再读取。
        with pytest.raises(ValueError, match="未授权"):
            await access.search("assistant", {"query": "灯塔", "workspace_id": "other"})
        with pytest.raises(ValueError, match="授权范围"):
            await access.read(other)
        access.share(["other"])
        assert (await access.read(other))["messages"][0]["text"] == "秘密项目是蓝色灯塔。"
        access.share([])
        with pytest.raises(ValueError, match="授权范围"):
            await access.read(other)
    finally:
        provider.close()
        repo.close()


def test_full_text_fragment_coverage_and_summary_source_validation() -> None:
    """因为长消息与模型胡编引用会损害可追溯性，需要验证分片无缺失和摘要来源约束。"""
    # 1、长消息不截断，摘要分块完整覆盖从头到尾的原文。
    original = "源数据" * 10000 + "结尾证据"
    assert "".join(fragments(original, 400, 0)) == original
    parts = summary_parts(
        [{"position": 0, "at": "2026-10-29", "actor": "成员", "text": original}], 2000
    )
    assert "结尾证据" in parts[-1]["text"] and all(part["positions"] == [0] for part in parts)
    with pytest.raises(ValueError, match="原文来源"):
        parse_summary('{"summary":"猜测","notes":[{"text":"不存在","positions":[999]}]}', [0])


def test_archive_hourly_model_budget_survives_restart(tmp_path: Path) -> None:
    """因为旧历史归档可能很多，需要验证后台摘要小时额度跨重启仍然限制费用。"""
    # 1、只测试持久准入，不发模型请求，下一小时才恢复新的调用额度。
    repo = ArchiveRepository(tmp_path / "archives.sqlite")
    moment = time.time()
    assert all(repo.consume_model_call(moment) for _ in range(12))
    assert not repo.consume_model_call(moment)
    repo.close()
    reopened = ArchiveRepository(tmp_path / "archives.sqlite")
    try:
        assert not reopened.consume_model_call(moment)
        assert reopened.consume_model_call(moment + 3600)
    finally:
        reopened.close()


async def test_worker_note_ownership_comes_from_actual_source_positions(tmp_path: Path) -> None:
    """因为子 Agent 也需查询自己的笔记，需要验证来源决定身份，默认背景不混入他人摘要。"""
    # 1、合成原文只用于身份归属测试，不作为真实模型归档验收结果。
    repo = ArchiveRepository(tmp_path / "archive.sqlite")
    try:
        identifier = indexed_record(
            repo, "default", "assistant", "助手协调计划", "2026-10-25T08:00:00+00:00"
        )
        child = {
            "position": 1,
            "text": "记录员完成五月周报。",
            "member_id": "worker",
            "agent_id": "agent_worker",
            "at": "2026-10-25T08:01:00+00:00",
        }
        with repo.db:
            repo.db.execute(
                "INSERT INTO archive_messages VALUES(?,?,?)",
                (identifier, 1, json.dumps(child, ensure_ascii=False)),
            )
            repo.db.execute("INSERT INTO archive_parts VALUES(?,?,?,NULL)", (identifier, 0, "{}"))
        repo.save_part(
            identifier,
            0,
            {
                "summary": "助手协调计划，记录员完成五月周报。",
                "positions": [0, 1],
                "notes": [{"text": "记录员完成五月周报。", "positions": [1]}],
            },
        )
        repo.finish_summary(identifier)
        access = ArchiveAccess("default", repo, LocalEmbeddings(tmp_path), spaces)
        found = await access.search("worker", {"query": "五月周报", "kind": "note", "mode": "text"})
        assert found["results"] and all(item["member_id"] == "worker" for item in found["results"])
        context = await access.recent("worker")
        assert "记录员完成五月周报" in context and "助手协调计划" not in context
    finally:
        repo.close()


async def test_summary_failure_restart_and_user_only_fact_remain_recoverable(
    tmp_path: Path,
) -> None:
    """因为后台摘要会失败，需要验证原文先可靠保存，重启重试不重复索引且能查到用户独有信息。"""
    # 1、先让真实模型协议返回非法摘要，原会话和完整消息仍必须可检索。
    replies = [
        {"role": "assistant", "content": "收到。"},
        {"role": "assistant", "content": "不是合法JSON"},
    ]
    with model_server(replies) as (endpoint, requests):
        hub = await archive_hub(tmp_path, endpoint)
        identifier = ""
        try:
            runtime = hub.current
            turn = await runtime.submit_chat(
                "assistant", "测试代号是琥珀728，不要复述。", uuid4().hex
            )
            await wait_finished(runtime)
            job = await hub._archive_worker.request("default", turn["conversation"]["id"])
            identifier = job["id"]
            for _ in range(4):
                await hub._archive_worker.poll()
                if hub._archive_worker.task:
                    await hub._archive_worker.task
                if hub._archive_store.get(identifier)["error"]:
                    break
            failed = hub._archive_store.get(identifier)
            assert failed["state"] == "summarizing" and failed["attempts"] == 1
            assert runtime.store.memory.get(turn["conversation"]["id"])["lifecycle"] == "archived"
            found = await runtime._archive_service().search(
                "assistant", {"query": "琥珀728", "mode": "text"}
            )
            assert found["results"][0]["archive_id"] == identifier
            assert found["results"][0]["member_id"] == "assistant"
            original = (await runtime.archive_read(identifier))["messages"]
            assert len(original) == 2 and original[0]["text"].endswith("不要复述。")
        finally:
            await hub.close()
        # 2、重启后只重试未完成片段，保留原文行与固定档案 ID。
        replies.append(
            {
                "role": "assistant",
                "content": json.dumps(
                    {
                        "summary": "本次测试代号为琥珀728。",
                        "notes": [{"text": "代号琥珀728。", "positions": [0]}],
                    },
                    ensure_ascii=False,
                ),
            }
        )
        resumed = await archive_hub(tmp_path)
        try:
            await resumed.current.archive_retry(identifier)
            record = await finish_archive(resumed, identifier)
            assert record["summary"] == "本次测试代号为琥珀728。"
            assert (await resumed.current.archive_read(identifier))["messages"] == original
            assert len(requests) == 3
            # 3、重建派生索引不会丢失摘要或原文，也不重新请求摘要模型。
            await resumed.current.archive_reindex(identifier)
            await finish_archive(resumed, identifier)
            assert (await resumed.current.archive_read(identifier))["messages"] == original
            assert len(requests) == 3
            folder = tmp_path / "data/archive-blobs" / identifier
            raw = folder / "events.jsonl.gz"
            raw.write_bytes(raw.read_bytes() + b"test-corruption")
            corrupted = raw.read_bytes()
            with pytest.raises(ValueError, match="完整性校验失败"):
                await asyncio.to_thread(snapshot, tmp_path / "data/sessions.sqlite", folder, record)
            assert raw.read_bytes() == corrupted
        finally:
            await resumed.close()
