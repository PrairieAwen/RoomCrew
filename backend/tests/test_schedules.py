"""持久计划、空间/Agent 绑定、幂等受理与真实 Deep Agents 定时工具验证。"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from mcp_fixture import mcp_server
from test_runtime import TEST_KEY, TEST_MODEL, model_server, tool_message, wait_finished

from roomcrew.application.workspaces import WorkspaceHub
from roomcrew.contracts.schedules import DispatchBusy
from roomcrew.platform.paths import AppPaths
from roomcrew.scheduling.triggers import next_fire, normalize_trigger


class TestClock:
    __test__ = False

    def __init__(self, value: float) -> None:
        """因为失败路径不应真实等待几天，需要为单元验证注入独立时钟而不改系统时间。"""
        # 1、此时钟只在测试协调器使用，真实五分钟验收不使用它。
        self.value = value

    def __call__(self) -> datetime:
        """因为协调器接收带时区时间，需要把测试时间戳转换为 UTC。"""
        # 1、不会替换工具 get_local_time 的系统时钟。
        return datetime.fromtimestamp(self.value, UTC)


async def schedule_hub(root: Path, endpoint: str | None = None) -> WorkspaceHub:
    """因为各测试必须隔离数据和计划，需要创建真实宿主并暂停自动滴答以精确控制边界。"""
    # 1、只暂停本测试的检查器，所有业务服务、SQLite、框架和工具仍是正式实现。
    hub = WorkspaceHub(AppPaths.create(root))
    await hub.start()
    await hub._schedule_timer.close()
    if endpoint:
        await hub.current.save_configuration(
            {"base_url": endpoint, "model": TEST_MODEL, "api_key": TEST_KEY}
        )
    return hub


def plan_values(member_id: str = "assistant") -> dict[str, Any]:
    """因为多个边界测试需要一致的普通任务，需要复用明确的五分钟示例配置。"""
    # 1、只包含公开参数，不配置模型端点或凭据。
    return {
        "title": "每五分钟看时间",
        "instruction": "调用 get_local_time 查看当前时间。",
        "target_member_id": member_id,
        "trigger": {"type": "interval", "seconds": 300},
    }


@pytest.mark.parametrize(
    "trigger",
    [
        {"type": []},
        {"type": "interval", "seconds": True},
        {"type": "interval", "seconds": 1},
        {"type": "daily", "time": "25:00"},
        {"type": "daily", "time": "14:30", "timezone": "invalid"},
        {"type": "weekly", "time": "14:30", "weekdays": [7]},
        {"type": "once", "at": "2026-10-29T14:30:00"},
        {"type": "daily", "time": "14:30", "callback": "exec"},
    ],
)
def test_invalid_schedule_rules_fail_before_persistence(trigger: Any) -> None:
    """因为模型可能生成无效时间或注入回调，需要在任何安排落库前拒绝。"""
    # 1、不发请求、不创建任务、不依赖用户本机时区。
    with pytest.raises(ValueError):
        normalize_trigger(trigger, datetime(2026, 10, 29, tzinfo=UTC))


def test_daily_weekly_interval_and_dst_are_explicit() -> None:
    """因为北京时间和夏令时不能靠固定偏移猜测，需要用真实时区数据库验证触发语义。"""
    # 1、每天北京时间两点半对应 UTC 六点半；今天已过后返回下一天。
    now = datetime(2026, 10, 29, 6, 0, tzinfo=UTC)
    daily = normalize_trigger({"type": "daily", "time": "14:30"}, now)
    assert next_fire(daily, now) == datetime(2026, 10, 29, 6, 30, tzinfo=UTC)
    assert next_fire(daily, datetime(2026, 10, 29, 6, 30, tzinfo=UTC)) == datetime(
        2026, 10, 30, 6, 30, tzinfo=UTC
    )
    weekly = normalize_trigger({"type": "weekly", "time": "14:30", "weekdays": [0]}, now)
    assert next_fire(weekly, now) == datetime(2026, 11, 2, 6, 30, tzinfo=UTC)
    interval = normalize_trigger({"type": "interval", "seconds": 300}, now)
    assert next_fire(interval, now) == now + timedelta(minutes=5)
    assert next_fire(interval, now + timedelta(minutes=6)) == now + timedelta(minutes=10)
    # 2、回拨重复时刻只执行第一次；春季不存在的时刻跳到下一次有效日历时间。
    fall = normalize_trigger(
        {"type": "daily", "time": "01:30", "timezone": "America/New_York"}, now
    )
    assert next_fire(fall, datetime(2026, 11, 1, 5, 30, tzinfo=UTC)) == datetime(
        2026, 11, 2, 6, 30, tzinfo=UTC
    )
    spring = normalize_trigger(
        {"type": "daily", "time": "02:30", "timezone": "America/New_York"}, now
    )
    assert next_fire(spring, datetime(2026, 3, 8, 5, 0, tzinfo=UTC)) == datetime(
        2026, 3, 9, 6, 30, tzinfo=UTC
    )


async def test_crud_is_bound_versioned_idempotent_and_durable(tmp_path: Path) -> None:
    """因为取消计划涉及持久自动执行，需要验证空间隔离、版本冲突和重放都不产生额外安排。"""
    # 1、新增操作同一命令重复提交返回相同计划，记录明确的目标配置 ID。
    hub = await schedule_hub(tmp_path)
    identifier = ""
    try:
        runtime = hub.current
        command = uuid4().hex
        created = await runtime.create_schedule(plan_values(), command)
        identifier = created["id"]
        assert created["workspace_id"] == "default"
        assert created["target_agent_id"] == runtime.accounts.get("assistant")["agent_id"]
        assert (await runtime.create_schedule(plan_values(), command))["id"] == identifier
        with pytest.raises(ValueError, match="其他操作"):
            await runtime.create_schedule({**plan_values(), "title": "另一个任务"}, command)
        assert len(await runtime.list_schedules()) == 1
        # 2、同一个 assistant ID 在另一个空间也不能读取或删除原计划。
        other = await hub.create("独立空间")
        other_id = other["active"]["id"]
        with pytest.raises(ValueError, match="当前工作空间"):
            await hub.invoke(other_id, "get_schedule", [identifier])
        with pytest.raises(ValueError):
            await hub.invoke(
                other_id, "set_schedule_state", [identifier, "deleted", 1, uuid4().hex]
            )
        changed = await runtime.update_schedule(
            identifier, {"title": "修改后的任务"}, 1, uuid4().hex
        )
        assert changed["revision"] == 2
        with pytest.raises(ValueError, match="已被修改"):
            await runtime.update_schedule(identifier, {"title": "旧版本覆盖"}, 1, uuid4().hex)
        paused = await runtime.set_schedule_state(identifier, "paused", 2, uuid4().hex)
        assert paused["next_fire"] is None
        resumed = await runtime.set_schedule_state(
            identifier, "active", paused["revision"], uuid4().hex
        )
        assert resumed["next_fire"] is not None
        deleted = await runtime.set_schedule_state(
            identifier, "deleted", resumed["revision"], uuid4().hex
        )
        assert deleted["state"] == "deleted" and deleted["next_fire"] is None
        with pytest.raises(ValueError, match="不能恢复"):
            await runtime.set_schedule_state(identifier, "active", deleted["revision"], uuid4().hex)
    finally:
        await hub.close()
    # 3、重启不会复活已取消计划，历史定义仍可查证。
    restarted = await schedule_hub(tmp_path)
    try:
        runtime = await restarted.runtime_for("default")
        assert not await runtime.list_schedules()
        assert (await runtime.get_schedule(identifier))["state"] == "deleted"
    finally:
        await restarted.close()


async def test_due_runs_target_agent_once_with_independent_thread_and_standard_trace(
    tmp_path: Path,
) -> None:
    """因为唤起必须沿用目标配置和官方框架，需要真实执行工具、验证轨迹并模拟丢失受理回执。"""
    # 1、模型只有确定性协议响应，时间工具、Agent 装配、SQLite 与检查点都是真实实现。
    replies = [
        tool_message("get_local_time", {}),
        {"role": "assistant", "content": "已通过工具查看当前时间"},
    ]
    with model_server(replies) as (endpoint, requests):
        hub = await schedule_hub(tmp_path, endpoint)
        try:
            runtime = hub.current
            worker = await runtime.save_member(
                {"name": "计时员", "prompt": "TARGET_PROMPT_SENTINEL"}, 0
            )
            created = await runtime.create_schedule(plan_values(worker["id"]), uuid4().hex)
            hub._schedule_coordinator._now = TestClock(created["next_fire"] + 0.1)
            await hub._schedule_coordinator.poll()
            await wait_finished(runtime)
            await hub._schedule_coordinator.poll()
            history = (await runtime.get_schedule(created["id"]))["history"]
            assert len(history) == 1 and history[0]["state"] == "completed"
            assert len(requests) == 2
            assert "TARGET_PROMPT_SENTINEL" in json.dumps(requests[0]["messages"])
            events = await runtime.events(history[0]["conversation_id"])
            start = next(event for event in events if event["kind"] == "run.started")
            assert start["member_id"] == worker["id"]
            assert start["payload"]["source"]["schedule_id"] == created["id"]
            assert events[0]["actor"] == "定时任务"
            assert any(
                event["kind"] == "tool.started" and event["payload"].get("name") == "get_local_time"
                for event in events
            )
            # 2、自动执行没有长期写工具；真实官方事件保留 run_id 和 parent_ids。
            names = {tool["function"]["name"] for tool in requests[0]["tools"]}
            assert "create_schedule" not in names and "list_schedules" in names
            native = await runtime.native_events(history[0]["conversation_id"])
            assert any(event["native"].get("run_id") for event in native)
            # 3、模拟跨库回执尚未写入的崩溃窗口；相同请求只能关联原 Run，不能再调用模型。
            with hub._schedule_store.db:
                hub._schedule_store.db.execute(
                    "UPDATE schedule_occurrences SET state='pending',run_id=NULL WHERE id=?",
                    (history[0]["id"],),
                )
            await hub._schedule_coordinator.poll()
            assert len(requests) == 2
            recovered = (await runtime.get_schedule(created["id"]))["history"][0]
            assert recovered["run_id"] == history[0]["run_id"] and recovered["state"] == "completed"
            await runtime.set_schedule_state(
                created["id"], "deleted", created["revision"], uuid4().hex
            )
        finally:
            await hub.close()


async def test_scheduled_worker_loads_its_mcp_and_latest_prompt(tmp_path: Path) -> None:
    """因为定时接单者的 MCP 与提示词可能不同，需要验证实际唤起的是目标定义而非默认助手。"""
    # 1、工具使用真实本地 MCP HTTP 服务，模型协议响应仅用于确定性核对。
    with (
        mcp_server() as (url, calls),
        model_server([
            tool_message("math_add_numbers", {"left": 19, "right": 23}),
            {"role": "assistant", "content": "42"},
        ]) as (endpoint, requests),
    ):
        hub = await schedule_hub(tmp_path, endpoint)
        try:
            runtime = hub.current
            worker = await runtime.save_member(
                {"name": "专用计算员", "prompt": "ORIGINAL_WORKER_PROMPT",
                 "mcp_servers": [{"name": "math", "url": url}]}, 0,
            )
            plan = await runtime.create_schedule(plan_values(worker["id"]), uuid4().hex)
            await runtime.save_member(
                {"id": worker["id"], "prompt": "UPDATED_TARGET_PROMPT"}, worker["revision"]
            )
            hub._schedule_coordinator._now = TestClock(plan["next_fire"] + 0.1)
            await hub._schedule_coordinator.poll()
            await wait_finished(runtime)
            await hub._schedule_coordinator.poll()
            assert calls == [{"left": 19, "right": 23}]
            assert "UPDATED_TARGET_PROMPT" in json.dumps(requests[0]["messages"])
            assert "ORIGINAL_WORKER_PROMPT" not in json.dumps(requests[0]["messages"])
            history = (await runtime.get_schedule(plan["id"]))["history"]
            assert history[0]["state"] == "completed"
            # 2、计划只保存引用，不复制 MCP 连接和系统提示词到持久日程正文。
            saved = json.dumps(hub._schedule_store.get("default", plan["id"]))
            assert url not in saved and "PROMPT" not in saved
        finally:
            await hub.close()


async def test_one_broken_plan_does_not_starve_other_due_tasks(tmp_path: Path) -> None:
    """因为一条损坏记录不能停掉全部空间调度，需要隔离单项错误并在处理正常项后报告不健康。"""
    # 1、不创建模型，正常的一次性安排因超过窗口被明确标记过期。
    hub = await schedule_hub(tmp_path)
    try:
        runtime = hub.current
        broken = await runtime.create_schedule(plan_values(), uuid4().hex)
        normal = await runtime.create_schedule({**plan_values(), "grace_seconds": 1}, uuid4().hex)
        body = dict(hub._schedule_store.get("default", broken["id"]))
        body["trigger"] = {"type": "invalid"}
        with hub._schedule_store.db:
            hub._schedule_store.db.execute(
                "UPDATE schedules SET body=? WHERE id=?", (json.dumps(body), broken["id"])
            )
        hub._schedule_coordinator._now = TestClock(normal["next_fire"] + 2)
        with pytest.raises(RuntimeError, match="部分定时任务"):
            await hub._schedule_coordinator.poll()
        assert (await runtime.get_schedule(normal["id"]))["history"][0]["state"] == "expired"
        assert not runtime.store.conversations()
    finally:
        await hub.close()


async def test_live_verification_preflight_preserves_preexisting_plans(tmp_path: Path) -> None:
    """因为真实验收的清理不能伤及用户原有安排，需要验证预检查退出后原计划仍然有效。"""
    from live_schedule_verification import verify

    # 1、只用独立数据创建未来计划，验收在读取模型配置前退出且不得取消这份原计划。
    hub = await schedule_hub(tmp_path)
    original = await hub.current.create_schedule(plan_values(), uuid4().hex)
    await hub.close()
    with pytest.raises(AssertionError, match="EXISTING_ACTIVE_SCHEDULES"):
        await verify(tmp_path, "default", "assistant", tmp_path / "evidence.json")
    restarted = await schedule_hub(tmp_path)
    try:
        saved = await restarted.current.get_schedule(original["id"])
        assert saved["state"] == "active" and saved["next_fire"] == original["next_fire"]
    finally:
        await restarted.close()


async def test_cancel_pending_and_expiry_never_call_a_model(tmp_path: Path) -> None:
    """因为暂停和取消必须阻止未来消耗，需要在真实队列中检查作废和错过窗口。"""
    # 1、没有模型配置，若取消失效就会出现阻塞或新增会话，不能伪造成功。
    hub = await schedule_hub(tmp_path)
    try:
        runtime = hub.current
        created = await runtime.create_schedule(plan_values(), uuid4().hex)
        raw = hub._schedule_store.get("default", created["id"])
        hub._schedule_store.materialize(raw, created["next_fire"] + 300, created["next_fire"] + 0.1)
        await runtime.set_schedule_state(created["id"], "deleted", 1, uuid4().hex)
        hub._schedule_coordinator._now = TestClock(created["next_fire"] + 0.1)
        await hub._schedule_coordinator.poll()
        assert (await runtime.get_schedule(created["id"]))["history"][0]["state"] == "cancelled"
        assert not runtime.store.conversations()
        # 2、过期实时任务只记错过，不在重启后补造过时的分析。
        expired = await runtime.create_schedule({**plan_values(), "grace_seconds": 10}, uuid4().hex)
        hub._schedule_coordinator._now = TestClock(expired["next_fire"] + 11)
        await hub._schedule_coordinator.poll()
        assert (await runtime.get_schedule(expired["id"]))["history"][0]["state"] == "expired"
        assert not runtime.store.conversations()
        await runtime.set_schedule_state(expired["id"], "deleted", 1, uuid4().hex)
    finally:
        await hub.close()


async def test_global_dispatch_gate_applies_to_scheduled_work(tmp_path: Path) -> None:
    """因为定时器不是桌面请求，也需要遵守四空间全局容量，需要覆盖统一闸门。"""
    # 1、容量测试只占用受理槽位，不调用模型或声称这些占位任务是实际 Agent 执行。
    hub = await schedule_hub(tmp_path)
    blockers = []
    try:
        for index in range(4):
            room = await hub.create(f"工作间{index}")
            runtime = await hub.runtime_for(room["active"]["id"])
            blocker = asyncio.create_task(asyncio.Event().wait())
            runtime._execution.active[uuid4().hex] = blocker
            blockers.append(blocker)
        with pytest.raises(DispatchBusy, match="四个"):
            await hub._dispatcher.invoke("default", "_submit_scheduled", [{}])
    finally:
        for blocker in blockers:
            blocker.cancel()
        await hub.close()


async def test_agent_uses_real_schedule_tools_to_create_and_cancel(tmp_path: Path) -> None:
    """因为只验证服务接口不能证明 Agent 工具可用，需要通过生产 Loop 完成新增和取消。"""
    # 1、响应仅规定模型协议，实际工具写入和取消均由正式配置服务完成。
    replies = [
        tool_message(
            "create_schedule",
            {
                "title": "工具验收",
                "instruction": "查看当前时间",
                "trigger": {"type": "interval", "seconds": 300},
            },
        ),
        {"role": "assistant", "content": "已创建安排"},
    ]
    with model_server(replies) as (endpoint, requests):
        hub = await schedule_hub(tmp_path, endpoint)
        try:
            runtime = hub.current
            conversation = await runtime.new_conversation()
            await hub.invoke(
                "default", "submit", [conversation["id"], "每五分钟查看时间", uuid4().hex]
            )
            await wait_finished(runtime)
            created = (await runtime.list_schedules())[0]
            assert (
                created["target_member_id"] == "assistant" and created["trigger"]["seconds"] == 300
            )
            # 2、第二轮调用专用删除工具，不能只回复已取消却留下活动计划。
            replies.extend(
                [
                    tool_message(
                        "delete_schedule",
                        {"schedule_id": created["id"], "revision": created["revision"]},
                    ),
                    {"role": "assistant", "content": "已取消安排"},
                ]
            )
            await hub.invoke(
                "default", "submit", [conversation["id"], "取消这个定时任务", uuid4().hex]
            )
            await wait_finished(runtime)
            assert not await runtime.list_schedules()
            assert (await runtime.get_schedule(created["id"]))["state"] == "deleted"
            assert len(requests) == 4
            assert any(
                event["kind"] == "tool.started"
                and event["payload"].get("name") == "delete_schedule"
                for event in await runtime.events(conversation["id"])
            )
        finally:
            await hub.close()


async def test_disabled_target_does_not_fall_back_to_assistant(tmp_path: Path) -> None:
    """因为绑定 Agent 停用后不能偷偷换人，需要验证到期仅记录阻塞而不创建模型调用。"""
    # 1、没有模型配置，本测试只验证目标失效和零会话副作用。
    hub = await schedule_hub(tmp_path)
    try:
        runtime = hub.current
        member = await runtime.save_member({"name": "专属员工"}, 0)
        created = await runtime.create_schedule(plan_values(member["id"]), uuid4().hex)
        await runtime.save_member({"id": member["id"], "enabled": False}, member["revision"])
        hub._schedule_coordinator._now = TestClock(created["next_fire"] + 0.1)
        await hub._schedule_coordinator.poll()
        assert (await runtime.get_schedule(created["id"]))["history"][0]["state"] == "blocked"
        assert not runtime.store.conversations()
        await runtime.set_schedule_state(created["id"], "deleted", 1, uuid4().hex)
    finally:
        await hub.close()
