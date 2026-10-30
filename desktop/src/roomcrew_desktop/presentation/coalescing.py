"""桌面行为聚合合同；只压缩演出次数，不压缩后端轨迹或工具调用。"""

from datetime import datetime
from typing import Any

WINDOW_MS = 60_000
COALESCED_KINDS = frozenset({"mcp", "archive"})
ACTION_POLICY = {
    "version": 1,
    "mode": "leading_window",
    "window_ms": WINDOW_MS,
    "kinds": sorted(COALESCED_KINDS),
    "scope": ["workspace", "member_id", "kind"],
}


def event_milliseconds(action: dict[str, Any]) -> int | None:
    """因为同类演出按真实事件时间合并，需要读取带时区时间；异常时间保守逐条处理。"""
    # 1、委派、审核及无可靠时间的事件不进入聚合窗口，不按当前电脑时间猜测来源。
    if action["kind"] not in COALESCED_KINDS:
        return None
    try:
        timestamp = datetime.fromisoformat(action["created_at"])
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            return None
        return int(timestamp.timestamp() * 1000)
    except (TypeError, ValueError, OverflowError):
        return None


def initial_aggregation(action: dict[str, Any]) -> dict[str, Any]:
    """因为界面需要知道一个动作代表几次调用，需要以首个来源 ID 建立有版本的有限聚合摘要。"""
    # 1、首条立即可播，窗口不随新调用延长；跨 Run 只共用人物演出，不共享执行上下文。
    return {
        **action,
        "aggregation": {
            "version": 1,
            "count": 1,
            "first_seq": action["source_seq"],
            "last_seq": action["source_seq"],
            "first_at": action["created_at"],
            "last_at": action["created_at"],
            "window_ms": WINDOW_MS if event_milliseconds(action) is not None else 0,
        },
    }
