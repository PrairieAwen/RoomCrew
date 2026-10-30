"""由公开事实产生有限动作提示；表情是表现规则，不是模型内心状态。"""

from typing import Any


def animation_hint(
    activity: str, tools: list[str], questions: int, warnings: int, kinds: list[str] | None = None
) -> dict[str, str]:
    """因为工作过程统一表现为操作电脑，需要按阶段保留人工与异常表情，特殊动作另行排队。"""
    # 1、快照不反复触发特殊行为，兼容调用参数不包含正文或模型推断的成败。
    gesture = {
        "thinking": "type",
        "executing": "type",
        "delegating": "type",
        "question": "ask",
        "reporting": "report",
        "warning": "alert",
        "receiving": "type",
        "waiting": "type",
    }.get(activity, "idle")
    # 特殊动作通过独立持久队列短暂演出；快照始终保留正常工作的电脑动作。
    # 2、问题与错误优先显示表情，但不令其他正在执行的上下文变成完成或暂停。
    expression = "focused" if activity in {"thinking", "executing", "delegating"} else "neutral"
    if activity == "reporting":
        expression = "smile"
    if questions:
        expression = "curious"
    elif warnings or activity == "warning":
        expression = "concerned"
    return {"gesture": gesture, "expression": expression, "source": "trace_rules"}


def visual_cue(event: dict[str, Any]) -> dict[str, Any] | None:
    """因为工具很快时轮询可能跳过活动状态，需要保留短暂且可丢弃的动作线索。"""
    # 1、只输出有限词表与序号，不能把线索当作执行指令或真实任务状态。
    kind, payload = event["kind"], event["payload"]
    if payload.get("external_worker") or payload.get("presentation_external"):
        return None
    expression, duration = "focused", 320
    if kind == "tool.started":
        if payload.get("tool_kind") in {"mcp", "security"} or payload.get("name") in {
            "search_archive",
            "read_archive_messages",
            "task",
            "ask_user",
        }:
            return None
        action = "type"
        # 快速远程工具也需留出转向显示器后的实际操作时间，不能只播放转身。
        duration = 900 if action in {"type", "work", "write"} else duration
    elif kind == "human.requested":
        action, expression, duration = "ask", "curious", 900
    elif kind in {"tool.failed", "run.failed", "run.interrupted", "task.failed"}:
        action, expression, duration = "alert", "concerned", 900
    elif kind == "run.completed":
        if event.get("scope", "main") != "main":
            return None
        action, expression, duration = "report", "smile", 800
    else:
        return None
    return {
        "source_seq": event["seq"],
        "member_id": event.get("member_id") or "assistant",
        "run_id": event["run_id"],
        "action": action,
        "expression": expression,
        "duration_ms": duration,
        "created_at": event["created_at"],
        "visual_only": True,
    }
