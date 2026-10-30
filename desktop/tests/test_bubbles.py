"""人物泡泡的稳定身份、已读回执和任务状态解耦验证。"""

import json
import sqlite3
from pathlib import Path

import pytest

from roomcrew.platform.paths import AppPaths
from roomcrew_desktop.runtime import DesktopRuntime


async def test_viewed_conversation_acknowledges_only_loaded_results_for_the_clicked_member(
    tmp_path: Path,
) -> None:
    """因为同会话多轮结果一次展示，需要一起已读但保留其他人物、会话、人工问题和迟到结果。"""
    # 1、为同一个主人物建立两轮完成，并混入另一人物及另一会话的完成结果。
    paths = AppPaths.create(tmp_path)
    runtime = DesktopRuntime(paths)
    await runtime.start()
    try:
        conversation = runtime.store.create_conversation("synthetic")
        for index in range(2):
            run = runtime.store.begin(conversation["id"], "一轮结果", f"viewed-round-{index}")
            runtime.store.finish(run, "completed", {})
        initial = (await runtime.studio_feed())["actors"][0]["bubble_notice"]
        worker = await runtime.save_member({"name": "另一个入口"}, 0)
        other_run = runtime.store.begin(
            conversation["id"],
            "其他入口",
            "other-entry-result",
            worker["name"],
            worker["agent_id"],
            worker["id"],
        )
        runtime.store.finish(other_run, "completed", {})
        other = runtime.store.create_conversation("synthetic")
        other_run = runtime.store.begin(other["id"], "其他会话", "other-thread-result")
        runtime.store.finish(other_run, "completed", {})
        # 2、模拟页面实际拉取到的上界；随后产生的新结果不能被这次回执吞掉。
        through = runtime.store.events(conversation["id"])[-1]["seq"]
        late = runtime.store.begin(conversation["id"], "晚到结果", "late-result")
        runtime.store.finish(late, "completed", {})
        question = runtime.store.begin(conversation["id"], "人工问题", "unanswered")
        runtime.store.append(
            conversation["id"], question, "human.requested", request_id="keep-question"
        )
        await runtime.studio_feed()
        for invalid in (True, initial["source_seq"] - 1):
            with pytest.raises(ValueError, match="加载"):
                await runtime.acknowledge_bubble("assistant", initial["id"], invalid)
        await runtime.acknowledge_bubble("assistant", initial["id"], through)
        await runtime.acknowledge_bubble("assistant", initial["id"], through)
        actors = {a["member_id"]: a for a in (await runtime.studio_feed())["actors"]}
        assert actors["assistant"]["bubble_pending_count"] == 3
        assert actors["assistant"]["bubble_notice"]["kind"] == "question"
        assert actors[worker["id"]]["bubble_pending_count"] == 1
        with sqlite3.connect(paths.data / "bubbles.sqlite") as db:
            assert (
                db.execute("SELECT count(*) FROM bubble_notices WHERE status='seen'").fetchone()[0]
                == 2
            )
        # 3、查看当前会话全部结果后仅剩其他会话与未答问题，任务权威状态保持原样。
        through = runtime.store.events(conversation["id"])[-1]["seq"]
        await runtime.acknowledge_bubble("assistant", initial["id"], through)
        assert (await runtime.studio_feed())["actors"][0]["bubble_pending_count"] == 2
        assert runtime.store.latest_status(other["id"]) == "completed"
    finally:
        await runtime.close()


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
        assert actor["bubble_is_history"]
        assert "当前任务仍在进行" in actor["bubble"]
        assert "干完" not in actor["bubble"]
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


