"""SDK 公开事件到产品轨迹的转换，独立于 SQLite 和桌面界面。"""

import json
from collections.abc import Callable
from typing import Any

from langgraph.errors import GraphInterrupt

from roomcrew.agent_loop.messages import message_text
from roomcrew.agent_loop.native_events import public_value
from roomcrew.contracts.agents import ActorRef
from roomcrew.tracing.events import TraceEvent


class EventAdapter:
    def __init__(
        self,
        redact: Callable[[Any], Any],
        main: ActorRef | None = None,
        workers: dict[str, ActorRef] | None = None,
    ) -> None:
        """因为每次 Run 的子任务作用域独立，需要建立本轮事件转换器并只接收脱敏能力。"""
        # 1、不接收原始模型配置或 Key，不访问产品数据库。
        self._redact = redact
        self._main = main or ActorRef()
        self._workers = workers or {}
        self._scopes: dict[str, tuple[ActorRef, str]] = {}
        self._tool_actors: dict[str, tuple[ActorRef, str]] = {}
        self._external_scopes: set[str] = set()
        self._delegations: dict[str, dict[str, Any]] = {}

    def project(self, event: dict[str, Any]) -> list[TraceEvent]:
        """因为主子 Agent 的事件需按真实调用链归并，需要投影公开字段后交给应用层持久化。"""
        # 1、查找最内层真实 task 作用域，不根据模型自然语言猜测角色身份。
        identity, scope = self._main, "main"
        external = False
        for parent in event.get("parent_ids", []):
            if parent in self._scopes:
                identity, scope = self._scopes[parent]
                external = parent in self._external_scopes
        actor = identity.name
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
                target = self._workers.get(employee, identity)
                configured = employee != "general-purpose" and employee in self._workers
                delegation = {
                    "from_member_id": identity.member_id,
                    "delegation_kind": "configured" if configured else "external",
                    "target_member_id": target.member_id if configured else None,
                }
                self._delegations[event["run_id"]] = delegation
                if not configured:
                    self._external_scopes.add(event["run_id"])
                self._scopes[event["run_id"]] = (target, event["run_id"])
                projected.append(
                    TraceEvent(
                        "task.assigned",
                        target.name,
                        event["run_id"],
                        delegation,
                        target.agent_id,
                        target.member_id,
                    )
                )
            product_kind = "tool.started"
            tool_kind = event.get("metadata", {}).get("roomcrew_tool_kind", "tool")
            if (
                name == "read_file"
                and isinstance(inputs, dict)
                and str(inputs.get("file_path", "")).startswith("/skills/")
            ):
                tool_kind = "skill"
            payload = {
                "name": name,
                "call_id": event["run_id"],
                "sdk_run_id": event["run_id"],
                "input": inputs,
                "tool_kind": tool_kind,
                "tool_call_id": event.get("metadata", {}).get("roomcrew_tool_call_id"),
            }
        elif kind == "on_tool_end":
            output = data.get("output", "")
            product_kind = "tool.completed"
            payload = {
                "name": name,
                "call_id": event["run_id"],
                "output": message_text(output),
                "status": getattr(output, "status", "success"),
                "tool_call_id": getattr(output, "tool_call_id", None),
                "sdk_run_id": event["run_id"],
            }
            if name == "task" and event["run_id"] in self._scopes:
                target, child_scope = self._scopes[event["run_id"]]
                projected.append(
                    TraceEvent(
                        "task.completed",
                        target.name,
                        child_scope,
                        {
                            "status": getattr(output, "status", "success"),
                            **self._delegations.get(child_scope, {}),
                        },
                        target.agent_id,
                        target.member_id,
                    )
                )
        elif kind == "on_tool_error":
            if isinstance(data.get("error"), GraphInterrupt):
                return []
            if name == "task" and event["run_id"] in self._scopes:
                target, child_scope = self._scopes[event["run_id"]]
                projected.append(
                    TraceEvent(
                        "task.failed",
                        target.name,
                        child_scope,
                        {"status": "error", **self._delegations.get(child_scope, {})},
                        target.agent_id,
                        target.member_id,
                    )
                )
            product_kind = "tool.failed"
            payload = {"name": name, "call_id": event["run_id"], "message": "工具执行失败"}
        elif kind == "on_chat_model_start" and name == "RoomCrewModel":
            product_kind = "model.started"
        elif kind == "on_chat_model_end" and name == "RoomCrewModel":
            message = data.get("output")
            for call in getattr(message, "tool_calls", []):
                self._tool_actors[call["id"]] = (identity, scope)
            product_kind = "model.completed"
            payload = {"usage": getattr(message, "usage_metadata", None),
                       "message": public_value(message)}
            text = message_text(message)
            if text:
                projected.append(
                    TraceEvent("assistant.message", actor, scope, {"text": self._redact(text)})
                )
        # 3、所有工具回显统一脱敏；返回值是普通产品数据，存储由外层决定。
        if product_kind:
            safe = self._redact(json.loads(json.dumps(payload, ensure_ascii=False, default=str)))
            projected.append(TraceEvent(product_kind, actor, scope, safe))
        # 4、通用外援仍归属发起人的轨迹，但其内部执行不驱动另一个场景人物。
        if external:
            projected = [
                TraceEvent(
                    item.kind,
                    "通用子任务",
                    item.scope,
                    {**item.payload, "external_worker": True},
                    item.agent_id,
                    item.member_id,
                )
                for item in projected
            ]
        return [
            item
            if item.member_id
            else TraceEvent(
                item.kind,
                item.actor,
                item.scope,
                item.payload,
                identity.agent_id,
                identity.member_id,
            )
            for item in projected
        ]

    def human_request(self, identifier: str, value: dict[str, Any]) -> TraceEvent:
        """因为只有已提交的中断才表示真实等待，需要把公开 interrupt 映射到发问成员。"""
        # 1、根据模型实际工具调用 ID 关联身份，正文问号不会触发这个入口。
        actor, scope = self._tool_actors.get(value.get("tool_call_id", ""), (self._main, "main"))
        payload = {
            "request_id": identifier,
            "request_kind": "question",
            "question": value.get("question", "需要你的答复"),
            "choices": value.get("choices", []),
            "tool_call_id": value.get("tool_call_id"),
            "interaction_type": value.get("interaction_type", "question"),
            "allow_other": value.get("allow_other", True),
        }
        return TraceEvent(
            "human.requested",
            actor.name,
            scope,
            self._redact(payload),
            actor.agent_id,
            actor.member_id,
        )
