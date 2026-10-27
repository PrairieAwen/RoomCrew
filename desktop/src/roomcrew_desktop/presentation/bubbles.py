"""人物未读提示与已读回执；独立于执行状态和可重建的动画缓存。"""

import json
import sqlite3
import threading
from contextlib import closing
from pathlib import Path
from typing import Any

KINDS = (
    "run.started",
    "run.completed",
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
        """因为提示必须由任务入口转达，需要增量记录 Run 主人物并保留稳定通知与已读回执。"""
        # 1、游标与提示在一个桌面事务中提交，重试和历史回放不会生成重复泡泡。
        with self._lock, closing(self._connect()) as db, db:
            previous = db.execute("SELECT cursor FROM bubble_cursor WHERE id=1").fetchone()[0]
            migrating = db.execute("PRAGMA user_version").fetchone()[0] < 1
            if migrating:
                # 旧版子任务提示退役；重放只恢复有效主任务提示，已读与已答复状态保持原样。
                db.execute("UPDATE bubble_notices SET status='retired' WHERE status='pending'")
                previous = 0
            if cursor > previous or migrating:
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
                db.execute("PRAGMA user_version=1")
            # 2、人工问题优先，多个完成结果逐个保留，不能被最新运行覆盖。
            result: dict[str, list[dict[str, Any]]] = {}
            for row in db.execute(
                "SELECT member_id,body FROM bubble_notices WHERE status='pending' "
                "ORDER BY CASE kind WHEN 'question' THEN 0 ELSE 1 END,source_seq"
            ):
                result.setdefault(row[0], []).append(json.loads(row[1]))
            return result

    def acknowledge(self, member_id: str, notice_id: str, through_seq: int | None = None) -> None:
        """因为一个会话可能已有多轮完成，需要按实际加载序号确认该人物在此会话中已展示的结果。

        未提供 through_seq 时兼容单通知回执；不能消除人工问题、其他会话或随后新增结果。
        """
        # 1、客户端不能通过已读接口消除人工问题；问题只由真实答复或任务取消解决。
        with self._lock, closing(self._connect()) as db, db:
            row = db.execute(
                "SELECT kind,status,body,source_seq FROM bubble_notices WHERE id=? AND member_id=?",
                (notice_id, member_id),
            ).fetchone()
            if row is None or row[1] == "retired":
                raise ValueError("该人物没有这条泡泡提示")
            if row[0] != "result":
                raise ValueError("人工问题需要提交答复后才会消失")
            # 2、旧客户端只确认单条；新客户端必须已经完整加载点击通知及其之前的会话记录。
            if through_seq is None:
                db.execute("UPDATE bubble_notices SET status='seen' WHERE id=?", (notice_id,))
                return
            if type(through_seq) is not int or not row[3] <= through_seq <= 9007199254740991:
                raise ValueError("请先成功加载这条完成结果")
            conversation = json.loads(row[2])["conversation_id"]
            # 3、按人物、会话和已展示上界原子确认，重试不吞掉问题或更晚完成的任务。
            db.execute(
                "UPDATE bubble_notices SET status='seen' WHERE member_id=? AND kind='result' "
                "AND status='pending' AND source_seq<=? "
                "AND json_extract(body,'$.conversation_id')=?",
                (member_id, through_seq, conversation),
            )

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
            CREATE TABLE IF NOT EXISTS bubble_runs(
                run_id TEXT PRIMARY KEY, member_id TEXT NOT NULL);
        """)
        return db

    def _consume(self, db: sqlite3.Connection, event: dict[str, Any]) -> None:
        """因为子任务只对主 Agent 汇报，需要把整轮完成和人工请求呈现给该 Run 的入口人物。"""
        # 1、主身份取自正式启动事件，不能根据当前选中人物、共享 agent_id 或子任务触发者猜测。
        payload = json.loads(event["payload"])
        kind, run = event["kind"], event["run_id"]
        if kind == "run.started":
            if event["scope"] != "main":
                return
            db.execute(
                "INSERT OR IGNORE INTO bubble_runs VALUES(?,?)",
                (run, event.get("member_id") or "assistant"),
            )
            return
        # 2、真实人工答复和取消只解除对应问题，不能把旧的完成结果标记已读。
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
        if kind == "run.completed" and event["scope"] != "main":
            return
        owner = db.execute("SELECT member_id FROM bubble_runs WHERE run_id=?", (run,)).fetchone()
        if owner is None:
            return
        # 3、只有整轮完成提示结果；人工请求保留原始 ID 和来源，答复仍恢复原来的子任务。
        question = kind == "human.requested"
        request = payload.get("request_id") if question else None
        if question and not isinstance(request, str):
            return
        identifier = f"question:{request}" if question else f"result:{run}:{event['scope']}"
        notice = {
            "id": identifier,
            "member_id": owner[0],
            "source_member_id": event.get("member_id") or "assistant",
            "conversation_id": event["conversation_id"],
            "run_id": run,
            "kind": "question" if question else "result",
            "request_id": request,
            "source_seq": event["seq"],
            "scope": event["scope"],
        }
        db.execute(
            "INSERT INTO bubble_notices VALUES(?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET member_id=excluded.member_id,body=excluded.body, "
            "status=CASE WHEN bubble_notices.status='retired' THEN 'pending' "
            "ELSE bubble_notices.status END",
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
