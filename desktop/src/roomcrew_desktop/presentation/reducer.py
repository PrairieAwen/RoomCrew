"""确定性地把日志事实归约为人物表现，不根据自然语言猜测任务成败。"""

from typing import Any

from roomcrew_desktop.presentation.animation import animation_hint
from roomcrew_desktop.presentation.collaboration import reduce_delegation

LABELS = {
    "idle": "待命",
    "thinking": "思考中",
    "executing": "执行工具",
    "delegating": "协调任务",
    "question": "需要你的答复",
    "waiting": "等待协作",
    "reporting": "本轮结束，待核对",
    "warning": "需要关注",
    "stopped": "已停止",
    "receiving": "接收任务",
}
ACTIONS = {
    "idle": "idle",
    "thinking": "think",
    "executing": "work",
    "delegating": "talk",
    "question": "ask",
    "waiting": "idle",
    "reporting": "report",
    "warning": "alert",
    "stopped": "idle",
    "receiving": "listen",
}


def reduce_event(actors: dict[str, Any], event: dict[str, Any]) -> None:
    """因为人物可能有多个执行上下文，需要按 Run 和 scope 聚合而非覆盖忙碌状态。"""
    # 1、重复事件不改变状态；历史无身份事件仅回退到兼容的默认人物。
    if event["kind"] == "user.message":
        return
    member_id = event.get("member_id") or "assistant"
    state = actors.setdefault(
        member_id,
        {
            "member_id": member_id,
            "contexts": {},
            "warnings": [],
            "last_source_seq": 0,
            "terminal": "idle",
            "created_at": event["created_at"],
        },
    )
    if event["seq"] <= state["last_source_seq"]:
        return
    state["conversation_id"] = event.get("conversation_id")
    reduce_delegation(actors, event)
    run_id, kind, payload = event["run_id"], event["kind"], event["payload"]
    # 2、外援内部轨迹保留在会话中，模型/工具片段不覆盖发起人的电话表现；真实提问仍显示。
    if (payload.get("external_worker") or payload.get("presentation_external")) and kind in {
        "model.started",
        "model.completed",
        "tool.started",
        "tool.completed",
        "tool.failed",
        "assistant.message",
    }:
        return
    if kind in {"run.started", "task.assigned"}:
        state["assignment_seq"] = event["seq"]
        target = payload.get("from_member_id", "assistant")
        state["interaction_target"] = "assistant" if target == "boss" else target
        if kind == "run.started" or not state["contexts"]:
            state["warnings"] = []
    scope = event.get("scope", "main")
    key = run_id + ":" + scope
    # 3、终态只清除本 Run 的上下文，不能让其他并行工作显示空闲。
    if kind in {"run.completed", "run.failed", "run.cancelled", "run.interrupted"}:
        if scope != "main":
            state["last_source_seq"] = event["seq"]
            return
        for item in actors.values():
            removed = [key for key, value in item["contexts"].items() if value["run_id"] == run_id]
            for context_key in removed:
                del item["contexts"][context_key]
            if removed or item is state:
                item["terminal"] = (
                    "reporting"
                    if kind == "run.completed"
                    else ("warning" if kind in {"run.failed", "run.interrupted"} else "stopped")
                )
                item["last_source_seq"] = event["seq"]
                item["created_at"] = event["created_at"]
                if kind in {"run.failed", "run.interrupted"}:
                    item["warnings"] = ["本轮执行异常，请查看轨迹"]
    elif kind == "run.waiting_user":
        for item in actors.values():
            for context in item["contexts"].values():
                if context["run_id"] == run_id:
                    context["waiting_dependency"] = True
                    item["last_source_seq"] = event["seq"]
    elif kind == "run.resumed":
        for item in actors.values():
            for context in item["contexts"].values():
                if context["run_id"] == run_id:
                    context["waiting_dependency"] = False
                    item["last_source_seq"] = event["seq"]
    elif kind in {
        "task.assigned",
        "model.started",
        "tool.started",
        "tool.completed",
        "tool.failed",
        "human.requested",
        "human.responded",
        "task.completed",
        "task.failed",
        "run.started",
        "model.completed",
        "assistant.message",
    }:
        if kind == "task.assigned" and payload.get("delegation_kind") == "external":
            state["last_source_seq"] = event["seq"]
            return
        context = state["contexts"].setdefault(
            key,
            {
                "run_id": run_id,
                "scope": scope,
                "phase": "thinking",
                "tools": {},
                "tool_kinds": {},
                "questions": [],
                "waiting_dependency": False,
            },
        )
        if kind == "task.assigned":
            context["phase"] = "receiving"
        elif kind == "model.started":
            context["phase"] = "thinking"
        elif kind == "tool.started":
            context["tools"][payload["call_id"]] = payload.get("name", "tool")
            context.setdefault("tool_kinds", {})[payload["call_id"]] = payload.get(
                "tool_kind", "tool"
            )
        elif kind in {"tool.completed", "tool.failed"}:
            context["tools"].pop(payload.get("call_id"), None)
            context.setdefault("tool_kinds", {}).pop(payload.get("call_id"), None)
            if kind == "tool.failed" or payload.get("status") == "error":
                state["warnings"] = ["工具返回错误，执行器可能仍在处理"]
        elif kind == "human.requested":
            context["questions"] = list(
                dict.fromkeys([*context["questions"], payload["request_id"]])
            )
        elif kind == "human.responded":
            context["questions"] = [
                identifier
                for identifier in context["questions"]
                if identifier != payload["request_id"]
            ]
        elif kind in {"task.completed", "task.failed"}:
            # 子任务结束不是整轮结束；主 scope 必须等正式 Run 终态才能释放。
            if scope == "main":
                context["phase"] = "thinking"
            else:
                state["contexts"].pop(key, None)
            failed = kind == "task.failed" or payload.get("status") == "error"
            state["terminal"] = "warning" if failed else "idle"
            if failed:
                state["warnings"] = ["子任务返回错误，请查看轨迹"]
    state["last_source_seq"] = event["seq"]
    state["created_at"] = event["created_at"]


