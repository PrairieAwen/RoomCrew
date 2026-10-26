"""产品会话与持久轨迹；与框架 checkpoint 数据库分开。"""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


def now_iso() -> str:
    """因为事件排序需要一致的时间表示，需要记录带时区的 UTC 时间并让界面本地化显示。"""
    # 1、序号用于严格排序，时间用于向用户显示。
    return datetime.now(UTC).isoformat()


class SessionStore:
    def __init__(self, database: Path) -> None:
        """因为会话需要跨重启保留，需要建立本机 SQLite 表并恢复未完成运行的可见状态。"""
        # 1、连接只在运行时所属线程使用；短事务不跨模型请求持锁。
        self.connection = sqlite3.connect(database)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA busy_timeout=5000;
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, profile_ref TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id),
                request_id TEXT NOT NULL UNIQUE, input TEXT NOT NULL, status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL REFERENCES conversations(id), run_id TEXT NOT NULL,
                kind TEXT NOT NULL, actor TEXT NOT NULL, scope TEXT NOT NULL,
                payload TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS events_conversation ON events(conversation_id, seq);
            CREATE INDEX IF NOT EXISTS runs_conversation ON runs(conversation_id);
        """)
        # 2、旧版事件保留原序号，新增身份列不重写历史正文。
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(events)")}
        for column in ("agent_id", "member_id"):
            if column not in columns:
                self.connection.execute(f"ALTER TABLE events ADD COLUMN {column} TEXT")
        self.connection.commit()
        # 3、进程重启不能把旧运行显示成仍在执行，也不自动重做可能产生副作用的工具。
        interrupted = self.connection.execute(
            "SELECT * FROM runs WHERE status='running'"
        ).fetchall()
        for run in interrupted:
            self.finish(run["id"], "interrupted", {"code": "APP_RESTARTED"})

    def create_conversation(self, profile_ref: str) -> dict[str, Any]:
        """因为多个会话不能共享可变上下文，需要为新会话生成独立线程和配置绑定。"""
        # 1、固定本次模型配置引用，产品表不保存真实模型参数。
        identifier, timestamp = uuid4().hex, now_iso()
        with self.connection:
            self.connection.execute(
                "INSERT INTO conversations VALUES(?,?,?,?,?)",
                (identifier, "新会话", profile_ref, timestamp, timestamp),
            )
        return self.conversation(identifier)

    def conversation(self, identifier: str) -> dict[str, Any]:
        """因为界面传来的会话可能已失效，需要校验存在后返回安全的产品字段。"""
        # 1、参数绑定查询不接受路径或 SQL 拼接。
        row = self.connection.execute(
            "SELECT * FROM conversations WHERE id=?", (identifier,)
        ).fetchone()
        if row is None:
            raise ValueError("会话不存在")
        return dict(row)

    def conversations(self) -> list[dict[str, Any]]:
        """因为用户需要重新打开历史会话，需要按最近活动排序返回会话清单。"""
        # 1、通过最后一个运行状态显示忙碌、失败和完成，无需猜测人物动画状态。
        rows = self.connection.execute("""
            SELECT c.*, (SELECT status FROM runs r WHERE r.conversation_id=c.id
                         ORDER BY r.rowid DESC LIMIT 1) AS status
            FROM conversations c ORDER BY updated_at DESC LIMIT 200
        """).fetchall()
        return [dict(row) for row in rows]

    def run_by_request(self, request_id: str) -> dict[str, Any] | None:
        """因为前端重发不能重复产生一次任务，需要按幂等请求标识查询既有运行。"""
        # 1、把原始输入留在用户会话表中用于比较，不包含模型配置。
        row = self.connection.execute(
            "SELECT * FROM runs WHERE request_id=?", (request_id,)
        ).fetchone()
        return dict(row) if row else None

    def latest_status(self, conversation_id: str) -> str | None:
        """因为中断后的工具执行不宜盲目续跑，需要查询该会话最近一次运行状态。"""
        # 1、仅以持久记录判断能否继续会话。
        row = self.connection.execute(
            "SELECT status FROM runs WHERE conversation_id=? ORDER BY rowid DESC LIMIT 1",
            (conversation_id,),
        ).fetchone()
        return row[0] if row else None

    def begin(
        self,
        conversation_id: str,
        text: str,
        request_id: str,
        actor: str = "助手",
        agent_id: str = "agent_assistant",
        member_id: str = "assistant",
    ) -> str:
        """因为执行前必须留下用户请求，需要在同一事务中建立 Run 并写入首个轨迹事件。"""
        # 1、独立 Run 对应本轮执行，同一会话继续使用独立于其他会话的框架线程。
        run_id, timestamp = uuid4().hex, now_iso()
        with self.connection:
            self.connection.execute(
                "INSERT INTO runs VALUES(?,?,?,?,?,?)",
                (run_id, conversation_id, request_id, text, "running", timestamp),
            )
            self.connection.execute(
                "UPDATE conversations SET title=CASE WHEN title='新会话' "
                "THEN ? ELSE title END, updated_at=? WHERE id=?",
                (text[:36], timestamp, conversation_id),
            )
            self._insert(
                conversation_id, run_id, "user.message", "你", "main", {"text": text}, None, "boss"
            )
            self._insert(
                conversation_id, run_id, "run.started", actor, "main", {}, agent_id, member_id
            )
        return run_id

    def _insert(
        self,
        conversation_id: str,
        run_id: str,
        kind: str,
        actor: str,
        scope: str,
        payload: dict[str, Any],
        agent_id: str | None = None,
        member_id: str | None = None,
    ) -> int:
        """因为事件写入要复用于事务和普通追加，需要统一持久化字段及 JSON 编码。"""
        # 1、由调用方控制事务，序号在落盘后作为前端增量游标。
        cursor = self.connection.execute(
            "INSERT INTO events(conversation_id,run_id,kind,actor,"
            "scope,payload,created_at,agent_id,member_id) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                conversation_id,
                run_id,
                kind,
                actor,
                scope,
                json.dumps(payload, ensure_ascii=False),
                now_iso(),
                agent_id,
                member_id,
            ),
        )
        return int(cursor.lastrowid or 0)

    def append(
        self,
        conversation_id: str,
        run_id: str,
        kind: str,
        actor: str = "助手",
        scope: str = "main",
        *,
        agent_id: str | None = None,
        member_id: str | None = None,
        **payload: Any,
    ) -> int:
        """因为实时显示不能先于可靠记录，需要先提交结构化事件再让界面轮询读取。"""
        # 1、每次追加是短事务，不把模型输入或 SDK 原始回调整体落库。
        with self.connection:
            return self._insert(
                conversation_id, run_id, kind, actor, scope, payload, agent_id, member_id
            )

    def finish(self, run_id: str, status: str, payload: dict[str, Any]) -> None:
        """因为运行状态与终态轨迹必须一致，需要在一个产品数据库事务中完成两者更新。"""
        # 1、使用条件更新防止取消和正常结束重复产生终态。
        row = self.connection.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None or row["status"] not in {"running", "waiting_user"}:
            return
        with self.connection:
            self.connection.execute("UPDATE runs SET status=? WHERE id=?", (status, run_id))
            initial = self.connection.execute(
                "SELECT actor,agent_id,member_id FROM events WHERE run_id=? "
                "AND kind='run.started' LIMIT 1",
                (run_id,),
            ).fetchone()
            self._insert(
                row["conversation_id"],
                run_id,
                f"run.{status}",
                initial["actor"] if initial else "助手",
                "main",
                payload,
                initial["agent_id"] if initial else "agent_assistant",
                initial["member_id"] if initial else "assistant",
            )

    def events(self, conversation_id: str, after: int = 0) -> list[dict[str, Any]]:
        """因为断线和重启后仍需完整轨迹，需要通过递增游标分批重放持久事件。"""
        # 1、严格按序号读取，客户端持续翻页直到追上最新事件。
        rows = self.connection.execute(
            "SELECT * FROM events WHERE conversation_id=? AND seq>? ORDER BY seq LIMIT 100",
            (conversation_id, after),
        ).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]

    def close(self) -> None:
        """因为窗口关闭后不能遗留数据库句柄，需要显式关闭产品连接。"""
        # 1、运行任务由上层先停止，本方法只负责释放存储连接。
        self.connection.close()

    def member_events(
        self, member_id: str, conversation_id: str, after: int = 0
    ) -> list[dict[str, Any]]:
        """因为一个人物的主子任务应统一展示，需要按持久身份读取同会话的事件切片。"""
        # 1、历史版本无身份列的事件兼容归于默认助手，不更写旧轨迹正文。
        rows = self.connection.execute(
            "SELECT * FROM events WHERE conversation_id=? AND seq>? "
            "AND (member_id=? OR (member_id IS NULL AND ?='assistant')) ORDER BY seq LIMIT 100",
            (conversation_id, max(0, int(after)), member_id, member_id),
        ).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]
