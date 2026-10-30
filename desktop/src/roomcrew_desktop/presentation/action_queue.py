"""独立于执行器的持久表现收件箱；演出回执不代表工具成功或真实授权。"""

import json
import sqlite3
import threading
from contextlib import closing
from pathlib import Path
from typing import Any

from roomcrew_desktop.presentation.coalescing import (
    ACTION_POLICY,
    WINDOW_MS,
    event_milliseconds,
    initial_aggregation,
)


def performance_event(event: dict[str, Any]) -> dict[str, Any] | None:
    """因为特殊行为需要逐次消费，需要从正式事件身份生成有限的表演指令，不解析自然语言。"""
    # 1、只有已配置成员的明确委派触发递文件，主角取正式来源身份而非当前选中人物。
    payload = event["payload"]
    kind, member, target = "", event.get("member_id"), None
    if event["kind"] == "task.assigned" and payload.get("delegation_kind") == "configured":
        kind, member, target = (
            "handoff",
            payload.get("from_member_id"),
            payload.get("target_member_id"),
        )
    elif event["kind"] == "tool.started":
        if payload.get("tool_kind") == "mcp":
            kind = "mcp"
        elif payload.get("name") in {"search_archive", "read_archive_messages"}:
            kind = "archive"
        elif payload.get("tool_kind") == "security":
            kind = "security"
    if not kind or not member or (kind == "handoff" and (not target or target == member)):
        return None
    # 2、动作不含任务正文、工具参数、文件路径或权限；相同序号只登记一次。
    return {
        "id": str(event["seq"]),
        "source_seq": event["seq"],
        "run_id": event["run_id"],
        "member_id": member,
        "target_member_id": target,
        "kind": kind,
        "created_at": event["created_at"],
        "visual_only": True,
    }


