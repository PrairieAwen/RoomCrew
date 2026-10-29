"""按工作空间绑定的计划管理用例；与时间检查器和实际 Agent 执行分离。"""

import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from roomcrew.scheduling.triggers import next_fire, normalize_trigger
from roomcrew.storage.schedules import ScheduleStore


class WorkspaceSchedules:
    def __init__(
        self,
        workspace_id: str,
        store: ScheduleStore,
        target: Callable[[str], Awaitable[dict[str, Any]]],
    ) -> None:
        """因为同名 Agent 可存在于不同会议室，需要在可信装配时固定空间并注入目标身份查询。"""
        # 1、空间 ID 不作为模型可填参数，仓库不挂载到任务文件视图。
        self._workspace = workspace_id
        self._store = store
        self._target = target

    @staticmethod
    def _fingerprint(operation: str, values: Any, command_id: str) -> str:
        """因为工具重放需要区分同一命令和伪复用，需要对规范请求计算稳定指纹。"""
        # 1、幂等键来自可信调用上下文，普通错误只解释格式而不回显任务内容。
        if not isinstance(command_id, str) or not 8 <= len(command_id) <= 100:
            raise ValueError("定时任务操作需要有效命令标识")
        return hashlib.sha256(
            json.dumps([operation, values], sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()

    @staticmethod
    def _public(value: dict[str, Any]) -> dict[str, Any]:
        """因为用户不应换算时间戳，需要同时返回下一次 UTC 和计划时区的可读时间。"""
        # 1、只投影计划本身，秘密和 Agent 的底层配置从不进入此记录。
        timestamp = value.get("next_fire")
        moment = datetime.fromtimestamp(timestamp, UTC) if timestamp is not None else None
        return {
            **value,
            "next_run_at": moment.isoformat() if moment else None,
            "next_run_local": moment.astimezone(ZoneInfo(value["trigger"]["timezone"])).isoformat()
            if moment
            else None,
        }

    async def list_schedules(
        self, query: str = "", include_inactive: bool = False
    ) -> list[dict[str, Any]]:
        """因为自然语言取消可能只提到标题，需要提供限定本空间的安全目录与版本信息。"""
        # 1、查询只匹配标题和任务正文，最多返回仓库的两百条有限记录。
        if not isinstance(query, str) or len(query) > 120 or type(include_inactive) is not bool:
            raise ValueError("定时任务查询参数无效")
        return [
            self._public(item)
            for item in self._store.list_for_workspace(self._workspace, include_inactive)
            if query.casefold() in (item["title"] + " " + item["instruction"]).casefold()
        ]

    async def get_schedule(self, schedule_id: str) -> dict[str, Any]:
        """因为修改和取消前要确认准确计划，需要返回当前版本及其实际触发历史。"""
        # 1、已删除的记录仍可追溯，历史查询继续校验工作空间。
        return {
            **self._public(self._store.get(self._workspace, schedule_id)),
            "history": self._store.history(self._workspace, schedule_id),
        }

    async def _definition(self, values: dict[str, Any], now: datetime) -> dict[str, Any]:
        """因为提示词和工具来自特定 Agent，需要验证当前目标后只保存稳定身份引用。"""
        # 1、任务正文必须有限且非空；跨空间字段、模型配置和任意执行回调都不接受。
        allowed = {"title", "instruction", "trigger", "target_member_id", "grace_seconds"}
        if not isinstance(values, dict) or set(values) - allowed:
            raise ValueError("定时任务字段无效，工作空间由当前会话自动绑定")
        title, instruction = values.get("title", ""), values.get("instruction", "")
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 120:
            raise ValueError("定时任务标题应为 1～120 字")
        if not isinstance(instruction, str) or not 1 <= len(instruction.strip()) <= 16000:
            raise ValueError("定时任务正文应为 1～16000 字")
        member_id = values.get("target_member_id")
        if not isinstance(member_id, str) or not member_id:
            raise ValueError("请指定本空间的接单成员")
        grace = values.get("grace_seconds", 900)
        if type(grace) is not int or not 1 <= grace <= 86400:
            raise ValueError("允许延后执行的窗口须为 1～86400 秒")
        # 2、解析时间后再加载身份；存引用不复制 MCP、Skills 或系统提示词。
        trigger = normalize_trigger(values.get("trigger"), now)
        member = await self._target(member_id)
        return {
            "title": title.strip(),
            "instruction": instruction.strip(),
            "trigger": trigger,
            "target_member_id": member_id,
            "target_agent_id": member["agent_id"],
            "target_name": member["name"],
            "grace_seconds": grace,
        }

    async def create_schedule(self, values: dict[str, Any], command_id: str) -> dict[str, Any]:
        """因为重复的工具恢复不能重复安排任务，需要先查幂等结果，再校验并保存新计划。"""
        # 1、重放优先，不因下一次执行时间随时钟变化而创建另一份安排。
        fingerprint = self._fingerprint("create", values, command_id)
        previous = self._store.replay(self._workspace, command_id, fingerprint)
        if previous is not None:
            return self._public(previous)
        now = datetime.now(UTC)
        definition = await self._definition(values, now)
        target = next_fire(definition["trigger"], now)
        if target is None:
            raise ValueError("一次性定时任务必须安排在未来")
        # 2、首次触发严格晚于创建时刻，不为验证缩短用户要求的五分钟间隔。
        saved = self._store.save(
            self._workspace,
            {
                **definition,
                "id": uuid4().hex,
                "state": "active",
                "next_fire": target.timestamp(),
                "created_at": now.timestamp(),
            },
            0,
            command_id,
            fingerprint,
        )
        return self._public(saved)

    async def update_schedule(
        self, schedule_id: str, changes: dict[str, Any], revision: int, command_id: str
    ) -> dict[str, Any]:
        """因为编辑后仅未来触发生效，需要按版本替换定义并废弃尚未受理的旧队列项。"""
        # 1、同一命令重放返回原结果；已取消的计划不能借修改复活。
        fingerprint = self._fingerprint("update", [schedule_id, changes, revision], command_id)
        replay = self._store.replay(self._workspace, command_id, fingerprint)
        if replay is not None:
            return self._public(replay)
        old = self._store.get(self._workspace, schedule_id)
        if old["state"] == "deleted" or type(revision) is not int or revision < 1:
            raise ValueError("任务已取消或版本无效")
        if (
            not isinstance(changes, dict)
            or not changes
            or set(changes)
            - {"title", "instruction", "trigger", "target_member_id", "grace_seconds"}
        ):
            raise ValueError("可修改标题、任务正文、时间、接单成员或允许延后窗口")
        now = datetime.now(UTC)
        values = {
            key: old[key]
            for key in ("title", "instruction", "trigger", "target_member_id", "grace_seconds")
        }
        definition = await self._definition({**values, **changes}, now)
        target = next_fire(definition["trigger"], now)
        if old["state"] != "paused" and target is None:
            raise ValueError("请把一次性任务修改到未来时间")
        # 2、任务正文修改也生成新版本，已经运行的快照不受影响。
        value = {
            **old,
            **definition,
            "state": "paused" if old["state"] == "paused" else "active",
            "next_fire": target.timestamp() if target and old["state"] != "paused" else None,
        }
        return self._public(
            self._store.save(self._workspace, value, revision, command_id, fingerprint)
        )

    async def set_schedule_state(
        self, schedule_id: str, state: str, revision: int, command_id: str
    ) -> dict[str, Any]:
        """因为取消计划与停止当前 Run 不同，需要只改变未来触发并保留已经受理的执行。"""
        # 1、状态变更遵守 CAS 和幂等，删除不能被 resume 隐式恢复。
        fingerprint = self._fingerprint("state", [schedule_id, state, revision], command_id)
        replay = self._store.replay(self._workspace, command_id, fingerprint)
        if replay is not None:
            return self._public(replay)
        old = self._store.get(self._workspace, schedule_id)
        if (
            state not in {"active", "paused", "deleted"}
            or type(revision) is not int
            or revision < 1
        ):
            raise ValueError("定时任务状态或版本无效")
        if old["state"] == "deleted" and state != "deleted":
            raise ValueError("已取消的任务不能恢复，请新建计划")
        target = next_fire(old["trigger"], datetime.now(UTC)) if state == "active" else None
        if state == "active":
            member = await self._target(old["target_member_id"])
            if member["agent_id"] != old["target_agent_id"] or target is None:
                raise ValueError("目标 Agent 已变化或时间已过期，请修改任务后再恢复")
        # 2、排队项由仓库同事务作废；运行中任务需用户明确调用停止接口。
        value = {**old, "state": state, "next_fire": target.timestamp() if target else None}
        return self._public(
            self._store.save(self._workspace, value, revision, command_id, fingerprint)
        )
