"""官方 Runnable v2 事件的受控 JSON 序列化，不产生桌面动作。"""

from collections.abc import Callable
from typing import Any

from langchain_core.messages import BaseMessage


def public_value(value: Any) -> Any:
    """因为 SDK 事件包含消息对象和异常，需要只序列化已知类型而不泄漏对象内部属性。"""
    # 1、消息使用官方公开结构；不对客户端、运行时对象调用 repr 或 vars。
    if isinstance(value, BaseMessage):
        return value.model_dump(
            mode="json",
            include={
                "type",
                "content",
                "name",
                "id",
                "tool_calls",
                "invalid_tool_calls",
                "usage_metadata",
                "tool_call_id",
                "status",
            },
        )
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, BaseException):
        return {
            "error_type": type(value).__name__,
            "message": "Execution interrupted"
            if type(value).__name__ == "GraphInterrupt"
            else "Execution error",
        }
    if isinstance(value, dict):
        return {
            str(key): public_value(item)
            for key, item in value.items()
            if isinstance(key, str | int)
        }
    if isinstance(value, list | tuple):
        return [public_value(item) for item in value]
    return {"unserialized_type": type(value).__name__}


def native_event(event: dict[str, Any], redact: Callable[[Any], Any]) -> dict[str, Any] | None:
    """因为官方轨迹需要保留调用树，需要记录原生事件字段并白名单过滤框架元数据。"""
    # 1、逐 token 输出不重复落盘；模型完整消息和图、工具生命周期保留。
    if event.get("event", "").endswith("_stream"):
        return None
    if event.get("event", "").startswith("on_chat_model_") and event.get("name") != "RoomCrewModel":
        return None
    metadata = event.get("metadata", {})
    allowed_metadata = {
        "langgraph_node",
        "langgraph_step",
        "langgraph_checkpoint_ns",
        "roomcrew_tool_kind",
        "roomcrew_tool_call_id",
    }
    value = {
        "event": event["event"],
        "name": event["name"],
        "run_id": event["run_id"],
        "parent_ids": list(event.get("parent_ids", [])),
        "tags": list(event.get("tags", [])),
        "metadata": {
            key: public_value(item) for key, item in metadata.items() if key in allowed_metadata
        },
        "data": public_value(event.get("data", {})),
    }
    # 2、图节点的输入输出重复包含完整状态，只保留其生命周期头；模型和工具保留真实载荷。
    if event["event"].startswith("on_chain_"):
        value["data"] = {}
    return dict(redact(value))