class ActionQueueStore:
    def __init__(self, journal: Path, database: Path) -> None:
        """因为画面可晚于任务且可能重启，需要单独持久化消费游标、待播事件和幂等回执。"""
        # 1、此存储只由桌面访问，不挂入后端 Run 或框架 checkpoint。
        self.journal, self.database = journal, database
        self._lock = threading.Lock()

    def _connect(self) -> sqlite3.Connection:
        """因为界面轮询可能来自多个线程，需要每次使用独立短连接和稳定唯一序号。"""
        # 1、业务日志只读；本库只记录表现层进度。
        db = sqlite3.connect(self.database, timeout=0.2)
        db.executescript("""
            CREATE TABLE IF NOT EXISTS action_cursor(
                id INTEGER PRIMARY KEY,cursor INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS actions(
                seq INTEGER PRIMARY KEY,body TEXT NOT NULL,status TEXT NOT NULL,reason TEXT);
            CREATE INDEX IF NOT EXISTS actions_pending ON actions(status,seq);
            CREATE TABLE IF NOT EXISTS action_windows(
                member_id TEXT NOT NULL,kind TEXT NOT NULL,starts_ms INTEGER NOT NULL,
                ends_ms INTEGER NOT NULL,seq INTEGER NOT NULL,
                PRIMARY KEY(member_id,kind));
        """)
        # 2、旧积压也必须合并；迁移与数据更新同事务，失败时保留原库供下次重试。
        try:
            with db:
                if db.execute("PRAGMA user_version").fetchone()[0] < 1:
                    self._migrate(db)
                    db.execute("PRAGMA user_version=1")
        except Exception:
            db.close()
            raise
        return db

    def _migrate(self, db: sqlite3.Connection) -> None:
        """因为旧版逐条待播项会继续造成积压，需要流式重建同类窗口并保留旧回执。"""
        # 1、来源按不可变主键遍历，不删除原始轨迹或把已播项重置为待播。
        db.execute("DELETE FROM action_windows")
        for seq, body, status, reason in db.execute(
            "SELECT seq,body,status,reason FROM actions ORDER BY seq"
        ):
            action = json.loads(body)
            if action["source_seq"] != seq:
                raise ValueError("表现动作来源序号不一致")
            self._record(db, action, status, reason, migrating=True)

    def _record(
        self,
        db: sqlite3.Connection,
        action: dict[str, Any],
        status: str = "pending",
        reason: str | None = None,
        *,
        migrating: bool = False,
    ) -> None:
        """因为重复轮询和旧回执不能重复演出，需要持久合并同人物同类动作并保留每次来源。"""
        # 1、来源序号幂等，普通委派与审核逐条保留；窗口在首个事件起算，不按自然分钟切桶。
        seq = action["source_seq"]
        if not migrating and db.execute("SELECT 1 FROM actions WHERE seq=?", (seq,)).fetchone():
            return
        value = initial_aggregation(action)
        stamp = event_milliseconds(action)
        window = None
        if stamp is not None:
            window = db.execute(
                "SELECT starts_ms,ends_ms,seq FROM action_windows WHERE member_id=? AND kind=?",
                (action["member_id"], action["kind"]),
            ).fetchone()
        if window and window[0] <= stamp < window[1]:
            representative = db.execute(
                "SELECT body,status FROM actions WHERE seq=?", (window[2],)
            ).fetchone()
            if representative is None:
                raise ValueError("表现聚合代表项缺失")
            group = json.loads(representative[0])
            aggregate = group["aggregation"]
            aggregate.update(
                count=aggregate["count"] + 1,
                last_seq=seq,
                last_at=action["created_at"],
            )
            # 2、已播窗口继续吸收后续调用；旧版若已消费任何一项，不重复播放同组。
            group_status = representative[1]
            if status == "played":
                group_status = "played"
            db.execute(
                "UPDATE actions SET body=?,status=? WHERE seq=?",
                (json.dumps(group, ensure_ascii=False), group_status, window[2]),
            )
            status, reason = "coalesced", str(window[2])
        elif stamp is not None and (not window or stamp >= window[0]):
            db.execute(
                "INSERT INTO action_windows VALUES(?,?,?,?,?) ON CONFLICT(member_id,kind) "
                "DO UPDATE SET starts_ms=excluded.starts_ms,ends_ms=excluded.ends_ms,"
                "seq=excluded.seq",
                (action["member_id"], action["kind"], stamp, stamp + WINDOW_MS, seq),
            )
        # 3、合并来源仅退出播放队列，仍保留关联与次数；代表项保留原 ID、顺序和回执。
        db.execute(
            "INSERT INTO actions VALUES(?,?,?,?) ON CONFLICT(seq) DO UPDATE SET "
            "body=excluded.body,status=excluded.status,reason=excluded.reason",
            (seq, json.dumps(value, ensure_ascii=False), status, reason),
        )

    def feed(self, cursor: int) -> dict[str, Any]:
        """因为重复外部调用应少演出而委派要保留，需要按确定窗口聚合并有界返回代表项。"""
        # 1、首次安装以当前历史为基线，不突然回放旧版本几天前的动作；之后保留全部已收到事件。
        with self._lock, closing(self._connect()) as db, db:
            previous = db.execute("SELECT cursor FROM action_cursor WHERE id=1").fetchone()
            if previous is None:
                # 快照重建每次仅归约 512 条，首次基线须取完整日志末尾，防止旧动作被分批补播。
                with closing(
                    sqlite3.connect(self.journal.as_uri() + "?mode=ro", uri=True, timeout=0.2)
                ) as source:
                    baseline = source.execute(
                        "SELECT coalesce(max(seq),0) FROM events"
                    ).fetchone()[0]
                db.execute("INSERT INTO action_cursor VALUES(1,?)", (baseline,))
            elif cursor > previous[0]:
                with closing(
                    sqlite3.connect(self.journal.as_uri() + "?mode=ro", uri=True, timeout=0.2)
                ) as source:
                    source.row_factory = sqlite3.Row
                    rows = source.execute(
                        "SELECT * FROM events WHERE seq>? AND seq<=? "
                        "AND kind IN ('tool.started','task.assigned') ORDER BY seq LIMIT 512",
                        (previous[0], cursor),
                    ).fetchall()
                for row in rows:
                    action = performance_event({**dict(row), "payload": json.loads(row["payload"])})
                    if action:
                        self._record(db, action)
                # 2、大批事件分多次接收，不能直接跳到最新游标而漏掉第 513 个特殊动作。
                reached = rows[-1]["seq"] if len(rows) == 512 else cursor
                db.execute("UPDATE action_cursor SET cursor=? WHERE id=1", (reached,))
            return {
                "action_policy": ACTION_POLICY,
                "actions": [
                    json.loads(row[0])
                    for row in db.execute(
                        "SELECT body FROM actions WHERE status='pending' ORDER BY seq LIMIT 32"
                    )
                ],
                "actions_pending": db.execute(
                    "SELECT count(*) FROM actions WHERE status='pending'"
                ).fetchone()[0],
                "actions_coalesced": db.execute(
                    "SELECT count(*) FROM actions WHERE status='coalesced'"
                ).fetchone()[0],
            }

    def acknowledge(self, identifier: str, result: str, reason: str = "") -> dict[str, str]:
        """因为动画结束可能重复回调，需要只幂等确认队首且拒绝把显示回执当作真实执行结果。"""
        # 1、回执只接受本库稳定序号和有限结果，不能修改模型任务、权限或原始轨迹。
        if not isinstance(identifier, str) or not identifier.isdigit() or len(identifier) > 18:
            raise ValueError("表现动作标识无效")
        if result not in {"played", "skipped"} or reason not in {
            "",
            "missing_actor",
            "missing_target",
            "unreachable",
            "manual",
            "reduced_motion",
            "layout_changed",
        }:
            raise ValueError("表现动作回执无效")
        with self._lock, closing(self._connect()) as db, db:
            row = db.execute(
                "SELECT status FROM actions WHERE seq=?", (int(identifier),)
            ).fetchone()
            if row is None:
                raise ValueError("表现动作不存在")
            if row[0] == "pending":
                first = db.execute(
                    "SELECT seq FROM actions WHERE status='pending' ORDER BY seq LIMIT 1"
                ).fetchone()[0]
                if first != int(identifier):
                    raise ValueError("请先消费前一个表现动作")
                db.execute(
                    "UPDATE actions SET status=?,reason=? WHERE seq=?",
                    (result, reason, int(identifier)),
                )
            else:
                # 2、重复回执返回已经落库的结果，后来的冲突请求不能改写消费事实。
                result = row[0]
        return {"id": identifier, "status": result}
