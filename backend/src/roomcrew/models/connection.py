"""用户模型连接探测，不属于 Agent 工具，也不写入任务上下文。"""

import asyncio
import json
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


async def test_presentation_connection(profile: ModelProfile) -> dict[str, Any]:
    """因为轻量旁白模型无需工具能力，需要独立验证有限 JSON 文本协议而不强制函数调用。"""
    # 1、只使用表现配置，并采用短超时和小输出上限。
    model = create_model(profile)
    try:
        async with asyncio.timeout(10):
            reply = await model.ainvoke(
                '只输出 JSON：{"action_id":"idle","summary":"准备就绪"}', max_tokens=100
            )
        content = reply.content
        value = json.loads(content) if isinstance(content, str) and len(content) <= 1000 else {}
        if (
            not isinstance(value, dict)
            or value.get("action_id") != "idle"
            or not isinstance(value.get("summary"), str)
        ):
            raise ValueError("旁白模型未返回有限 JSON；保持规则模式即可使用全部执行能力")
    except TimeoutError:
        raise ValueError("旁白探测超时；可以保持规则模式") from None
    except (TypeError, json.JSONDecodeError):
        raise ValueError("旁白模型返回格式不兼容；请使用支持 JSON 输出的模型") from None
    finally:
        await model.close()
    return {"message": "连接成功，已收到旁白 JSON；不会替代执行模型或事实状态。"}
