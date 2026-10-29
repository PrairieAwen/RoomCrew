"""会话所有者、静默时间、封存生命周期与持久默认聊天指针。"""

import sqlite3
import time
from datetime import UTC, datetime
from typing import Any


class ConversationMemory:
    def __init__(self, db: sqlite3.Connection) -> None:
        """因为续聊与归档需和受理保持一致，需要在原会话库保存元数据而不改 checkpoint。"""
        # 1、旧会话按首次接单者与最后事件迁移，原事件、会话 ID 和文件目录不变。
        self.db = db
        db.executescript("""
            CREATE TABLE IF NOT EXISTS conversation_memory(
                conversation_id TEXT PRIMARY KEY REFERENCES conversations(id),
                member_id TEXT NOT NULL DEFAULT '',agent_id TEXT NOT NULL DEFAULT '',
                lifecycle TEXT NOT NULL DEFAULT 'open',activity REAL NOT NULL,
                predecessor_id TEXT,inherit_memory INTEGER NOT NULL DEFAULT 1);
            CREATE INDEX IF NOT EXISTS conversation_idle ON conversation_memory(lifecycle,activity);
            CREATE TABLE IF NOT EXISTS member_channels(
                member_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL REFERENCES conversations(id));
            INSERT OR IGNORE INTO conversation_memory(conversation_id,member_id,agent_id,activity)
                SELECT c.id,COALESCE((SELECT member_id FROM events e WHERE e.conversation_id=c.id
                    AND kind='run.started' AND scope='main' ORDER BY seq LIMIT 1),''),
                    COALESCE((SELECT agent_id FROM events e WHERE e.conversation_id=c.id
                    AND kind='run.started' AND scope='main' ORDER BY seq LIMIT 1),''),
                    COALESCE(unixepoch((SELECT MAX(created_at) FROM events e
                        WHERE e.conversation_id=c.id)),unixepoch(c.updated_at))
                FROM conversations c;
        """)

    def register(
        self, identifier: str, predecessor: str | None = None, inherit: bool = True
    ) -> None:
        """因为新会话可能还没有消息，需要登记来源关系但不因打开人物而发送或生成摘要。"""
        # 1、由调用方控制事务，重复登记不会覆盖已封存会话。
        self.db.execute(
            "INSERT OR IGNORE INTO conversation_memory(conversation_id,activity,predecessor_id,"
            "inherit_memory) VALUES(?,?,?,?)",
            (identifier, time.time(), predecessor, int(inherit)),
        )

    def get(self, identifier: str) -> dict[str, Any]:
        """因为受理需要判断会话是否已封存，需要读取真实生命周期而非根据摘要状态猜测。"""
        # 1、未知会话不能通过本接口凭空注册或扩张文件视图。
        row = self.db.execute(
            "SELECT * FROM conversation_memory WHERE conversation_id=?", (identifier,)
        ).fetchone()
        if row is None:
            raise ValueError("会话元数据不存在")
        return dict(row)

    def bind(self, identifier: str, member_id: str, agent_id: str, channel: bool = True) -> None:
        """因为旧会话允许多个独立成员线程，需要保留首次入口身份并登记各自聊天引用。"""
        # 1、旧多入口会话不重写所有者；新无感入口按成员分开，SDK 仍按成员隔离线程。
        previous = self.get(identifier)
        if previous["lifecycle"] != "open":
            raise ValueError("该会话已进入档案，请通过继续对话创建延续线程")
        if not previous["member_id"] or previous["member_id"] == member_id:
            self.db.execute(
                "UPDATE conversation_memory SET member_id=?,agent_id=? WHERE conversation_id=?",
                (member_id, agent_id, identifier),
            )
        if channel:
            self.db.execute(
                "INSERT INTO member_channels VALUES(?,?) ON CONFLICT(member_id) "
                "DO UPDATE SET conversation_id=excluded.conversation_id",
                (member_id, identifier),
            )

    def touch(self, identifier: str) -> None:
        """因为一小时静默应从最后一次真实写入起算，需要在每次公开或原生事件提交时更新时间。"""
        # 1、与调用方的事件事务共提交，UI 读取和轮询不会延长静默窗口。
        self.db.execute(
            "UPDATE conversation_memory SET activity=? WHERE conversation_id=?",
            (time.time(), identifier),
        )

    def preferred(self, member_id: str) -> dict[str, Any] | None:
        """因为用户重启后仍应回到同一员工的聊天，需要读取持久指针并兼容旧历史。"""
        # 1、归档会话仍返回其引用，真正发送时由应用创建延续线程；不创建空会话。
        row = self.db.execute(
            "SELECT c.* FROM conversations c JOIN member_channels p ON p.conversation_id=c.id "
            "WHERE p.member_id=?",
            (member_id,),
        ).fetchone()
        if row is None:
            row = self.db.execute(
                "SELECT c.* FROM conversations c JOIN conversation_memory m "
                "ON m.conversation_id=c.id WHERE m.member_id=? "
                "AND EXISTS(SELECT 1 FROM events e WHERE e.conversation_id=c.id "
                "AND kind='user.message' AND actor!='定时任务') ORDER BY m.activity DESC LIMIT 1",
                (member_id,),
            ).fetchone()
        return {**dict(row), **self.get(row["id"])} if row else None

    def candidates(self, now: float, quiet_seconds: float = 3600) -> list[dict[str, Any]]:
        """因为运行或等待人工的会话不能归档，需要仅筛选真实静默一小时的终止会话。"""
        # 1、sealing 状态支持恢复文件阶段崩溃；空会话不产生无意义档案。
        return self._sources(
            "(m.lifecycle='open' AND m.activity<=? OR m.lifecycle='sealing')",
            (now - quiet_seconds,),
        )

    def source(self, identifier: str) -> dict[str, Any]:
        """因为用户可主动提前归档，需要读取指定已完成会话的同一份高水位和身份记录。"""
        # 1、运行或等待人工仍被排除，不允许强制截断正在执行的会话。
        rows = self._sources("c.id=?", (identifier,))
        if not rows:
            raise ValueError("会话不存在、没有工作记录或仍在执行/等待人工答复")
        return rows[0]

    def _sources(self, where: str, values: tuple[Any, ...]) -> list[dict[str, Any]]:
        """因为自动与人工归档需保持相同数据边界，需要集中读取身份、高水位和可封存状态。"""
        # 1、条件只来自本模块具名入口，所有外部值使用参数绑定。
        rows = self.db.execute(
            "SELECT c.*,m.*,(SELECT MAX(seq) FROM events e "
            "WHERE e.conversation_id=c.id) event_seq,COALESCE((SELECT MAX(seq) "
            "FROM native_events n WHERE n.conversation_id=c.id),0) native_seq "
            "FROM conversations c JOIN conversation_memory m ON m.conversation_id=c.id WHERE "
            + where + " "
            "AND EXISTS(SELECT 1 FROM runs r WHERE r.conversation_id=c.id) "
            "AND NOT EXISTS(SELECT 1 FROM runs r WHERE r.conversation_id=c.id "
            "AND r.status IN ('running','waiting_user')) ORDER BY m.activity LIMIT 16",
            values,
        ).fetchall()
        return [
            {**dict(row), "last_at": datetime.fromtimestamp(row["activity"], UTC).isoformat()}
            for row in rows
        ]

    def seal(self, identifier: str, activity: float) -> bool:
        """因为归档扫描与新消息会竞争，需要用静默版本和活动状态做原子封存。"""
        # 1、检查后有新写入或 Run 已受理则封存失败，不让后台截断前台工作。
        with self.db:
            cursor = self.db.execute(
                "UPDATE conversation_memory SET lifecycle='sealing' WHERE conversation_id=? "
                "AND activity=? AND lifecycle IN ('open','sealing') "
                "AND NOT EXISTS(SELECT 1 FROM runs WHERE conversation_id=? "
                "AND status IN ('running','waiting_user'))",
                (identifier, activity, identifier),
            )
        return cursor.rowcount == 1

    def archived(self, identifier: str) -> None:
        """因为原文可靠保存后才可视作已归档，需要显式推进生命周期而不删除原库。"""
        # 1、摘要仍可异步生成；用户新对话无需等待其完成。
        with self.db:
            self.db.execute(
                "UPDATE conversation_memory SET lifecycle='archived' WHERE conversation_id=? "
                "AND lifecycle='sealing'",
                (identifier,),
            )
