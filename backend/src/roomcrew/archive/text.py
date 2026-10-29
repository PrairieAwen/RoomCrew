"""完整公开消息投影与有来源的分块，不把摘要替代为原始证据。"""

import json
from collections.abc import Iterable
from typing import Any


def visible_messages(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """因为压缩后的 checkpoint 可能不含早期消息，需要从不删减的产品事件重建公开历史。"""
    # 1、保留用户、AI、工具与人工答复，角色身份和事件序号来自原始记录。
    events = list(events)
    structured = {
        event["run_id"]
        for event in events
        if event["kind"] == "model.completed" and event["payload"].get("message")
    }
    messages: list[dict[str, Any]] = []
    for event in events:
        kind, payload = event["kind"], event["payload"]
        if kind == "assistant.message" and event["run_id"] in structured:
            continue
        if kind == "model.completed" and isinstance(payload.get("message"), dict):
            kind = "assistant.message"
            payload = {**payload, "text": payload["message"].get("content", "")}
        roles = {
            "user.message": "user",
            "assistant.message": "assistant",
            "tool.started": "tool_call",
            "tool.completed": "tool",
            "tool.failed": "tool_error",
            "human.requested": "human_request",
            "human.responded": "user_answer",
        }
        if kind not in roles:
            continue
        text = payload.get("text", payload.get("output", payload.get("answer")))
        if text is None:
            text = json.dumps(payload, ensure_ascii=False)
        messages.append(
            {
                "position": len(messages),
                "event_seq": event["seq"],
                "role": roles[kind],
                "actor": event["actor"],
                "member_id": event.get("member_id"),
                "agent_id": event.get("agent_id"),
                "at": event["created_at"],
                "text": text if isinstance(text, str) else json.dumps(text, ensure_ascii=False),
                "payload": payload,
            }
        )
    return messages


def fragments(text: str, size: int = 400, overlap: int = 40) -> list[str]:
    """因为向量模型有输入窗口，需要完整分片而不是截断长消息丢失后面的事实。"""
    # 1、相邻分片保留少量重叠，位置仍由外层消息索引定位，不修改原文。
    if size <= overlap or overlap < 0:
        raise ValueError("档案分片长度必须大于重叠范围")
    return [text[index : index + size] for index in range(0, len(text), size - overlap)]


def summary_parts(messages: list[dict[str, Any]], size: int = 12000) -> list[dict[str, Any]]:
    """因为完整对话可能超过摘要模型窗口，需要逐段覆盖所有公开消息并保存准确来源位置。"""
    # 1、单条大工具结果也分片；每段保留消息位置、时间和执行者，不猜测未记录的信息。
    result: list[dict[str, Any]] = []
    current: list[str] = []
    positions: set[int] = set()
    length = 0
    for message in messages:
        for piece in fragments(message["text"], max(200, size // 2), 0):
            line = f"[{message['position']}][{message['at']}][{message['actor']}] {piece}"
            if current and length + len(line) > size:
                result.append({"text": "\n".join(current), "positions": sorted(positions)})
                current, positions, length = [], set(), 0
            current.append(line)
            positions.add(message["position"])
            length += len(line)
    if current:
        result.append({"text": "\n".join(current), "positions": sorted(positions)})
    return result
