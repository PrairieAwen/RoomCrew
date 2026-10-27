"""人物未读提示与已读回执；独立于执行状态和可重建的动画缓存。"""

import json
import sqlite3
import threading
from contextlib import closing
from pathlib import Path
from typing import Any

KINDS = (
    "run.completed",
    "task.completed",
    "human.requested",
    "human.responded",
    "run.cancelled",
    "run.failed",
    "run.interrupted",
)


class BubbleStore:
    def __init__(self, journal: Path, database: Path) -> None:
        """因为未读泡泡不能被新任务或重启清除，需要单独保存稳定通知身份与用户回执。"""
        # 1、不在执行器注册回调；仅在桌面查询时读取已提交的业务事件。
        self.journal, self.database = journal, database
        self._lock = threading.Lock()

    def feed(self, cursor: int) -> dict[str, list[dict[str, Any]]]:
        """因为人物最新状态会改变，需要按日志增量维护独立待处理提示并返回每个人物的未读队列。"""
        # 1、游标与提示在一个桌面事务中提交，重试和历史回放不会生成重复泡泡。
        with self._lock, closing(self._connect()) as db, db:
            previous = db.execute("SELECT cursor FROM bubble_cursor WHERE id=1").fetchone()[0]
            if cursor > previous:
                with closing(
                    sqlite3.connect(self.journal.as_uri() + "?mode=ro", uri=True, timeout=0.2)
                ) as source:
                    source.row_factory = sqlite3.Row
                    placeholders = ",".join("?" for _ in KINDS)
                    rows = source.execute(
                        "SELECT * FROM events WHERE seq>? AND seq<=? "
                        f"AND kind IN ({placeholders}) ORDER BY seq",
                        (previous, cursor, *KINDS),
                    ).fetchall()
                for row in rows:
                    self._consume(db, dict(row))
                db.execute("UPDATE bubble_cursor SET cursor=? WHERE id=1", (cursor,))
            # 2、人工问题优先，多个完成结果逐个保留，不能被最新运行覆盖。
            result: dict[str, list[dict[str, Any]]] = {}
            for row in db.execute(
                "SELECT member_id,body FROM bubble_notices WHERE status='pending' "
                "ORDER BY CASE kind WHEN 'question' THEN 0 ELSE 1 END,source_seq"
            ):
                result.setdefault(row[0], []).append(json.loads(row[1]))
            return result

    def acknowledge(self, member_id: str, notice_id: str) -> None:
        """因为只有成功查看结果才算已读，需要按人物和稳定通知 ID 保存幂等回执。"""
        # 1、客户端不能通过已读接口消除人工问题；问题只由真实答复或任务取消解决。
        with self._lock, closing(self._connect()) as db, db:
            row = db.execute(
                "SELECT kind FROM bubble_notices WHERE id=? AND member_id=?", (notice_id, member_id)
            ).fetchone()
            if row is None:
                raise ValueError("该人物没有这条泡泡提示")
            if row[0] != "result":
                raise ValueError("人工问题需要提交答复后才会消失")
            db.execute("UPDATE bubble_notices SET status='seen' WHERE id=?", (notice_id,))

    def _connect(self) -> sqlite3.Connection:
        """因为回执不属于可丢弃的投影缓存，需要在工作空间独立的桌面数据库建立稳定表。"""
        # 1、连接只在本次调用线程使用，不持锁跨网络、模型或用户输入。
        db = sqlite3.connect(self.database, timeout=0.2)
        db.executescript("""
            CREATE TABLE IF NOT EXISTS bubble_cursor(
                id INTEGER PRIMARY KEY, cursor INTEGER NOT NULL);
            INSERT OR IGNORE INTO bubble_cursor VALUES(1,0);
            CREATE TABLE IF NOT EXISTS bubble_notices(
                id TEXT PRIMARY KEY, member_id TEXT NOT NULL, run_id TEXT NOT NULL,
                kind TEXT NOT NULL, request_id TEXT, source_seq INTEGER NOT NULL,
                status TEXT NOT NULL, body TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS bubble_pending
                ON bubble_notices(status,member_id,source_seq);
        """)
        return db

    def _consume(self, db: sqlite3.Connection, event: dict[str, Any]) -> None:
        """因为一个 Run 有多个成员和人工恢复，需要只按真实触发事件建立或解决对应提示。"""
        # 1、真实人工答复和取消只解除对应问题，不能把旧的完成结果标记已读。
        payload = json.loads(event["payload"])
        kind, run = event["kind"], event["run_id"]
        if kind == "human.responded":
            db.execute(
                "UPDATE bubble_notices SET status='resolved' "
                "WHERE kind='question' AND request_id=?",
                (payload.get("request_id"),),
            )
            return
        if kind in {"run.cancelled", "run.failed", "run.interrupted"}:
            db.execute(
                "UPDATE bubble_notices SET status='resolved' WHERE kind='question' AND run_id=?",
                (run,),
            )
            return
        if kind == "task.completed" and (
            payload.get("status") == "error"
            or payload.get("external_worker")
            or payload.get("presentation_external")
            or payload.get("delegation_kind") == "external"
        ):
            return
        # 2、完成与问题使用稳定 ID；同一工具中断恢复重复发出事件也只登记一次。
        question = kind == "human.requested"
        request = payload.get("request_id") if question else None
        if question and not isinstance(request, str):
            return
        identifier = f"question:{request}" if question else f"result:{run}:{event['scope']}"
        notice = {
            "id": identifier,
            "member_id": event.get("member_id") or "assistant",
            "conversation_id": event["conversation_id"],
            "run_id": run,
            "kind": "question" if question else "result",
            "request_id": request,
            "source_seq": event["seq"],
            "scope": event["scope"],
        }
        db.execute(
            "INSERT OR IGNORE INTO bubble_notices VALUES(?,?,?,?,?,?,?,?)",
            (
                identifier,
                notice["member_id"],
                run,
                notice["kind"],
                request,
                event["seq"],
                "pending",
                json.dumps(notice, ensure_ascii=False),
            ),
        )
