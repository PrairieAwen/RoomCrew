"""可滞后但不丢弃的表现队列、顺序回执与工作空间隔离验证。"""

import json
import sqlite3
from pathlib import Path

import pytest

from roomcrew_desktop.presentation.action_queue import ActionQueueStore, performance_event


def journal(path: Path, rows: list[tuple]) -> None:
    """因为队列只能消费正式来源，需要构造不包含模型秘密的独立合成事件日志。"""
    # 1、字段保持生产消费者读取合同，不直接写入表现队列。
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY,kind TEXT,run_id TEXT,"
            "member_id TEXT,created_at TEXT,payload TEXT)"
        )
        db.executemany("INSERT INTO events VALUES(?,?,?,?,?,?)", rows)


def test_parallel_delegations_are_ordered_persistent_and_acknowledged_once(tmp_path: Path) -> None:
    """因为一个模型可能同时派给两个成员，需要保留 A 后 B 并在重启、重试时不重复消费。"""
    # 1、先建立首次基线，再写两条同 Run 不同目标的真实形状事件。
    source, database = tmp_path / "events.sqlite", tmp_path / "actions.sqlite"
    journal(source, [])
    queue = ActionQueueStore(source, database)
    assert queue.feed(0)["actions_pending"] == 0
    rows = [
        (
            seq,
            "task.assigned",
            "same-run",
            target,
            "2020-01-01T00:00:00Z",
            json.dumps(
                {
                    "delegation_kind": "configured",
                    "from_member_id": "lead",
                    "target_member_id": target,
                }
            ),
        )
        for seq, target in [(1, "a"), (2, "b")]
    ]
    journal(source, rows)
    first = queue.feed(2)
    assert [item["target_member_id"] for item in first["actions"]] == ["a", "b"]
    assert all(item["member_id"] == "lead" for item in first["actions"])
    assert queue.feed(2) == first
    # 2、不允许跨过 A 确认 B，完成回执可重试；重启恢复剩余队首。
    with pytest.raises(ValueError, match="前一个"):
        queue.acknowledge("2", "played")
    queue.acknowledge("1", "played")
    assert queue.acknowledge("1", "skipped", "manual")["status"] == "played"
    restored = ActionQueueStore(source, database)
    assert [item["id"] for item in restored.feed(2)["actions"]] == ["2"]
    restored.acknowledge("2", "skipped", "missing_target")
    assert restored.feed(2)["actions_pending"] == 0
    with sqlite3.connect(source) as db:
        assert db.execute("SELECT count(*) FROM events").fetchone()[0] == 2


def test_queue_bootstrap_and_large_catchup_do_not_drop_tail(tmp_path: Path) -> None:
    """因为应用可能在大量事件后升级，需要跳过首次旧历史，但之后分批接收不能漏掉尾部。"""
    # 1、首次旧记录不突然回放，之后七百个外部调用必须全部进入待播队列。
    source = tmp_path / "events.sqlite"
    row = (1, "tool.started", "r", "lead", "2020-01-01T00:00:00Z", json.dumps({"tool_kind": "mcp"}))
    journal(source, [row])
    queue = ActionQueueStore(source, tmp_path / "actions.sqlite")
    assert queue.feed(0)["actions_pending"] == 0
    assert queue.feed(1)["actions_pending"] == 0
    journal(source, [(seq, *row[1:]) for seq in range(2, 702)])
    first = queue.feed(701)
    assert first["actions_pending"] == 1
    assert first["actions"][0]["aggregation"]["count"] == 512
    second = queue.feed(701)
    assert second["actions_pending"] == 1 and second["actions_coalesced"] == 699
    assert second["actions"][0]["aggregation"]["count"] == 700
    assert second["actions"][0]["aggregation"]["last_seq"] == 701
    # 2、另一个空间使用独立收件箱和消费基线，不能读到本空间的待播队列。
    other = ActionQueueStore(source, tmp_path / "other-space.sqlite")
    assert other.feed(701)["actions_pending"] == 0


def tool_row(
    seq: int,
    timestamp: str,
    member: str = "lead",
    kind: str = "mcp",
    run: str = "r",
) -> tuple:
    """因为聚合边界取决于来源时间与人物，需要生成保留完整正式字段的独立工具事件。"""
    # 1、档案查询与 MCP 为不同语义；不包含模型秘密或外部输入正文。
    payload = {"tool_kind": kind}
    if kind == "archive":
        payload["name"] = "search_archive"
    return seq, "tool.started", run, member, timestamp, json.dumps(payload)


