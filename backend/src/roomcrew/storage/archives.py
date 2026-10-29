"""独立档案 SQLite：原文页、摘要作业、文本索引和用户共享规则。"""

import json
import sqlite3
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5


class ArchiveRepository:
    def __init__(self, path: Path) -> None:
        """因为档案应独立于会话与 checkpoint 演进，需要建立轻量产品库并保存可重建索引。"""
        # 1、只有宿主线程写入，短事务不跨摘要模型或本地推理等待。
        self.path = path
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA busy_timeout=5000;
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS archives(
                id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,conversation_id TEXT NOT NULL,
                member_id TEXT NOT NULL,agent_id TEXT NOT NULL,title TEXT NOT NULL,
                started_at TEXT NOT NULL,ended_at TEXT NOT NULL,event_seq INTEGER NOT NULL,
                native_seq INTEGER NOT NULL,state TEXT NOT NULL,summary TEXT NOT NULL DEFAULT '',
                error TEXT,attempts INTEGER NOT NULL DEFAULT 0,retry_at REAL NOT NULL DEFAULT 0,
                manifest TEXT NOT NULL DEFAULT '{}',UNIQUE(workspace_id,conversation_id));
            CREATE INDEX IF NOT EXISTS archives_scope ON archives(workspace_id,member_id,ended_at);
            CREATE INDEX IF NOT EXISTS archives_jobs ON archives(state,retry_at);
            CREATE TABLE IF NOT EXISTS archive_messages(
                archive_id TEXT NOT NULL REFERENCES archives(id),position INTEGER NOT NULL,
                body TEXT NOT NULL,PRIMARY KEY(archive_id,position));
            CREATE TABLE IF NOT EXISTS archive_parts(
                archive_id TEXT NOT NULL REFERENCES archives(id),position INTEGER NOT NULL,
                body TEXT NOT NULL,result TEXT,PRIMARY KEY(archive_id,position));
            CREATE TABLE IF NOT EXISTS archive_documents(
                id INTEGER PRIMARY KEY,archive_id TEXT NOT NULL REFERENCES archives(id),
                workspace_id TEXT NOT NULL,member_id TEXT NOT NULL,agent_id TEXT NOT NULL,
                at TEXT NOT NULL,kind TEXT NOT NULL,text TEXT NOT NULL,
                first_position INTEGER NOT NULL,last_position INTEGER NOT NULL,
                vector BLOB,model TEXT);
            CREATE INDEX IF NOT EXISTS archive_document_scope
                ON archive_documents(workspace_id,member_id,at);
            CREATE INDEX IF NOT EXISTS archive_document_pending ON archive_documents(model,id);
            CREATE INDEX IF NOT EXISTS archive_document_owner
                ON archive_documents(archive_id,model);
            CREATE VIRTUAL TABLE IF NOT EXISTS archive_fts USING fts5(
                text,content='archive_documents',content_rowid='id',tokenize='trigram');
            CREATE TRIGGER IF NOT EXISTS archive_fts_insert AFTER INSERT ON archive_documents BEGIN
                INSERT INTO archive_fts(rowid,text) VALUES(new.id,new.text); END;
            CREATE TABLE IF NOT EXISTS archive_shares(
                target_workspace TEXT NOT NULL,source_workspace TEXT NOT NULL,
                PRIMARY KEY(target_workspace,source_workspace));
            CREATE TABLE IF NOT EXISTS archive_model_usage(
                hour INTEGER PRIMARY KEY,calls INTEGER NOT NULL);
        """)

    @staticmethod
    def identifier(workspace_id: str, conversation_id: str) -> str:
        """因为重启不能为同一封存会话生成重复档案，需要由空间和会话计算稳定标识。"""
        # 1、不同空间中相同会话标识也不会共用一份档案。
        return uuid5(NAMESPACE_URL, f"roomcrew:archive:{workspace_id}:{conversation_id}").hex

    def begin(self, workspace_id: str, source: dict[str, Any]) -> dict[str, Any]:
        """因为文件写入与数据库不能跨介质事务，需要先持久化待快照作业以供崩溃恢复。"""
        # 1、只登记公开身份与源高水位，不保存模型配置或可变运行对象。
        identifier = self.identifier(workspace_id, source["id"])
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO archives(id,workspace_id,conversation_id,member_id,"
                "agent_id,title,started_at,ended_at,event_seq,native_seq,state) "
                "VALUES(?,?,?,?,?,?,?,?,?,?, 'snapshot')",
                (
                    identifier,
                    workspace_id,
                    source["id"],
                    source["member_id"],
                    source["agent_id"],
                    source["title"],
                    source["created_at"],
                    source["last_at"],
                    source["event_seq"],
                    source["native_seq"],
                ),
            )
        return self.get(identifier)

    def get(self, identifier: str) -> dict[str, Any]:
        """因为读取原文前需要获得可信归属，需要只按生成的档案 ID 查询普通元数据。"""
        # 1、权限由外层服务使用 workspace_id 进一步检查，不接受文件路径。
        row = self.db.execute("SELECT * FROM archives WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise ValueError("档案不存在或尚未生成")
        return dict(row)

    def jobs(self, now: float) -> list[dict[str, Any]]:
        """因为归档需断点恢复，需要取出少量已到重试时间的作业而不是每次重跑全部历史。"""
        # 1、失败三次后保留原文等待用户明确重试，防止后台无限消耗模型额度。
        return [
            dict(row)
            for row in self.db.execute(
                "SELECT * FROM archives WHERE state IN "
                "('snapshot','indexing_raw','summarizing','indexing') "
                "AND retry_at<=? AND attempts<3 ORDER BY CASE state WHEN 'snapshot' THEN 0 "
                "WHEN 'indexing_raw' THEN 1 WHEN 'indexing' THEN 2 ELSE 3 END,"
                "retry_at,ended_at LIMIT 8",
                (now,),
            )
        ]

    def snapshot(
        self,
        identifier: str,
        messages: list[dict[str, Any]],
        parts: list[dict[str, Any]],
        documents: list[dict[str, Any]],
        manifest: dict[str, Any],
    ) -> None:
        """因为检索不能只依赖有损摘要，需要原子保存完整公开消息页、摘要分片和全文索引。"""
        # 1、只在 snapshot 阶段首次写入，重启复用文件和事务回执，不追加重复索引。
        record = self.get(identifier)
        if record["state"] != "snapshot":
            return
        with self.db:
            self.db.executemany(
                "INSERT INTO archive_messages VALUES(?,?,?)",
                [
                    (identifier, item["position"], json.dumps(item, ensure_ascii=False))
                    for item in messages
                ],
            )
            self.db.executemany(
                "INSERT INTO archive_parts VALUES(?,?,?,NULL)",
                [
                    (identifier, index, json.dumps(part, ensure_ascii=False))
                    for index, part in enumerate(parts)
                ],
            )
            for document in documents:
                self.document(identifier, document)
            self.db.execute(
                "UPDATE archives SET state='indexing_raw',manifest=?,error=NULL WHERE id=?",
                (json.dumps(manifest, ensure_ascii=False), identifier),
            )

    def document(self, identifier: str, value: dict[str, Any]) -> None:
        """因为摘要、笔记和原文片段都要复用检索，需要在同一索引合同中保存来源范围。"""
        # 1、事务由调用方管理，向量稍后补齐不会改变原文字段或来源。
        record = self.get(identifier)
        member = value.get("member_id")
        agent = value.get("agent_id")
        if member in {None, "", "boss"}:
            member, agent = record["member_id"], record["agent_id"]
        self.db.execute(
            "INSERT INTO archive_documents(archive_id,workspace_id,member_id,agent_id,at,"
            "kind,text,first_position,last_position) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                identifier,
                record["workspace_id"],
                member,
                agent or record["agent_id"],
                value.get("at") or record["ended_at"],
                value["kind"],
                value["text"],
                value["first_position"],
                value["last_position"],
            ),
        )

    def next_part(self, identifier: str) -> dict[str, Any] | None:
        """因为一次归档不能无限占用模型，需要每次只取一个尚未完成的摘要片段。"""
        # 1、已提交的片段结果保留，重试不重复收费。
        row = self.db.execute(
            "SELECT * FROM archive_parts WHERE archive_id=? AND result IS NULL "
            "ORDER BY position LIMIT 1",
            (identifier,),
        ).fetchone()
        return {**dict(row), **json.loads(row["body"])} if row else None

    def consume_model_call(self, now: float) -> bool:
        """因为归档旧历史不能无限消耗模型额度，需要按真实小时持久限制全应用十二次后台摘要调用。"""
        # 1、请求发出前扣额度，重启不重置，失败调用同样计数；这不影响用户前台任务。
        hour = int(now // 3600)
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO archive_model_usage VALUES(?,0)", (hour,))
            result = self.db.execute(
                "UPDATE archive_model_usage SET calls=calls+1 WHERE hour=? AND calls<12", (hour,)
            )
        return result.rowcount == 1

    def save_part(self, identifier: str, position: int, result: dict[str, Any]) -> None:
        """因为模型调用后可能发生崩溃，需要及时提交已通过来源校验的摘要与笔记。"""
        # 1、同一片段只接受首次成功结果，不覆盖已经用于生成索引的内容。
        with self.db:
            self.db.execute(
                "UPDATE archive_parts SET result=? WHERE archive_id=? "
                "AND position=? AND result IS NULL",
                (json.dumps(result, ensure_ascii=False), identifier, position),
            )

    def finish_summary(self, identifier: str) -> None:
        """因为每段都有独立来源，需要合并已完成摘要并索引笔记，而不删去较早片段。"""
        # 1、缺失片段不能宣称归档摘要完成；所有结果合并为带日期的可追溯内容。
        rows = self.db.execute(
            "SELECT result FROM archive_parts WHERE archive_id=? ORDER BY position", (identifier,)
        ).fetchall()
        if any(row[0] is None for row in rows):
            raise ValueError("档案仍有未完成摘要片段")
        results = [json.loads(row[0]) for row in rows]
        summary = "\n".join(item["summary"] for item in results)
        with self.db:
            for item in results:
                for note in [
                    {"text": item["summary"], "positions": item["positions"]},
                    *item["notes"],
                ]:
                    self.document(
                        identifier,
                        {
                            "kind": "note",
                            "text": note["text"],
                            "first_position": min(note["positions"]),
                            "last_position": max(note["positions"]),
                            **self.note_actor(identifier, note["positions"]),
                        },
                    )
            self.db.execute(
                "UPDATE archives SET summary=?,state='indexing',error=NULL,attempts=0 WHERE id=?",
                (summary, identifier),
            )

    def note_actor(self, identifier: str, positions: list[int]) -> dict[str, str]:
        """因为子 Agent 也需自己的笔记，需要按真实来源识别执行者，而不相信模型填写身份。"""
        # 1、用户消息归属会话入口；明确单一员工来源归该员工，混合来源保留在主任务档案下。
        placeholders = ",".join("?" for _ in positions)
        rows = self.db.execute(
            "SELECT body FROM archive_messages WHERE archive_id=? AND position IN ("
            + placeholders
            + ")",
            [identifier, *positions],
        )
        actors = {}
        for row in rows:
            message = json.loads(row[0])
            if message.get("member_id") not in {None, "", "boss"}:
                actors[message["member_id"]] = message.get("agent_id") or ""
        if len(actors) == 1:
            member, agent = next(iter(actors.items()))
            return {"member_id": member, "agent_id": agent}
        return {}

    def own_excerpts(self, identifier: str, member_id: str) -> str:
        """因为参与他人主任务不代表应自动载入全部主任务记忆，需要优先提取自己的笔记和原话。"""
        # 1、只读取该档案中实际归属当前成员的索引，按笔记优先保留少量背景。
        rows = self.db.execute(
            "SELECT text FROM archive_documents WHERE archive_id=? AND member_id=? "
            "ORDER BY CASE kind WHEN 'note' THEN 0 ELSE 1 END,id DESC LIMIT 4",
            (identifier, member_id),
        )
        return "\n".join(row[0] for row in rows)

    def pending_vectors(
        self, identifier: str, limit: int = 32, model: str = ""
    ) -> list[dict[str, Any]]:
        """因为长会话的向量不能一次占满内存，需要分批读取尚未编码的片段。"""
        # 1、每批限制数量，原文可在向量生成之前通过文本索引查询。
        return [
            dict(row)
            for row in self.db.execute(
                "SELECT id,text FROM archive_documents WHERE archive_id=? "
                "AND (vector IS NULL OR (?!='' AND COALESCE(model,'')!=?)) "
                "ORDER BY id LIMIT ?",
                (identifier, model, model, limit),
            )
        ]

    def reindex(self, identifier: str) -> None:
        """因为模型升级或索引损坏后需要重建，需要只清除派生向量并从保留文本恢复全文索引。"""
        # 1、不删除原文、摘要和会话；向量由后台按当前模型版本重新生成。
        with self.db:
            self.db.execute(
                "UPDATE archive_documents SET vector=NULL,model=NULL WHERE archive_id=?",
                (identifier,),
            )
            self.db.execute("INSERT INTO archive_fts(archive_fts) VALUES('rebuild')")
            self.db.execute(
                "UPDATE archives SET state='indexing',attempts=0,error=NULL,retry_at=0 WHERE id=?",
                (identifier,),
            )

    def save_vectors(self, values: list[tuple[bytes, str, int]]) -> None:
        """因为模型版本不同的向量不能混用，需要为每个持久向量明确登记模型标识。"""
        # 1、向量写入不修改全文索引，不保存远程模型配置。
        with self.db:
            self.db.executemany("UPDATE archive_documents SET vector=?,model=? WHERE id=?", values)

    def state(
        self, identifier: str, state: str, error: str | None = None, retry_at: float = 0
    ) -> None:
        """因为后台失败不能静默反复收费，需要持久状态、稳定错误码和下次重试时间。"""
        # 1、明确重试清零次数；一般异常累计次数并保留原文与成功分片。
        with self.db:
            self.db.execute(
                "UPDATE archives SET state=?,error=?,retry_at=?,"
                "attempts=CASE WHEN ? IS NULL THEN 0 ELSE attempts+1 END WHERE id=?",
                (state, error, retry_at, error, identifier),
            )

    def messages(self, identifier: str, offset: int, limit: int) -> list[dict[str, Any]]:
        """因为完整会话可能很长，需要按稳定消息位置分页读取，不用摘要冒充原始列表。"""
        # 1、权限检查由应用在调用前完成；查询不把其他档案行混入当前页。
        return [
            json.loads(row[0])
            for row in self.db.execute(
                "SELECT body FROM archive_messages WHERE archive_id=? AND position>=? "
                "ORDER BY position LIMIT ?",
                (identifier, offset, limit),
            )
        ]

    def scope(self, workspace_id: str) -> list[str]:
        """因为共享是有方向的用户授权，需要返回当前空间及用户选定的来源空间。"""
        # 1、模型无法通过查询参数扩大这个白名单。
        return [
            workspace_id,
            *[
                row[0]
                for row in self.db.execute(
                    "SELECT source_workspace FROM archive_shares WHERE target_workspace=?",
                    (workspace_id,),
                )
            ],
        ]

    def share(self, target: str, sources: list[str]) -> None:
        """因为撤销后新查询必须立即失效，需要由可信用户入口原子替换当前空间的来源白名单。"""
        # 1、来源有效性由空间目录校验，Agent 工具没有此方法。
        with self.db:
            self.db.execute("DELETE FROM archive_shares WHERE target_workspace=?", (target,))
            self.db.executemany(
                "INSERT INTO archive_shares VALUES(?,?)",
                [(target, source) for source in sources if source != target],
            )

    def close(self) -> None:
        """因为数据库由单宿主管理，需要在后台归档停止后释放连接。"""
        # 1、关闭不删除历史、摘要或用户共享设置。
        self.db.close()
