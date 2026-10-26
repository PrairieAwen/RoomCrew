"""用户模型连接探测，不属于 Agent 工具，也不写入任务上下文。"""

from typing import Any

from langchain_core.exceptions import ContextOverflowError

from roomcrew.config.schema import ModelProfile
from roomcrew.contracts.errors import ExecutionError
from roomcrew.models.factory import create_model


async def test_model_connection(profile: ModelProfile) -> dict[str, Any]:
    """因为普通聊天响应不代表能运行工具循环，需要用真实 SDK 验证标准函数调用协议。"""
    # 1、只在可信配置入口构建模型；探测消息不包含 Key 或端点。
    model = create_model(profile)
    probe = {
        "type": "function",
        "function": {
            "name": "roomcrew_connection_probe",
            "description": "Return the supplied probe value.",
            "parameters": {
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
                "additionalProperties": False,
            },
        },
    }
    # 2、强制真实工具协议响应，关闭连接发生在成功或失败两条路径上。
    try:
        response = await model.bind_tools(
            [probe],
            tool_choice={"type": "function", "function": {"name": "roomcrew_connection_probe"}},
        ).ainvoke("Call roomcrew_connection_probe with value 'ok'.")
    except ContextOverflowError:
        raise ExecutionError("CONTEXT_LIMIT") from None
    finally:
        await model.close()
    if not any(call["name"] == "roomcrew_connection_probe" for call in response.tool_calls):
        raise ValueError("已收到模型响应，但未得到标准工具调用；请检查模型的工具调用支持")
    return {"message": "连接成功，已收到标准工具调用响应。实际任务仍需会话验证。"}
