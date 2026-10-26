"""多会议室的身份、数据边界和真实执行回归。"""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

import pytest
from test_runtime import TEST_KEY, TEST_MODEL, model_server, tool_message, wait_finished

from roomcrew.application.workspaces import WorkspaceHub
from roomcrew.platform.paths import AppPaths
from roomcrew.storage.workspaces import WorkspaceRepository
from roomcrew_desktop.api import DesktopAPI
from roomcrew_desktop.host import RuntimeThread


def test_workspace_directory_keeps_unique_rooms_and_selection(tmp_path: Path) -> None:
    """因为空间名称可改而会议室身份必须稳定，需要验证一对一、输入边界与重启恢复。"""
    # 1、目录只存元数据，不因为显示名称相同就共享房间。
    path = tmp_path / "workspaces.sqlite"
    repo = WorkspaceRepository(path)
    first = repo.create("资料")
    second = repo.create("资料")
    assert first["room_id"] != second["room_id"]
    repo.select(first["id"])
    renamed = repo.rename(first["id"], "研究 <室>")
    assert renamed["id"] == first["id"] and renamed["room_id"] == first["room_id"]
    for value in ("", "x" * 61, "坏\n名称"):
        with pytest.raises(ValueError):
            repo.create(value)
    for _ in range(13):
        repo.create("独立会议室")
    with pytest.raises(ValueError, match="16"):
        repo.create("超额")
    repo.close()
    # 2、恢复上次选择，所有房间仍只有一个对应空间。
    reopened = WorkspaceRepository(path)
    assert reopened.active() == first["id"]
    assert len({item["room_id"] for item in reopened.list()}) == 16
    reopened.close()


async def configured_hub(root: Path, endpoint: str) -> WorkspaceHub:
    """因为验证不能使用真实凭据，需要通过生产入口保存模拟配置并启动空间装配。"""
    # 1、使用真实 DPAPI 和 Runtime，不替换生产用例或 Agent 循环。
    hub = WorkspaceHub(AppPaths.create(root))
    await hub.start()
    await hub.invoke(
        "default",
        "save_configuration",
        [{"base_url": endpoint, "model": TEST_MODEL, "api_key": TEST_KEY}],
    )
    return hub


@pytest.mark.integration
async def test_room_switch_preserves_legacy_and_scopes_every_request(tmp_path: Path) -> None:
    """因为切换时旧请求可能迟到，需要验证显式请求不随活动房间改派，并拒绝跨空间读取。"""
    # 1、原数据留在默认空间，新空间不复制成员、会话和文件。
    hub = await configured_hub(tmp_path, "http://127.0.0.1:1/v1")
    try:
        original = hub.current
        conversation = await hub.invoke("default", "new_conversation", [])
        marker = original.paths.session_files(conversation["id"]) / "original.txt"
        marker.write_text("旧空间文件", "utf-8")
        employee = await hub.invoke("default", "save_member", [{"name": "资料员"}, 0])
        directory = await hub.create("开发空间")
        identifier = directory["active"]["id"]
        current = hub.current
        assert current is not original
        assert current.paths.private == original.paths.private
        assert current.paths.sessions != original.paths.sessions
        assert marker.read_text("utf-8") == "旧空间文件"
        assert current.paths.data == tmp_path / "workspaces" / identifier / "data"
        assert len((await hub.invoke(identifier, "studio_feed", [0]))["members"]) == 2
        assert employee["id"] not in {item["id"] for item in current.accounts.members()}
        # 2、活动房间是新空间，但旧身份请求仍只写回默认会议室。
        late = await hub.invoke("default", "new_conversation", [])
        assert original.store.conversation(late["id"])
        assert not (await hub.invoke(identifier, "overview", []))["conversations"]
        for method, args in (
            ("events", [conversation["id"]]),
            ("artifacts", [conversation["id"]]),
            ("read_artifact", [conversation["id"], "original.txt"]),
        ):
            with pytest.raises(ValueError):
                await hub.invoke(identifier, method, args)
        for method in ("close", "config", "__dict__", "execution_replay"):
            with pytest.raises(ValueError):
                await hub.invoke(identifier, method, [])
        with pytest.raises(ValueError):
            await hub.invoke("../private", "overview", [])
        with pytest.raises(ValueError):
            hub.paths.for_workspace("../private")
        assert (await hub.invoke("default", "studio_feed", [0]))["workspace"][
            "room_id"
        ] == "room_default"
    finally:
        await hub.close()


