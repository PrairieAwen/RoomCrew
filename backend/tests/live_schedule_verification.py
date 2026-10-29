"""显式启用的真实模型五分钟验收；不复制凭据、不加速时钟，并在 finally 取消测试计划。"""

import argparse
import asyncio
import json
import msvcrt
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from roomcrew.application.options import RunOptions
from roomcrew.application.runtime import Runtime
from roomcrew.application.workspaces import WorkspaceHub
from roomcrew.contracts.limits import RunLimits
from roomcrew.platform.paths import AppPaths


def bounded_runtime(paths: AppPaths) -> Runtime:
    """因为真实模型验证也必须有花费和时长上限，需要复用正式运行时并收紧每轮额度。"""
    # 1、不替换模型或工具，只限制本次验收的真实生产执行次数和等待时长。
    return Runtime(paths, RunOptions(limits=RunLimits(model_calls=10, total_seconds=150)))


def progress(phase: str, **values: Any) -> None:
    """因为五分钟等待需要可观察进度，需要只输出公开标识和状态而不打印配置或凭据。"""
    # 1、调用方明确选择字段，原始模型请求和工具内容不进入控制台。
    print(json.dumps({"phase": phase, **values}, ensure_ascii=False), flush=True)


async def finish(runtime: Runtime, conversation_id: str) -> list[dict[str, Any]]:
    """因为 submit 只表示已受理，需要等待真实 Loop 完成并检验实际执行轨迹。"""
    # 1、额度外再设宿主等待上限；失败不伪装为完成，也不自动增加模型重试。
    async with asyncio.timeout(170):
        while runtime.active:
            await asyncio.sleep(0.2)
    if runtime.store.latest_status(conversation_id) != "completed":
        raise AssertionError("LIVE_RUN_NOT_COMPLETED")
    return await runtime.events(conversation_id)


def tool_names(events: list[dict[str, Any]]) -> list[str]:
    """因为模型口头说成功不代表实际调用，需要从正式轨迹提取真正开始的工具名称。"""
    # 1、不记录参数、结果全文和上下文，避免把无关数据写入验收报告。
    return [event["payload"].get("name", "") for event in events if event["kind"] == "tool.started"]


