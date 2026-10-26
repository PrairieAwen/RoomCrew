"""持久轨迹合同，不依赖 LangChain 或 Deep Agents 私有字段。"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TraceEvent:
    kind: str
    actor: str = "助手"
    scope: str = "main"
    payload: dict[str, Any] = field(default_factory=dict)
