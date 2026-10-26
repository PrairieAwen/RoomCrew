"""由公开事实产生有限动作提示；表情是表现规则，不是模型内心状态。"""

from typing import Any

OPERATIONS = {
    "read_file": "read",
    "ls": "read",
    "glob": "read",
    "grep": "read",
    "write_file": "write",
    "edit_file": "type",
    "write_todos": "write",
    "task": "talk",
    "ask_user": "ask",
    "get_local_time": "think",
}


def animation_hint(
    activity: str, tools: list[str], questions: int, warnings: int
) -> dict[str, str]:
    """因为同一执行状态可以包含不同工具动作，需要用有限映射细化动作并保留人工与异常表情。"""
    # 1、工具名只用于白名单映射，不读取工具正文、参数或模型自然语言。
    gesture = {
        "thinking": "think",
        "executing": "work",
        "delegating": "talk",
        "question": "ask",
        "reporting": "report",
        "warning": "alert",
        "receiving": "listen",
    }.get(activity, "idle")
    if activity == "executing" and tools:
        gesture = OPERATIONS.get(tools[-1], "work")
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
    if payload.get("presentation_external"):
        return None
    expression, duration = "focused", 320
    if kind == "tool.started":
        action = OPERATIONS.get(payload.get("name", ""), "work")
    elif kind == "human.requested":
        action, expression, duration = "ask", "curious", 900
    elif kind in {"tool.failed", "run.failed", "run.interrupted", "task.failed"}:
        action, expression, duration = "alert", "concerned", 900
    elif kind == "run.completed":
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