def test_window_is_leading_immediate_and_does_not_extend(tmp_path: Path) -> None:
    """因为自然分钟切桶会在相邻秒重复演出，需要从首次事件起算六十秒且首条立即可播。"""
    # 1、12:00:59 的首条直接入队，不等待一分钟；不同 Run 的同一人物共用演出窗口。
    source = tmp_path / "events.sqlite"
    journal(source, [])
    queue = ActionQueueStore(source, tmp_path / "actions.sqlite")
    queue.feed(0)
    journal(source, [tool_row(1, "2026-10-30T12:00:59Z")])
    first = queue.feed(1)
    assert [item["id"] for item in first["actions"]] == ["1"]
    journal(source, [tool_row(2, "2026-10-30T12:01:58.999Z", run="other-run")])
    assert queue.feed(2)["actions"][0]["aggregation"]["count"] == 2
    # 2、恰好第六十秒开始新窗，上一秒重复不延长旧窗；时区等价表示仍正确聚合。
    journal(
        source,
        [
            tool_row(3, "2026-10-30T12:01:59Z"),
            tool_row(4, "2026-10-30T20:02:58.999+08:00"),
        ],
    )
    snapshot = queue.feed(4)
    assert snapshot["action_policy"]["window_ms"] == 60000
    assert [item["id"] for item in snapshot["actions"]] == ["1", "3"]
    assert [item["aggregation"]["count"] for item in snapshot["actions"]] == [2, 2]
    assert queue.feed(4) == snapshot


def test_played_window_absorbs_new_calls_across_restart(tmp_path: Path) -> None:
    """因为快动作可能在下次调用前播完，需要已消费窗口跨重启仍吸收一分钟内的重复。"""
    # 1、播放第一条后立即再来调用，不能创建第二次电话或查档行走。
    source, database = tmp_path / "events.sqlite", tmp_path / "actions.sqlite"
    journal(source, [])
    queue = ActionQueueStore(source, database)
    queue.feed(0)
    journal(source, [tool_row(1, "2026-10-30T12:00:00Z", kind="archive")])
    queue.feed(1)
    queue.acknowledge("1", "played")
    journal(source, [tool_row(2, "2026-10-30T12:00:30Z", kind="archive")])
    restored = ActionQueueStore(source, database)
    snapshot = restored.feed(2)
    assert snapshot["actions"] == [] and snapshot["actions_coalesced"] == 1
    # 2、回执重试不改变次数，跨窗下一次查档仍允许一次新演出。
    assert restored.acknowledge("1", "skipped", "manual")["status"] == "played"
    journal(source, [tool_row(3, "2026-10-30T12:01:00Z", kind="archive")])
    assert [item["id"] for item in restored.feed(3)["actions"]] == ["3"]
    with sqlite3.connect(database) as db:
        group = json.loads(db.execute("SELECT body FROM actions WHERE seq=1").fetchone()[0])
        assert group["aggregation"]["count"] == 2
    with sqlite3.connect(source) as db:
        assert db.execute("SELECT count(*) FROM events").fetchone()[0] == 3


def test_members_kinds_and_workspaces_are_not_mixed(tmp_path: Path) -> None:
    """因为共享 Agent 定义不代表共享人物，需要分别聚合人物和动作类别，空间仍独立。"""
    # 1、同一时刻的不同人物、MCP 与查档、每次审核都各自保留。
    source = tmp_path / "events.sqlite"
    journal(source, [])
    queue = ActionQueueStore(source, tmp_path / "actions.sqlite")
    other = ActionQueueStore(source, tmp_path / "other.sqlite")
    queue.feed(0)
    other.feed(0)
    stamp = "2026-10-30T12:00:00Z"
    journal(
        source,
        [
            tool_row(1, stamp),
            tool_row(2, stamp),
            tool_row(3, stamp, member="second"),
            tool_row(4, stamp, kind="archive"),
            tool_row(5, stamp, kind="security"),
            tool_row(6, stamp, kind="security"),
        ],
    )
    snapshot = queue.feed(6)
    assert [item["id"] for item in snapshot["actions"]] == ["1", "3", "4", "5", "6"]
    queue.acknowledge("1", "played")
    assert other.feed(6)["actions"][0]["id"] == "1"
    assert [item["aggregation"]["count"] for item in snapshot["actions"]] == [2, 1, 1, 1, 1]


