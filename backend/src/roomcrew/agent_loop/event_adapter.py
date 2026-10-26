"""SDK 公开事件到产品轨迹的转换，独立于 SQLite 和桌面界面。"""

import json
from collections.abc import Callable
from typing import Any

from roomcrew.agent_loop.messages import message_text
from roomcrew.tracing.events import TraceEvent


class EventAdapter:
    def __init__(self, redact: Callable[[Any], Any]) -> None:
        """因为每次 Run 的子任务作用域独立，需要建立本轮事件转换器并只接收脱敏能力。"""
        # 1、不接收原始模型配置或 Key，不访问产品数据库。
        self._redact = redact
        self._scopes: dict[str, tuple[str, str]] = {}

    def project(self, event: dict[str, Any]) -> list[TraceEvent]:
        """因为主子 Agent 的事件需按真实调用链归并，需要投影公开字段后交给应用层持久化。"""
        # 1、查找最内层真实 task 作用域，不根据模型自然语言猜测角色身份。
        actor, scope = "助手", "main"
        for parent in event.get("parent_ids", []):
            if parent in self._scopes:
                actor, scope = self._scopes[parent]
        kind, name, data = event["event"], event["name"], event.get("data", {})
        projected: list[TraceEvent] = []
        payload: dict[str, Any] = {}
        product_kind = ""
        # 2、仅转换可观察模型/工具事件，不保存原始请求、隐藏思考或框架私有状态。
        if kind == "on_tool_start":
            inputs = data.get("input", {})
            if name == "task":
                employee = (
                    inputs.get("subagent_type", "general-purpose")
                    if isinstance(inputs, dict)
                    else "general-purpose"
                )
                self._scopes[event["run_id"]] = (f"员工 · {employee}", event["run_id"])
            product_kind = "tool.started"
            payload = {"name": name, "call_id": event["run_id"], "input": inputs}
        elif kind == "on_tool_end":
            output = data.get("output", "")
            product_kind = "tool.completed"
            payload = {
                "name": name,
                "call_id": event["run_id"],
                "output": message_text(output),
                "status": getattr(output, "status", "success"),
            }
        elif kind == "on_tool_error":
            product_kind = "tool.failed"
            payload = {"name": name, "call_id": event["run_id"], "message": "工具执行失败"}
        elif kind == "on_chat_model_start" and name == "RoomCrewModel":
            product_kind = "model.started"
        elif kind == "on_chat_model_end" and name == "RoomCrewModel":
            message = data.get("output")
            product_kind = "model.completed"
            payload = {"usage": getattr(message, "usage_metadata", None)}
            text = message_text(message)
            if text:
                projected.append(
                    TraceEvent("assistant.message", actor, scope, {"text": self._redact(text)})
                )
        # 3、所有工具回显统一脱敏；返回值是普通产品数据，存储由外层决定。
        if product_kind:
            safe = self._redact(json.loads(json.dumps(payload, ensure_ascii=False, default=str)))
            projected.append(TraceEvent(product_kind, actor, scope, safe))
        return projected
