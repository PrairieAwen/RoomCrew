"""计划与触发记录 SQLite 仓库；不加载 Agent、不创建模型、不实现时间规则。"""

import json
import sqlite3
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5


class ScheduleStore:
    def __init__(self, path: Path) -> None:
        """因为定时安排需要跨空间统一扫描和跨重启恢复，需要建立独立产品库及到期索引。"""
        # 1、只保存公开任务和绑定 ID；一次触发唯一，SQLite 事务不跨网络请求。
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA busy_timeout=5000;
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS schedules(
                id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,revision INTEGER NOT NULL,
                state TEXT NOT NULL,next_fire REAL,body TEXT NOT NULL,created_at REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS schedule_due ON schedules(state,next_fire);
            CREATE INDEX IF NOT EXISTS schedule_workspace ON schedules(workspace_id,state);
            CREATE TABLE IF NOT EXISTS schedule_occurrences(
                id TEXT PRIMARY KEY,schedule_id TEXT NOT NULL REFERENCES schedules(id),
                workspace_id TEXT NOT NULL,schedule_revision INTEGER NOT NULL,
                scheduled_for REAL NOT NULL,deadline REAL NOT NULL,state TEXT NOT NULL,
                body TEXT NOT NULL,run_id TEXT,error TEXT,UNIQUE(schedule_id,scheduled_for));
            CREATE INDEX IF NOT EXISTS occurrence_state ON schedule_occurrences(state);
            CREATE TABLE IF NOT EXISTS schedule_commands(
                workspace_id TEXT NOT NULL,id TEXT NOT NULL,fingerprint TEXT NOT NULL,
                result TEXT NOT NULL,PRIMARY KEY(workspace_id,id));
        """)

    @staticmethod
    def _schedule(row: sqlite3.Row) -> dict[str, Any]:
        """因为索引列与正文有不同职责，需要统一返回以索引身份和版本为准的计划记录。"""
        # 1、正文不能覆盖可信 ID、空间、状态或时间列。
        return {
            **json.loads(row["body"]),
            **{
                key: row[key]
                for key in ("id", "workspace_id", "revision", "state", "next_fire", "created_at")
            },
        }

    def get(self, workspace_id: str, identifier: str) -> dict[str, Any]:
        """因为知道计划 ID 也不能越过空间边界，需要把空间条件加入每次读取。"""
        # 1、未知和跨空间使用同一错误，避免泄露其他会议室的安排。
        row = self.db.execute(
            "SELECT * FROM schedules WHERE workspace_id=? AND id=?", (workspace_id, identifier)
        ).fetchone()
        if row is None:
            raise ValueError("当前工作空间没有这个定时任务")
        return self._schedule(row)

    def list_for_workspace(
        self, workspace_id: str, include_inactive: bool = False
    ) -> list[dict[str, Any]]:
        """因为用户和 Agent 都需要查询本空间安排，需要有界返回计划而不扫描任务正文文件。"""
        # 1、默认展示活动和已暂停安排，历史一次性与已删除记录可显式查看。
        rows = self.db.execute(
            "SELECT * FROM schedules WHERE workspace_id=? "
            "AND (? OR state IN ('active','paused')) "
            "ORDER BY CASE WHEN state IN ('active','paused') THEN 0 ELSE 1 END,"
            "created_at DESC LIMIT 200",
            (workspace_id, include_inactive),
        ).fetchall()
        return [self._schedule(row) for row in rows]

    def replay(self, workspace_id: str, command_id: str, fingerprint: str) -> dict[str, Any] | None:
        """因为工具恢复时会重放同一请求，需要返回原结果并拒绝复用命令标识修改其他内容。"""
        # 1、幂等记录与计划修改在同一事务提交，不依赖模型是否记得之前的调用。
        row = self.db.execute(
            "SELECT * FROM schedule_commands WHERE workspace_id=? AND id=?",
            (workspace_id, command_id),
        ).fetchone()
        if row is None:
            return None
        if row["fingerprint"] != fingerprint:
            raise ValueError("定时任务命令标识已用于其他操作")
        return dict(json.loads(row["result"]))

    def save(
        self,
        workspace_id: str,
        value: dict[str, Any],
        expected_revision: int,
        command_id: str,
        fingerprint: str,
    ) -> dict[str, Any]:
        """因为计划修改可能与到期检查同时发生，需要在短事务内做版本校验和排队取消。"""
        # 1、先处理完全相同的重放，再校验版本；同一空间最多保留六十四个未删除计划。
        with self.db:
            previous_reply = self.replay(workspace_id, command_id, fingerprint)
            if previous_reply is not None:
                return previous_reply
            old = self.db.execute("SELECT * FROM schedules WHERE id=?", (value["id"],)).fetchone()
            if old is not None and old["workspace_id"] != workspace_id:
                raise ValueError("当前工作空间没有这个定时任务")
            if (old["revision"] if old else 0) != expected_revision:
                raise ValueError("定时任务已被修改，请重新查询后再操作")
            if (
                old is None
                and self.db.execute(
                    "SELECT count(*) FROM schedules WHERE workspace_id=? AND state!='deleted'",
                    (workspace_id,),
                ).fetchone()[0]
                >= 64
            ):
                raise ValueError("一个工作空间最多保存 64 个未删除定时任务")
            result = {**value, "workspace_id": workspace_id, "revision": expected_revision + 1}
            self.db.execute(
                "INSERT INTO schedules VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,"
                "state=excluded.state,next_fire=excluded.next_fire,body=excluded.body",
                (
                    result["id"],
                    workspace_id,
                    result["revision"],
                    result["state"],
                    result["next_fire"],
                    json.dumps(result, ensure_ascii=False),
                    result["created_at"],
                ),
            )
            # 2、编辑、暂停与删除都使尚未受理的旧版本失效，已受理 Run 继续保留真实状态。
            self.db.execute(
                "UPDATE schedule_occurrences SET state='cancelled',error='PLAN_CHANGED' "
                "WHERE schedule_id=? AND state='pending'",
                (result["id"],),
            )
            self.db.execute(
                "INSERT INTO schedule_commands VALUES(?,?,?,?)",
                (workspace_id, command_id, fingerprint, json.dumps(result, ensure_ascii=False)),
            )
            return result

    def due(self, now: float) -> list[dict[str, Any]]:
        """因为时间检查器不应初始化所有会议室，需要通过索引只取真正到期的计划。"""
        # 1、每次最多物化一百个到期项，下一次检查继续处理剩余项。
        rows = self.db.execute(
            "SELECT * FROM schedules WHERE state='active' AND next_fire<=? "
            "ORDER BY next_fire LIMIT 100",
            (now,),
        ).fetchall()
        return [self._schedule(row) for row in rows]

    def materialize(self, schedule: dict[str, Any], next_fire: float | None, now: float) -> None:
        """因为一次到期不能重复派发，需要原子生成唯一触发快照并推进下一时间。"""
        # 1、再次验证当前版本和待触发时间；旧回调不能复活被修改或取消的计划。
        with self.db:
            current = self.get(schedule["workspace_id"], schedule["id"])
            if (current["revision"], current["state"], current["next_fire"]) != (
                schedule["revision"],
                "active",
                schedule["next_fire"],
            ):
                return
            slot = float(schedule["next_fire"])
            identifier = uuid5(NAMESPACE_URL, f"roomcrew:schedule:{schedule['id']}:{slot:.6f}").hex
            overlap = self.db.execute(
                "SELECT 1 FROM schedule_occurrences WHERE schedule_id=? "
                "AND state IN ('pending','running','waiting_user') LIMIT 1",
                (schedule["id"],),
            ).fetchone()
            deadline = slot + schedule["grace_seconds"]
            state = "expired" if now > deadline else "skipped_overlap" if overlap else "pending"
            body = {**schedule, "occurrence_id": identifier, "conversation_id": identifier}
            self.db.execute(
                "INSERT OR IGNORE INTO schedule_occurrences VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    identifier,
                    schedule["id"],
                    schedule["workspace_id"],
                    schedule["revision"],
                    slot,
                    deadline,
                    state,
                    json.dumps(body, ensure_ascii=False),
                    None,
                    None,
                ),
            )
            self.db.execute(
                "UPDATE schedules SET next_fire=?,state=? WHERE id=?",
                (next_fire, "active" if next_fire is not None else "finished", schedule["id"]),
            )

    @staticmethod
    def _occurrence(row: sqlite3.Row) -> dict[str, Any]:
        """因为触发时的任务正文必须固定，需要把不可变快照与当前运行状态组合返回。"""
        # 1、状态列覆盖快照中的计划状态，不把新的计划正文混入旧触发。
        return {**json.loads(row["body"]), **dict(row), "body": None}

    def occurrences(self, states: tuple[str, ...]) -> list[dict[str, Any]]:
        """因为持久队列需要恢复未结束触发，需要只返回已知状态中的有限记录。"""
        # 1、状态由可信服务传入并参数绑定，查询不拼接外部 SQL。
        placeholders = ",".join("?" for _ in states)
        ordering = (
            "ROW_NUMBER() OVER (PARTITION BY workspace_id ORDER BY scheduled_for),scheduled_for"
            if states == ("pending",)
            else "scheduled_for"
        )
        rows = self.db.execute(
            f"SELECT * FROM schedule_occurrences WHERE state IN ({placeholders}) "
            f"ORDER BY {ordering} LIMIT 100",
            states,
        ).fetchall()
        return [self._occurrence(row) for row in rows]

    def history(self, workspace_id: str, schedule_id: str) -> list[dict[str, Any]]:
        """因为取消后仍需追溯报告，需要按空间和计划返回最近二十次真实执行状态。"""
        # 1、先校验归属，返回引用与状态，不广播整个任务快照或其他空间内容。
        self.get(workspace_id, schedule_id)
        rows = self.db.execute(
            "SELECT id,scheduled_for,state,run_id,error FROM schedule_occurrences "
            "WHERE workspace_id=? AND schedule_id=? ORDER BY scheduled_for DESC LIMIT 20",
            (workspace_id, schedule_id),
        ).fetchall()
        return [{**dict(row), "conversation_id": row["id"]} for row in rows]

    def valid(self, occurrence: dict[str, Any]) -> bool:
        """因为打开空间可能让出事件循环，需要在真正受理前再次确认计划仍有效。"""
        # 1、一次性计划物化后为 finished，仍允许其唯一排队项受理。
        plan = self.get(occurrence["workspace_id"], occurrence["schedule_id"])
        row = self.db.execute(
            "SELECT state FROM schedule_occurrences WHERE id=?", (occurrence["id"],)
        ).fetchone()
        return (
            row is not None
            and row[0] == "pending"
            and plan["state"] in {"active", "finished"}
            and plan["revision"] == occurrence["schedule_revision"]
        )

    def mark(
        self, identifier: str, state: str, run_id: str | None = None, error: str | None = None
    ) -> None:
        """因为状态来自真实执行回执，需要记录结果并保护已经取消的排队项不被迟到回调覆盖。"""
        # 1、只更新仍未终止的记录；取消和历史终态保持可追溯。
        with self.db:
            self.db.execute(
                "UPDATE schedule_occurrences SET state=?,run_id=COALESCE(?,run_id),error=? "
                "WHERE id=? AND state IN ('pending','running','waiting_user')",
                (state, run_id, error, identifier),
            )

    def close(self) -> None:
        """因为 SQLite 连接属于宿主事件循环，需要在检查器和执行器结束后释放连接。"""
        # 1、关闭不会删除计划或执行历史。
        self.db.close()