def actor_view(state: dict[str, Any]) -> dict[str, Any]:
    """因为场景不应该收到消息正文或工具参数，需要只输出有限的语义状态和素材动作引用。"""
    # 1、实际运行优先于生活动作，同时保留其他上下文的问题与提醒徽记。
    contexts = list(state["contexts"].values())
    questions = sum(len(context["questions"]) for context in contexts)
    running = [
        context
        for context in contexts
        if not context["questions"] and not context["waiting_dependency"]
    ]
    tool_names = [name for context in running for name in context["tools"].values()]
    tool_kinds = [name for context in running for name in context.get("tool_kinds", {}).values()]
    if running:
        activity = (
            "executing"
            if any(name != "task" for name in tool_names)
            else ("delegating" if tool_names else running[-1]["phase"])
        )
    elif questions:
        activity = "question"
    elif contexts:
        activity = "waiting"
    else:
        activity = state["terminal"]
    # 2、协议给语义和注册动作，不下发任意帧、脚本、路径或权限指令。
    return {
        "protocol_version": 1,
        "member_id": state["member_id"],
        "conversation_id": state.get("conversation_id"),
        "source_seq": state["last_source_seq"],
        "activity": activity,
        "action_id": ACTIONS.get(activity, "idle"),
        "summary": LABELS.get(activity, "状态更新"),
        "question_count": questions,
        "warning_count": len(state["warnings"]),
        "active_contexts": len(contexts),
        "idle_eligible": not contexts
        and not state["warnings"]
        and activity in {"idle", "reporting", "stopped"},
        "active_runs": sorted({context["run_id"] for context in contexts}),
        "created_at": state["created_at"],
        "origin": "rules",
        "requires_input": questions > 0,
        "assignment_seq": state.get("assignment_seq", 0),
        "interaction_target": state.get("interaction_target"),
        "external_calls": sum(
            link["kind"] == "external" for link in state.get("delegations", {}).values()
        ),
        "delegation_targets": [
            link["target"] for link in state.get("delegations", {}).values() if link.get("target")
        ],
        "tool_kind": tool_kinds[-1] if tool_kinds else None,
        "animation": animation_hint(
            activity, tool_names, questions, len(state["warnings"]), tool_kinds
        ),
    }