async def test_delegation_bubbles_belong_to_the_entry_member(tmp_path: Path) -> None:
    """因为任务入口负责对用户汇报，需要验证子任务完成无泡泡且人工请求由非默认主人物转达。"""
    # 1、主子人物共用定义也按 run.started 区分，子任务返回不等于主任务完成。
    runtime = DesktopRuntime(AppPaths.create(tmp_path))
    await runtime.start()
    try:
        lead = await runtime.save_member({"name": "入口同事", "agent_id": "agent_assistant"}, 0)
        member = await runtime.save_member({"name": "执行同事", "agent_id": "agent_assistant"}, 0)
        conversation = runtime.store.create_conversation("synthetic")
        run = runtime.store.begin(
            conversation["id"], "委派", "worker-result", lead["name"], lead["agent_id"], lead["id"]
        )
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
        assert not any(actor["bubble"] for actor in actors.values())
        # 2、子任务的人工请求归主人物展示，源身份、问题 ID 和恢复目标保持不变。
        runtime.store.append(
            conversation["id"],
            run,
            "human.requested",
            member["name"],
            "worker:two",
            member_id=member["id"],
            request_id="delegated-question",
        )
        runtime.store.append(conversation["id"], run, "run.waiting_user", member_id=lead["id"])
        data = await runtime.studio_feed()
        actors = {item["member_id"]: item for item in data["actors"]}
        notice = actors[lead["id"]]["bubble_notice"]
        assert notice["member_id"] == lead["id"]
        assert notice["source_member_id"] == member["id"]
        assert actors[lead["id"]]["requires_input"]
        assert actors[lead["id"]]["material_category"] == "human"
        assert not actors[member["id"]]["requires_input"]
        assert not actors[member["id"]]["bubble"]
        assert data["question_presenters"] == {"delegated-question": lead["id"]}
        assert all(cue["member_id"] == lead["id"] for cue in data["cues"] if cue["action"] == "ask")
        # 3、最终仅主任务产生一个完成泡泡，错误人物不能代读，实际身份仍保留在轨迹。
        runtime.store.append(
            conversation["id"],
            run,
            "human.responded",
            member["name"],
            "worker:two",
            member_id=member["id"],
            request_id="delegated-question",
        )
        runtime.store.finish(run, "completed", {})
        actors = {item["member_id"]: item for item in (await runtime.studio_feed())["actors"]}
        notice = actors[lead["id"]]["bubble_notice"]
        assert notice["kind"] == "result"
        assert actors[lead["id"]]["bubble_pending_count"] == 1
        assert not actors[member["id"]]["bubble"]
        assert not actors.get("assistant", {}).get("bubble")
        with pytest.raises(ValueError, match="没有"):
            await runtime.acknowledge_bubble(member["id"], notice["id"])
        await runtime.acknowledge_bubble(lead["id"], notice["id"])
        assert runtime.store.latest_status(conversation["id"]) == "completed"
    finally:
        await runtime.close()


async def test_legacy_child_notices_retire_without_losing_read_receipts(tmp_path: Path) -> None:
    """因为已有用户会保存旧版子任务泡泡，需要验证迁移清理旧提示且保留主结果的已读状态。"""
    # 1、建立真实历史事件及新版表，再模拟上一版保存的子任务提示与待处理人工问题。
    paths = AppPaths.create(tmp_path)
    runtime = DesktopRuntime(paths)
    await runtime.start()
    try:
        worker = await runtime.save_member({"name": "子成员"}, 0)
        conversation = runtime.store.create_conversation("synthetic")
        seen_run = runtime.store.begin(conversation["id"], "已读结果", "seen-before-migration")
        runtime.store.finish(seen_run, "completed", {})
        actor = (await runtime.studio_feed())["actors"][0]
        await runtime.acknowledge_bubble("assistant", actor["bubble_notice"]["id"])
        run = runtime.store.begin(conversation["id"], "待回复", "old-question-run")
        child_seq = runtime.store.append(
            conversation["id"], run, "task.completed", scope="child:old", member_id=worker["id"]
        )
        question_seq = runtime.store.append(
            conversation["id"],
            run,
            "human.requested",
            scope="child:next",
            member_id=worker["id"],
            request_id="old-child-question",
        )
        with sqlite3.connect(paths.data / "bubbles.sqlite") as db:
            for kind, identifier, seq, request in (
                ("result", f"result:{run}:child:old", child_seq, None),
                ("question", "question:old-child-question", question_seq, "old-child-question"),
            ):
                notice = {
                    "id": identifier,
                    "member_id": worker["id"],
                    "run_id": run,
                    "kind": kind,
                    "conversation_id": conversation["id"],
                    "request_id": request,
                    "source_seq": seq,
                    "scope": "child:old",
                }
                db.execute(
                    "INSERT INTO bubble_notices VALUES(?,?,?,?,?,?,?,?)",
                    (
                        identifier,
                        worker["id"],
                        run,
                        kind,
                        request,
                        seq,
                        "pending",
                        json.dumps(notice),
                    ),
                )
            db.execute("PRAGMA user_version=0")
        # 2、迁移后子完成退役，人工请求转交主人物；重放两次也不恢复已读结果。
        for _ in range(2):
            data = await runtime.studio_feed()
            actors = {item["member_id"]: item for item in data["actors"]}
            assert not actors[worker["id"]]["bubble"]
            assert actors["assistant"]["bubble_pending_count"] == 1
            assert actors["assistant"]["bubble_notice"]["id"] == "question:old-child-question"
        with sqlite3.connect(paths.data / "bubbles.sqlite") as db:
            assert (
                db.execute(
                    "SELECT status FROM bubble_notices WHERE id=?", (f"result:{run}:child:old",)
                ).fetchone()[0]
                == "retired"
            )
            assert (
                db.execute(
                    "SELECT status FROM bubble_notices WHERE run_id=?", (seen_run,)
                ).fetchone()[0]
                == "seen"
            )
    finally:
        await runtime.close()
