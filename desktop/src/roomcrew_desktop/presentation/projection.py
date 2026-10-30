"""可丢弃、可重建的场景读模型，独立连接不加入执行器写事务。"""

import json
import sqlite3
import threading
from contextlib import closing
from pathlib import Path
from typing import Any

from roomcrew_desktop.presentation.animation import visual_cue
from roomcrew_desktop.presentation.collaboration import meeting_groups
from roomcrew_desktop.presentation.reducer import actor_view, reduce_event


class StudioProjection:
    def __init__(self, journal: Path, cache: Path) -> None:
        """因为场景故障不能让任务失败，需要只读业务日志并单独保存投影缓存。"""
        # 1、构造时不注册模型回调；消费由界面查询触发并放在独立工作线程。
        self._journal, self._cache = journal, cache
        self._lock = threading.Lock()

    def feed(self, after: int = 0) -> dict[str, Any]:
        """因为高频工具事件不宜逐条触发走动，需要有界增量归约并输出合并后的当前状态。"""
        # 1、只读源日志，投影锁和缓存写入不会持有执行器产品事务。
        with self._lock, closing(sqlite3.connect(self._cache, timeout=0.2)) as cache, cache:
            cache.execute(
                "CREATE TABLE IF NOT EXISTS projection("
                "id INTEGER PRIMARY KEY, cursor INTEGER, body TEXT)"
            )
            row = cache.execute("SELECT cursor,body FROM projection WHERE id=1").fetchone()
            cursor, actors = (row[0], json.loads(row[1])) if row else (0, {})
            # 新归约规则必须重放旧日志，不能继续复用旧子任务产生的 reporting 缓存。
            if cache.execute("PRAGMA user_version").fetchone()[0] < 1:
                cursor, actors = 0, {}
                cache.execute("PRAGMA user_version=1")
            with closing(
                sqlite3.connect(self._journal.as_uri() + "?mode=ro", uri=True, timeout=0.2)
            ) as journal:
                journal.row_factory = sqlite3.Row
                rows = journal.execute(
                    "SELECT * FROM events WHERE seq>? ORDER BY seq LIMIT 512", (cursor,)
                ).fetchall()
                latest_cursor = rows[-1]["seq"] if rows else cursor
                cue_rows = journal.execute(
                    "SELECT * FROM events WHERE seq>? AND seq<=? ORDER BY seq DESC LIMIT 96",
                    (max(0, int(after)), latest_cursor),
                ).fetchall()
            # 2、只转换已经提交的事件；未知输入保留安全回退，原日志不做任何修改。
            for source in rows:
                event = {**dict(source), "payload": json.loads(source["payload"])}
                reduce_event(actors, event)
                cursor = event["seq"]
            cache.execute(
                "INSERT INTO projection VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET "
                "cursor=excluded.cursor,body=excluded.body",
                (cursor, json.dumps(actors, ensure_ascii=False)),
            )
            cues = []
            for source in reversed(cue_rows):
                cue = visual_cue({**dict(source), "payload": json.loads(source["payload"])})
                if cue:
                    cues.append(cue)
            # 3、恢复时传快照；连接显式关闭，避免 Windows 句柄阻止重建缓存，正文不进入表现合同。
            views = [actor_view(state) for state in actors.values()]
            return {
                "protocol_version": 1,
                "cursor": cursor,
                "reset": after > cursor or after == 0,
                "catching_up": len(rows) == 512,
                "actors": views,
                "interactions": meeting_groups(views, actors),
                "cues": cues,
            }
