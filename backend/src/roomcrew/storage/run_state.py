"""持久化人工问题、运行身份快照和跨中断额度；与 checkpoint 分开对账。"""

import json
from typing import Any

from roomcrew.storage.sessions import SessionStore


class RunStateStore:
    def __init__(self, store: SessionStore) -> None:
        """因为人工等待需要跨重启恢复，需要在产品库保存可验证的问题和本次定义快照。"""
        # 1、这些字段不含模型客户端或秘密，只保存定义和业务引用。
        self.store = store
        self.db = store.connection
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS run_bindings(
                run_id TEXT PRIMARY KEY REFERENCES runs(id), binding TEXT NOT NULL,
                model_calls INTEGER NOT NULL DEFAULT 0, spent REAL NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS human_requests(
                id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
                conversation_id TEXT NOT NULL, member_id TEXT NOT NULL, agent_id TEXT NOT NULL,
                actor TEXT NOT NULL, scope TEXT NOT NULL, body TEXT NOT NULL, status TEXT NOT NULL,
                answer TEXT, command_id TEXT UNIQUE);
        """)

    def capture(self, run_id: str, binding: dict[str, Any]) -> None:
        """因为编辑人物不能改变已接单任务，需要在执行开始前固定主子 Agent 定义。"""
        # 1、只在首次受理时插入，恢复不能覆盖原快照。
        with self.db:
            self.db.execute(
                "INSERT INTO run_bindings(run_id,binding) VALUES(?,?)",
                (run_id, json.dumps(binding, ensure_ascii=False)),
            )

    def context(self, run_id: str) -> dict[str, Any]:
        """因为恢复需要沿用身份和消耗额度，需要读取本轮固定上下文。"""
        # 1、只接受实际已受理的运行。
        row = self.db.execute("SELECT * FROM run_bindings WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise ValueError("运行缺少可恢复的身份快照")
        return {**dict(row), "binding": json.loads(row["binding"])}

    def usage(self, run_id: str, calls: int, seconds: float) -> None:
        """因为等待用户不能重置总额度，需要保存模型累计次数和实际执行时长。"""
        # 1、人工离线等待不计入活动执行时间，但恢复后的请求继续扣同一额度。
        with self.db:
            self.db.execute(
                "UPDATE run_bindings SET model_calls=?,spent=spent+? WHERE run_id=?",
                (calls, max(0, seconds), run_id),
            )

    def request(
        self,
        conversation_id: str,
        run_id: str,
        actor: str,
        scope: str,
        agent_id: str,
        member_id: str,
        payload: dict[str, Any],
    ) -> bool:
        """因为框架中断在重放时可能重复出现，需要按 interrupt ID 幂等记录问题。"""
        # 1、重复问题不重写已提交的回答，也不重复追加提醒。
        with self.db:
            result = self.db.execute(
                "INSERT OR IGNORE INTO human_requests "
                "(id,run_id,conversation_id,member_id,agent_id,actor,scope,body,status) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    payload["request_id"],
                    run_id,
                    conversation_id,
                    member_id,
                    agent_id,
                    actor,
                    scope,
                    json.dumps(payload, ensure_ascii=False),
                    "pending",
                ),
            )
        return result.rowcount == 1

    def wait(self, run_id: str) -> None:
        """因为模型暂停不是任务完成，需要把运行明确转入等待人工状态。"""
        # 1、等待状态可以在应用关闭后保留，不伪装成运行或成功。
        with self.db:
            self.db.execute("UPDATE runs SET status='waiting_user' WHERE id=?", (run_id,))

    def questions(self, conversation_id: str | None = None) -> list[dict[str, Any]]:
        """因为老板需要知道哪些事项等待决定，需要查询持久问题而不靠正文问号猜测。"""
        # 1、只返回尚未回答且所属运行仍可恢复的问题。
        query = (
            "SELECT h.* FROM human_requests h JOIN runs r ON r.id=h.run_id "
            "WHERE h.status='pending' AND r.status='waiting_user'"
        )
        params: tuple[Any, ...] = ()
        if conversation_id:
            query += " AND h.conversation_id=?"
            params = (conversation_id,)
        return [{**dict(row), **json.loads(row["body"])} for row in self.db.execute(query, params)]

    def duplicate(self, command_id: str, request_id: str, answer: str) -> dict[str, Any] | None:
        """因为重试人工回答不能再次执行工具，需要先检查同一命令是否已受理。"""
        # 1、幂等标识绑定问题和内容，不能跨请求复用。
        row = self.db.execute(
            "SELECT * FROM human_requests WHERE command_id=?", (command_id,)
        ).fetchone()
        if row is not None and (row["id"] != request_id or row["answer"] != answer):
            raise ValueError("回答命令标识已用于其他内容")
        return dict(row) if row else None

    def answer(self, request_id: str, answer: str, command_id: str) -> dict[str, Any]:
        """因为过期或取消的问题不能恢复任务，需要在同一事务中验证并领取回答。"""
        # 1、这里处理信息确认，不签发系统权限或安全 VM 授权。
        with self.db:
            row = self.db.execute(
                "SELECT h.*,r.status AS run_status FROM human_requests h "
                "JOIN runs r ON h.run_id=r.id WHERE h.id=?",
                (request_id,),
            ).fetchone()
            if row is None or row["status"] != "pending" or row["run_status"] != "waiting_user":
                raise ValueError("该问题已回答、取消或不再等待")
            self.db.execute(
                "UPDATE human_requests SET status='answered',answer=?,command_id=? WHERE id=?",
                (answer, command_id, request_id),
            )
            self.db.execute("UPDATE runs SET status='running' WHERE id=?", (row["run_id"],))
        return dict(row)

    def cancel(self, run_id: str) -> None:
        """因为取消后旧按钮可能仍在页面，需要同步废弃该运行的人工问题。"""
        # 1、保留原记录，不删除历史证据。
        with self.db:
            self.db.execute(
                "UPDATE human_requests SET status='cancelled' WHERE run_id=? AND status='pending'",
                (run_id,),
            )
