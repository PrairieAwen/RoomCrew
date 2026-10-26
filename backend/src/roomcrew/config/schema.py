"""模型配置字段与用户可见投影。"""

from dataclasses import dataclass, field
from typing import Any


class ConfigurationError(ValueError):
    """可以直接展示的配置错误，不携带输入中的密钥。"""


@dataclass(frozen=True)
class ModelProfile:
    reference: str
    label: str
    base_url: str
    model: str
    api_key: str = field(repr=False)
    timeout: int = 90
    context_window: int = 32768
    proxy: str = ""

    def public(self) -> dict[str, Any]:
        """因为用户需要修改非秘密参数，需要返回配置概况，同时永远不返回已保存的 Key。"""
        # 1、只返回人工配置界面需要的字段，不能用完整对象序列化作为公共响应。
        return {
            "configured": True,
            "reference": self.reference,
            "label": self.label,
            "base_url": self.base_url,
            "model": self.model,
            "timeout": self.timeout,
            "context_window": self.context_window,
            "proxy": self.proxy,
            "has_key": bool(self.api_key),
            "protocol": "openai-compatible",
        }