def test_legacy_backlog_is_coalesced_without_replaying_receipts(tmp_path: Path) -> None:
    """因为升级前已经积压的动作也会来回跑，需要迁移旧队列且保留已经播放的事实。"""
    # 1、建立旧表与旧回执；MCP 已播一项，查档两项仍待播，源日志保持完整。
    source, database = tmp_path / "events.sqlite", tmp_path / "actions.sqlite"
    stamp = "2026-10-30T12:00:00Z"
    rows = [tool_row(1, stamp), tool_row(2, stamp)] + [
        tool_row(seq, stamp, kind="archive") for seq in (3, 4)
    ]
    journal(source, rows)
    with sqlite3.connect(database) as db:
        db.executescript(
            "CREATE TABLE action_cursor(id INTEGER PRIMARY KEY,cursor INTEGER NOT NULL);"
            "CREATE TABLE actions(seq INTEGER PRIMARY KEY,body TEXT,status TEXT,reason TEXT);"
            "INSERT INTO action_cursor VALUES(1,4);"
        )
        for row in rows:
            event = dict(zip(
                ("seq", "kind", "run_id", "member_id", "created_at", "payload"), row, strict=True
            ))
            event["payload"] = json.loads(event["payload"])
            db.execute(
                "INSERT INTO actions VALUES(?,?,?,NULL)",
                (
                    row[0], json.dumps(performance_event(event)),
                    "played" if row[0] == 1 else "pending",
                ),
            )
    # 2、旧待播电话归入已播窗口，不重播；查档只保留一个往返，重开库不重复累计。
    snapshot = ActionQueueStore(source, database).feed(4)
    assert [item["id"] for item in snapshot["actions"]] == ["3"]
    assert snapshot["actions"][0]["aggregation"]["count"] == 2
    assert snapshot["actions_coalesced"] == 2
    assert ActionQueueStore(source, database).feed(4) == snapshot
    with sqlite3.connect(source) as db:
        assert db.execute("SELECT count(*) FROM events").fetchone()[0] == 4


def test_invalid_or_backward_time_is_conservative(tmp_path: Path) -> None:
    """因为异常时间不能导致错误抑制，需要保守逐条保留且时钟回拨不污染新的正常窗口。"""
    # 1、缺时区、损坏时间以及回拨记录不能被加入未来窗口。
    source = tmp_path / "events.sqlite"
    journal(source, [])
    queue = ActionQueueStore(source, tmp_path / "actions.sqlite")
    queue.feed(0)
    journal(source, [tool_row(i, stamp) for i, stamp in enumerate([
        "invalid", "2026-10-30T12:00:00", "2026-10-30T12:00:00Z",
        "2026-10-30T11:59:00Z", "2026-10-30T12:00:30Z",
    ], 1)])
    snapshot = queue.feed(5)
    assert [item["id"] for item in snapshot["actions"]] == ["1", "2", "3", "4"]
    assert snapshot["actions"][2]["aggregation"]["count"] == 2


def test_interleaved_delegation_is_not_skipped_by_group_last_sequence(tmp_path: Path) -> None:
    """因为两次 MCP 之间可能派给员工任务，需要聚合最后序号不跳过中间的独立委派。"""
    # 1、聚合代表仍用首序号排队，委派保持独立来源与回执。
    source = tmp_path / "events.sqlite"
    journal(source, [])
    queue = ActionQueueStore(source, tmp_path / "actions.sqlite")
    queue.feed(0)
    stamp = "2026-10-30T12:00:00Z"
    journal(source, [
        tool_row(1, stamp),
        (2, "task.assigned", "r", "a", stamp, json.dumps({
            "delegation_kind": "configured", "from_member_id": "lead", "target_member_id": "a",
        })),
        tool_row(3, stamp),
    ])
    snapshot = queue.feed(3)
    assert [item["id"] for item in snapshot["actions"]] == ["1", "2"]
    assert snapshot["actions"][0]["aggregation"]["last_seq"] == 3
    queue.acknowledge("1", "played")
    assert [item["id"] for item in queue.feed(3)["actions"]] == ["2"]
    queue.acknowledge("2", "played")
    assert queue.feed(3)["actions_pending"] == 0


def test_only_explicit_special_behaviors_enter_performance_queue() -> None:
    """因为普通工作应持续打电脑，需要只将外部调用、历史检索、明确委派和审核请求做一次性演出。"""
    # 1、不得从工具文本、模型自称完成或未配置的角色名字推断表演。
    base = {
        "seq": 1,
        "kind": "tool.started",
        "run_id": "run",
        "member_id": "lead",
        "created_at": "2026-10-30T00:00:00Z",
    }
    for name in ["read_file", "write_file", "execute_python", "list_agents"]:
        assert performance_event({**base, "payload": {"name": name}}) is None
    for payload, expected in [
        ({"tool_kind": "mcp"}, "mcp"),
        ({"name": "search_archive"}, "archive"),
        ({"name": "read_archive_messages"}, "archive"),
        ({"tool_kind": "security"}, "security"),
    ]:
        result = performance_event({**base, "payload": payload})
        assert result and result["kind"] == expected and result["visual_only"]
    assert (
        performance_event({**base, "kind": "assistant.message", "payload": {"text": "走到档案库"}})
        is None
    )