async def verify(root: Path, workspace: str, member: str, evidence: Path) -> None:
    """因为验收必须包含真实等待与最终取消，需要在独占用户数据目录内跑完整生命周期。"""
    # 1、使用与桌面一致的单实例锁，拒绝与已启动的应用同时访问同一套真实状态。
    paths = AppPaths.create(root)
    lock = (paths.private / "instance.lock").open("a+b")
    lock.seek(0)
    lock.write(b"0")
    lock.flush()
    lock.seek(0)
    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    hub: WorkspaceHub | None = None
    baseline: set[str] | None = None
    report: dict[str, Any] = {"clock": "real_system_clock", "interval_seconds": 300}
    owned_runs: list[tuple[Runtime, str]] = []
    try:
        hub = WorkspaceHub(paths, bounded_runtime)
        # 2、存在其他活动计划时退出，不能为了验收意外触发原有的付费工作。
        baseline = {
            row[0] for row in hub._schedule_store.db.execute("SELECT id FROM schedules")
        }
        if hub._schedule_store.db.execute(
            "SELECT 1 FROM schedules WHERE state='active' LIMIT 1"
        ).fetchone():
            raise AssertionError("EXISTING_ACTIVE_SCHEDULES")
        await hub.start()
        runtime = await hub.runtime_for(workspace)
        target = runtime.accounts.get(member)
        if not target["enabled"] or not target["agent_id"] or target.get("archived"):
            raise AssertionError("TARGET_UNAVAILABLE")
        tag = "调度真实验收_" + datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid4().hex[:6]
        conversation = await runtime.new_conversation()
        reply = await hub.invoke(
            workspace,
            "submit",
            [
                conversation["id"],
                f"请通过定时任务工具只创建一个新计划，标题必须是 {tag}。"
                f"绑定当前工作空间的成员 {member}，每5分钟执行一次（interval seconds=300，"
                "不要设置 start_at），首次在创建后5分钟。任务正文："
                "只调用 get_local_time 查看并用一句话报告当时的实际时间；不联网、不写文件、"
                "不委派、不创建其他计划。本次只安排未来任务，不要等待或执行该任务。",
                uuid4().hex,
                member,
            ],
        )
        owned_runs.append((runtime, reply["run_id"]))
        events = await finish(runtime, conversation["id"])
        assert "create_schedule" in tool_names(events), "NO_REAL_CREATE_TOOL"
        plans = await runtime.list_schedules(tag)
        assert len(plans) == 1, "UNEXPECTED_TEST_PLAN_COUNT"
        plan = plans[0]
        assert plan["trigger"]["type"] == "interval" and plan["trigger"]["seconds"] == 300
        assert plan["workspace_id"] == workspace and plan["target_member_id"] == member
        assert plan["target_agent_id"] == target["agent_id"]
        assert 299 <= plan["next_fire"] - plan["created_at"] <= 301
        report.update(
            schedule_id=plan["id"], workspace_id=workspace, member_id=member,
            agent_id=target["agent_id"], created_at=plan["created_at"],
            scheduled_for=plan["next_fire"], create_tools=tool_names(events),
            created_conversation_id=conversation["id"],
        )
        progress("waiting_real_five_minutes", **report)
        # 3、保持生产定时器与系统时间运行；不修改 next_fire、触发间隔或数据库来提前执行。
        async with asyncio.timeout(480):
            while True:
                current = await runtime.get_schedule(plan["id"])
                history = current["history"]
                if history and history[0]["state"] == "completed" and not runtime.active:
                    occurrence = history[0]
                    break
                if history and history[0]["state"] in {
                    "failed", "blocked", "expired", "interrupted", "cancelled", "waiting_user"
                }:
                    raise AssertionError("SCHEDULE_OCCURRENCE_DID_NOT_COMPLETE")
                await asyncio.sleep(0.5)
        events = await runtime.events(occurrence["conversation_id"])
        assert "get_local_time" in tool_names(events), "NO_REAL_TIME_TOOL"
        start = next(event for event in events if event["kind"] == "run.started")
        assert start["member_id"] == member
        assert start["payload"]["source"]["schedule_id"] == plan["id"]
        completed_at = datetime.now(UTC).isoformat()
        report.update(
            occurrence_id=occurrence["id"], occurrence_state=occurrence["state"],
            scheduled_tools=tool_names(events), completed_at=completed_at,
        )
        progress("scheduled_agent_completed", **report)
        # 4、取消也通过真实 Agent 工具执行；finally 再以确定性服务收尾，防止模型遗漏。
        reply = await hub.invoke(
            workspace, "submit",
            [conversation["id"], f"刚才的测试已经结束，请用 delete_schedule 取消标题为 {tag}、"
             f"ID 为 {plan['id']} 的计划，只取消这一个，确保不再定时唤起。", uuid4().hex, member],
        )
        owned_runs.append((runtime, reply["run_id"]))
        events = await finish(runtime, conversation["id"])
        assert "delete_schedule" in tool_names(events), "NO_REAL_DELETE_TOOL"
        cancelled = await runtime.get_schedule(plan["id"])
        assert cancelled["state"] == "deleted" and cancelled["next_fire"] is None
        await hub._schedule_coordinator.poll()
        assert len((await runtime.get_schedule(plan["id"]))["history"]) == 1
        report.update(cancel_state="deleted", cancel_tools=tool_names(events), passed=True)
    finally:
        # 5、任何断言失败也只清理本次新增计划；不取消用户以前的安排或任务。
        if hub is not None:
            for scheduled in hub._schedule_store.db.execute(
                "SELECT id,workspace_id FROM schedules"
            ).fetchall():
                if baseline is None or scheduled["id"] in baseline:
                    continue
                state = hub._schedule_store.get(scheduled["workspace_id"], scheduled["id"])
                if state["state"] != "deleted":
                    runtime = await hub.runtime_for(scheduled["workspace_id"])
                    await runtime.set_schedule_state(
                        state["id"], "deleted", state["revision"], uuid4().hex
                    )
            for runtime, run_id in owned_runs:
                if run_id in runtime.active:
                    await runtime.stop(run_id)
            report["remaining_active_plans"] = hub._schedule_store.db.execute(
                "SELECT count(*) FROM schedules WHERE state='active'"
            ).fetchone()[0]
            await hub.close()
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        lock.close()
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        progress("cleanup_complete", **report)


def main() -> None:
    """因为真实验收会消耗用户模型额度，需要显式标志和目录才能运行，且不被 pytest 自动执行。"""
    # 1、没有授权标志时不打开真实配置，不接受以普通单元测试掩盖付费调用。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-live", action="store_true", required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--workspace", default="default")
    parser.add_argument("--member", default="assistant")
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(verify(args.data_dir.resolve(), args.workspace, args.member, args.evidence))


if __name__ == "__main__":
    main()
