"""人物泡泡的稳定身份、已读回执和任务状态解耦验证。"""

from pathlib import Path

import pytest

from roomcrew.platform.paths import AppPaths
from roomcrew_desktop.runtime import DesktopRuntime


async def test_unread_result_survives_new_tasks_restart_and_projection_rebuild(
    tmp_path: Path,
) -> None:
    """因为未读结果不能随任务切换消失，需要验证新任务、重启和投影重建都保留未读回执。"""
    # 1、第一轮完成后再开始另一会话，泡泡仍指向原始结果，不跟随最新任务状态消失。
    paths = AppPaths.create(tmp_path)
    runtime = DesktopRuntime(paths)
    await runtime.start()
    try:
        first = runtime.store.create_conversation("synthetic")
        run = runtime.store.begin(first["id"], "第一轮", "first-bubble-request")
        runtime.store.finish(run, "completed", {})
        initial = (await runtime.studio_feed())["actors"][0]["bubble_notice"]
        second = runtime.store.create_conversation("synthetic")
        next_run = runtime.store.begin(second["id"], "第二轮", "second-bubble-request")
        actor = (await runtime.studio_feed())["actors"][0]
        assert actor["activity"] != "reporting"
        assert actor["bubble_notice"] == initial
        assert actor["bubble_notice"]["conversation_id"] == first["id"]
        runtime.store.finish(next_run, "completed", {})
    finally:
        await runtime.close()
    # 2、重新启动保留两条未读；仅确认点击的第一条，不吞掉另一个结果。
    reopened = DesktopRuntime(paths)
    await reopened.start()
    try:
        actor = (await reopened.studio_feed())["actors"][0]
        assert actor["bubble_pending_count"] == 2
        assert actor["bubble_notice"]["id"] == initial["id"]
        await reopened.acknowledge_bubble("assistant", initial["id"])
        actor = (await reopened.studio_feed())["actors"][0]
        assert actor["bubble_pending_count"] == 1
        assert actor["bubble_notice"]["conversation_id"] == second["id"]
        await reopened.acknowledge_bubble("assistant", actor["bubble_notice"]["id"])
        assert not (await reopened.studio_feed())["actors"][0]["bubble"]
    finally:
        await reopened.close()
    # 3、丢弃动画投影缓存不会丢失已读记录；重放历史不能重新弹出已处理的泡泡。
    (paths.data / "presentation.sqlite").unlink()
    rebuilt = DesktopRuntime(paths)
    await rebuilt.start()
    try:
        assert not (await rebuilt.studio_feed())["actors"][0]["bubble"]
    finally:
        await rebuilt.close()


async def test_question_bubble_requires_a_real_answer_and_keeps_old_result(tmp_path: Path) -> None:
    """因为打开或关闭人工表单不是答复，需要验证问题保留、真实答复解除和旧结果独立存在。"""
    # 1、完成结果保持未读；新人工问题优先展示但不覆盖它。
    runtime = DesktopRuntime(AppPaths.create(tmp_path))
    await runtime.start()
    try:
        conversation = runtime.store.create_conversation("synthetic")
        first = runtime.store.begin(conversation["id"], "完成", "prior-result")
        runtime.store.finish(first, "completed", {})
        run = runtime.store.begin(conversation["id"], "提问", "human-bubble")
        runtime.store.append(conversation["id"], run, "human.requested", request_id="question-one")
        notice = (await runtime.studio_feed())["actors"][0]["bubble_notice"]
        assert notice["kind"] == "question"
        with pytest.raises(ValueError, match="答复"):
            await runtime.acknowledge_bubble("assistant", notice["id"])
        assert (await runtime.studio_feed())["actors"][0]["bubble_notice"] == notice
        # 2、只处理正式答复事件；取消新任务也不能把上一次结果误标记已读。
        runtime.store.append(conversation["id"], run, "human.responded", request_id="question-one")
        runtime.store.finish(run, "cancelled", {})
        actor = (await runtime.studio_feed())["actors"][0]
        assert actor["bubble_notice"]["kind"] == "result"
        assert actor["bubble_notice"]["run_id"] == first
    finally:
        await runtime.close()


async def test_worker_bubble_belongs_to_the_actual_member(tmp_path: Path) -> None:
    """因为多位员工可复用 Agent 定义，需要验证子任务完成通知和已读不能串到另一人物。"""
    # 1、两个形象共用配置；有形象子任务完成只登记实际执行成员。
    runtime = DesktopRuntime(AppPaths.create(tmp_path))
    await runtime.start()
    try:
        member = await runtime.save_member({"name": "同事", "agent_id": "agent_assistant"}, 0)
        conversation = runtime.store.create_conversation("synthetic")
        run = runtime.store.begin(conversation["id"], "委派", "worker-result")
        runtime.store.append(
            conversation["id"],
            run,
            "task.completed",
            member["name"],
            "worker:one",
            agent_id=member["agent_id"],
            member_id=member["id"],
            delegation_kind="configured",
            status="success",
        )
        data = await runtime.studio_feed()
        actors = {item["member_id"]: item for item in data["actors"]}
        notice = actors[member["id"]]["bubble_notice"]
        assert notice["member_id"] == member["id"]
        assert not actors["assistant"]["bubble"]
        with pytest.raises(ValueError, match="没有"):
            await runtime.acknowledge_bubble("assistant", notice["id"])
        # 2、读取真正成员的结果只消除他的泡泡，不修改真实 Run 状态。
        await runtime.acknowledge_bubble(member["id"], notice["id"])
        assert runtime.store.latest_status(conversation["id"]) == "running"
        data = await runtime.studio_feed()
        assert not next(item for item in data["actors"] if item["member_id"] == member["id"])[
            "bubble"
        ]
    finally:
        await runtime.close()
