"""框架消息到可见文本的投影。"""

from typing import Any

from langchain_core.messages import BaseMessage


def message_text(message: BaseMessage | str | Any) -> str:
    """因为模型可能返回多种内容块，需要统一提取可展示正文并排除隐藏推理和厂商私有字段。"""
    # 1、只投影用户可见文本，不序列化整个框架消息对象。
    content = message.content if isinstance(message, BaseMessage) else message
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""