@pytest.mark.integration
async def test_background_rooms_execute_independently_and_keep_model_private(
    tmp_path: Path,
) -> None:
    """因为切换会议室不能暂停旧任务，需要真实并行执行并核对两个上下文没有互相污染。"""
    # 1、同一模拟服务返回普通答案，真实 SDK 和 Deep Agents 各运行一次。
    with model_server([{"role": "assistant", "content": "处理完成"}], delay=0.25) as (
        endpoint,
        requests,
    ):
        hub = await configured_hub(tmp_path, endpoint)
        try:
            first = hub.current
            conversation_a = await hub.invoke("default", "new_conversation", [])
            request = uuid4().hex
            submitted = await hub.invoke(
                "default", "submit", [conversation_a["id"], "仅A空间的资料", request]
            )
            directory = await hub.create("第二空间")
            identifier = directory["active"]["id"]
            second = hub.current
            conversation_b = await hub.invoke(identifier, "new_conversation", [])
            await hub.invoke(
                identifier, "submit", [conversation_b["id"], "仅B空间的资料", uuid4().hex]
            )
            assert first.active and second.active
            status = await hub.state()
            assert sum(item["active_runs"] for item in status["workspaces"]) == 2
            with pytest.raises(ValueError, match="所有工作空间"):
                await hub.invoke(identifier, "save_configuration", [{}])
            await asyncio.gather(wait_finished(first), wait_finished(second))
            assert first.store.latest_status(conversation_a["id"]) == "completed"
            assert second.store.latest_status(conversation_b["id"]) == "completed"
            assert (
                await hub.invoke(
                    "default", "submit", [conversation_a["id"], "仅A空间的资料", request]
                )
            )["run_id"] == submitted["run_id"]
            assert len(requests) == 2
            # 2、服务看到的每份上下文只包含自己的任务，模型 Key 永不进入消息。
            for item in requests:
                messages = json.dumps(item["messages"], ensure_ascii=False)
                assert ("仅A空间的资料" in messages) != ("仅B空间的资料" in messages)
                assert TEST_KEY not in messages
            assert all(
                event["conversation_id"] == conversation_a["id"]
                for event in await first.events(conversation_a["id"])
            )
        finally:
            await hub.close()


@pytest.mark.integration
async def test_unopened_pending_room_protects_shared_model_configuration(tmp_path: Path) -> None:
    """因为重启后未打开的会议室也可能等待人工，需要保留待办计数并阻止破坏原模型绑定。"""
    # 1、通过真实 ask_user 进入等待，再切换默认空间并关闭全部连接。
    with model_server(
        [tool_message("ask_user", {"question": "确认资料用途", "choices": ["研究", "归档"]})]
    ) as (endpoint, _):
        hub = await configured_hub(tmp_path, endpoint)
        directory = await hub.create("等待确认")
        identifier = directory["active"]["id"]
        conversation = await hub.invoke(identifier, "new_conversation", [])
        await hub.invoke(identifier, "submit", [conversation["id"], "先问我资料用途", uuid4().hex])
        await wait_finished(hub.current)
        await hub.select("default")
        await hub.close()
    # 2、只启动默认会议室，侧栏仍能看见其他房间待办，但不返回问题正文。
    reopened = WorkspaceHub(AppPaths.create(tmp_path))
    await reopened.start()
    try:
        directory = await reopened.state()
        pending = next(item for item in directory["workspaces"] if item["id"] == identifier)
        assert pending["pending_count"] == 1 and identifier not in reopened.runtimes
        assert "确认资料用途" not in json.dumps(directory, ensure_ascii=False)
        with pytest.raises(ValueError, match="所有工作空间"):
            await reopened.invoke("default", "save_configuration", [{}])
        await reopened.select(identifier)
        assert (await reopened.current.questions())[0]["question"] == "确认资料用途"
    finally:
        await reopened.close()


def test_native_bridge_never_accepts_free_avatar_paths(tmp_path: Path) -> None:
    """因为通用桥不能成为宿主任意读入口，需要验证文件导入仍要求用户原生选择。"""
    # 1、使用真实后台线程，非法方法和空间都在任何业务操作之前拒绝。
    host = RuntimeThread(AppPaths.create(tmp_path))
    try:
        api = DesktopAPI(host)
        assert not api.invoke("default", "import_avatar", ["C:/private/key.json"])["ok"]
        assert not api.invoke("default", "close", [])["ok"]
        assert not api.invoke("../../private", "overview", [])["ok"]
        assert api.workspace_state()["data"]["active"]["id"] == "default"
    finally:
        host.close()
