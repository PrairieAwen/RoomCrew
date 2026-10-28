"""账号级元数据 SQLite 实现，秘密配置仍留在 DPAPI 文件。"""

import json
import sqlite3
from pathlib import Path
from typing import Any

AGENT_FIELDS = ("prompt", "description", "model_binding", "skills", "mcp_servers", "python_enabled")


class SqliteAccountRepository:
    def __init__(self, path: Path) -> None:
        """因为账号属性需要独立持久化，需要建立与工作日志分离的本地元数据仓库。"""
        # 1、稳定字符串 ID 与版本可用于未来云端存储，不暴露本地绝对路径。
        self._db = sqlite3.connect(path)
        self._db.row_factory = sqlite3.Row
        self._db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS members(
                id TEXT PRIMARY KEY, revision INTEGER NOT NULL, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS agent_definitions(
                id TEXT PRIMARY KEY, revision INTEGER NOT NULL, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS preferences(id INTEGER PRIMARY KEY, body TEXT NOT NULL);
        """)

    def members(self) -> list[dict[str, Any]]:
        """因为人物与 Agent 定义都按账号引用保存，需要返回完整属性供可信应用筛选。"""
        # 1、一次读取共享定义，避免每名成员再发起单独查询；成员顺序仍按原来的 rowid。
        agents = {
            row["id"]: (row["body"], row["revision"])
            for row in self._db.execute("SELECT id,revision,body FROM agent_definitions")
        }
        result = []
        for row in self._db.execute("SELECT body FROM members ORDER BY rowid"):
            member = json.loads(row["body"])
            if member.get("agent_id"):
                agent = agents.get(member["agent_id"])
                if agent:
                    # 2、逐成员恢复独立嵌套配置，避免编辑时互相污染；共享缓存仅保留序列化数据。
                    member.update(json.loads(agent[0]))
                    member["agent_revision"] = agent[1]
            result.append(member)
        return result

    def save(self, member: dict[str, Any], expected_revision: int) -> dict[str, Any]:
        """因为人物编辑和 Agent 属性更新必须一致，需要在同一事务里比较并更新版本。"""
        # 1、创建时要求版本为零，更新时拒绝过期视图。
        with self._db:
            row = self._db.execute(
                "SELECT revision FROM members WHERE id=?", (member["id"],)
            ).fetchone()
            current = int(row[0]) if row else 0
            if current != expected_revision:
                raise ValueError("成员已被修改，请刷新后再保存")
            saved = {**member, "revision": current + 1}
            agent_id = saved.get("agent_id")
            if agent_id:
                definition = {key: saved[key] for key in AGENT_FIELDS if key in saved}
                previous_agent = self._db.execute(
                    "SELECT revision,body FROM agent_definitions WHERE id=?", (agent_id,)
                ).fetchone()
                agent_revision = previous_agent["revision"] if previous_agent else 0
                if agent_revision != saved.get("agent_revision", 0):
                    raise ValueError("Agent 定义已被其他形象修改，请刷新")
                if previous_agent is None or json.loads(previous_agent["body"]) != definition:
                    agent_revision += 1
                    self._db.execute(
                        "INSERT INTO agent_definitions VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET "
                        "revision=excluded.revision,body=excluded.body",
                        (agent_id, agent_revision, json.dumps(definition, ensure_ascii=False)),
                    )
                saved["agent_revision"] = agent_revision
            body = {
                key: value
                for key, value in saved.items()
                if key not in {*AGENT_FIELDS, "agent_revision"}
            }
            self._db.execute(
                "INSERT INTO members VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET "
                "revision=excluded.revision,body=excluded.body",
                (saved["id"], saved["revision"], json.dumps(body, ensure_ascii=False)),
            )
        return saved

    def close(self) -> None:
        """因为关闭应用要释放元数据连接，需要独立关闭账号仓库。"""
        # 1、账号配置不因关闭被删除。
        self._db.close()

    def agent_definitions(self) -> list[dict[str, Any]]:
        """因为执行定义可以独立于人物管理，需要直接查询专门的 Agent 表。"""
        # 1、仅返回本空间的配置数据，不包含模型私有文件或凭据。
        return [
            {"id": row["id"], "revision": row["revision"], **json.loads(row["body"])}
            for row in self._db.execute("SELECT * FROM agent_definitions ORDER BY id")
        ]

    def save_agent(
        self, identifier: str, body: dict[str, Any], expected_revision: int
    ) -> dict[str, Any]:
        """因为管理员修改定义不能覆盖人物属性，需要只在 Agent 表内进行版本比较和更新。"""
        # 1、版本检查和写入使用同一事务，不改动引用它的任何人物行。
        with self._db:
            row = self._db.execute(
                "SELECT revision FROM agent_definitions WHERE id=?", (identifier,)
            ).fetchone()
            revision = row[0] if row else 0
            if revision != expected_revision:
                raise ValueError("Agent 配置已被修改，请刷新后保存")
            revision += 1
            self._db.execute(
                "INSERT INTO agent_definitions VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET "
                "revision=excluded.revision,body=excluded.body",
                (identifier, revision, json.dumps(body, ensure_ascii=False)),
            )
        return {"id": identifier, "revision": revision, **body}

    def preferences(self) -> dict[str, Any]:
        """因为应用重启后应保持人工选择，需要返回不含凭据的账号偏好。"""
        # 1、首次运行默认关闭表现模型调用。
        row = self._db.execute("SELECT body FROM preferences WHERE id=1").fetchone()
        return json.loads(row[0]) if row else {"narration_enabled": False}

    def set_preferences(self, values: dict[str, Any]) -> None:
        """因为旁白不能自行开启付费模型请求，需要只允许人工启用标记保存到账号配置。"""
        # 1、白名单防止把模型 Key 或 URL 混进未来云端数据。
        if set(values) - {"narration_enabled"} or not isinstance(
            values.get("narration_enabled"), bool
        ):
            raise ValueError("账号偏好字段无效")
        with self._db:
            self._db.execute(
                "INSERT INTO preferences VALUES(1,?) ON CONFLICT(id) "
                "DO UPDATE SET body=excluded.body",
                (json.dumps(values),),
            )
