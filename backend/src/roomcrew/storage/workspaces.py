"""工作空间目录：一空间一会议室，不存 Agent 上下文或模型秘密。"""

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


class WorkspaceRepository:
    def __init__(self, path: Path) -> None:
        """因为多个会议室需要跨重启保留，需要独立目录数据库管理空间与一对一房间标识。"""
        # 1、默认空间映射旧数据目录，不迁移原会话或用户文件。
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS workspaces(
                id TEXT PRIMARY KEY,name TEXT NOT NULL,
                room_id TEXT NOT NULL UNIQUE,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY,active_id TEXT NOT NULL);
        """)
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO workspaces VALUES(?,?,?,?)",
                ("default", "默认工作空间", "room_default", datetime.now(UTC).isoformat()),
            )
            self.db.execute("INSERT OR IGNORE INTO settings VALUES(1,'default')")

    def list(self) -> list[dict[str, Any]]:
        """因为左侧需要稳定展示会议室目录，需要只返回名称、ID 与创建时间。"""
        # 1、创建顺序保持稳定，不读取空间里的消息或工具正文。
        return [dict(row) for row in self.db.execute("SELECT * FROM workspaces ORDER BY rowid")]

    def get(self, identifier: str) -> dict[str, Any]:
        """因为页面传入的空间 ID 不能变成任意路径，需要先在目录白名单中精确查询。"""
        # 1、参数绑定防止 SQL 拼接；不存在的标识不能创建数据目录。
        row = self.db.execute("SELECT * FROM workspaces WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise ValueError("工作空间不存在")
        return dict(row)

    def create(self, name: str) -> dict[str, Any]:
        """因为创建工作空间必须同步产生会议室，需要在同一事务写入唯一对应关系。"""
        # 1、显示名称不参与文件路径，空间目录始终使用随机 ID。
        title = self._name(name)
        if len(self.list()) >= 16:
            raise ValueError("当前最多保留 16 个工作空间")
        identifier = uuid4().hex
        with self.db:
            self.db.execute(
                "INSERT INTO workspaces VALUES(?,?,?,?)",
                (identifier, title, "room_" + identifier, datetime.now(UTC).isoformat()),
            )
        return self.get(identifier)

    def rename(self, identifier: str, name: str) -> dict[str, Any]:
        """因为会议室名称应跟随工作空间，需要只修改显示名称而保留房间和运行身份。"""
        # 1、重命名不搬动文件、改变作用域或重建 Agent。
        self.get(identifier)
        title = self._name(name)
        with self.db:
            self.db.execute("UPDATE workspaces SET name=? WHERE id=?", (title, identifier))
        return self.get(identifier)

    def active(self) -> str:
        """因为重启要回到用户最近查看的房间，需要读取已保存的活动空间标识。"""
        # 1、目录仍会再次验证引用，避免坏设置变成路径。
        identifier = self.db.execute("SELECT active_id FROM settings WHERE id=1").fetchone()[0]
        self.get(identifier)
        return str(identifier)

    def select(self, identifier: str) -> None:
        """因为切换会议室需要跨重启记住选择，需要只更新目录设置而不切换正在执行的任务。"""
        # 1、运行实例由应用层按独立空间维护，不在此迁移上下文。
        self.get(identifier)
        with self.db:
            self.db.execute("UPDATE settings SET active_id=? WHERE id=1", (identifier,))

    def _name(self, name: str) -> str:
        """因为名称属于人工显示字段，需要拒绝空值、控制字符与过长输入。"""
        # 1、允许普通中英文和标点，界面仍使用纯文本节点。
        if (
            not isinstance(name, str)
            or not 1 <= len(name.strip()) <= 60
            or any(ord(char) < 32 for char in name)
        ):
            raise ValueError("工作空间名称应为 1—60 字，不能包含控制字符")
        return name.strip()

    def close(self) -> None:
        """因为目录使用独立连接，需要在所有空间关闭后释放它。"""
        # 1、关闭目录不删除空间或业务数据。
        self.db.close()


def offline_workspace_status(database: Path) -> dict[str, Any]:
    """因为未打开空间也可能等待人工，需要只读查询待办数量而不启动执行器或自动重放任务。"""
    # 1、不存在的新空间视为尚未打开；历史运行绝不当成当前进程仍在执行。
    if not database.is_file():
        return {"active_runs": 0, "pending_count": 0, "status": "未打开"}
    try:
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=0.1)) as db:
            count = db.execute(
                "SELECT count(*) FROM human_requests h JOIN runs r ON r.id=h.run_id "
                "WHERE h.status='pending' AND r.status='waiting_user'"
            ).fetchone()[0]
            return {
                "active_runs": 0,
                "pending_count": count,
                "status": "待答复" if count else "未打开",
            }
    except sqlite3.Error:
        return {"active_runs": 0, "pending_count": 0, "status": "需要检查"}
