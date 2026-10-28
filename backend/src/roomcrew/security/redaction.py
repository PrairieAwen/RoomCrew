"""递归清除秘密回显，不执行或解释外部内容。"""

from typing import Any


def redact_value(value: Any, key: str) -> Any:
    """因为密钥可能被异常服务放进工具参数或内容块，需要递归清除而不破坏标准消息结构。"""
    # 1、只替换实际密钥文本；保留列表、字典和数值的原有语义。
    if isinstance(value, str):
        return value.replace(key, "[已隐藏凭据]")
    if isinstance(value, list):
        return [redact_value(item, key) for item in value]
    if isinstance(value, dict):
        return {
            name.replace(key, "[已隐藏凭据]") if isinstance(name, str) else name: redact_value(
                item, key
            )
            for name, item in value.items()
        }
    return value
