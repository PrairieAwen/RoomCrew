"""人物身份与可执行 Agent 定义分离，不携带真实模型连接参数。"""

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ActorRef:
    member_id: str = "assistant"
    agent_id: str = "agent_assistant"
    name: str = "助手"


@dataclass(frozen=True)
class AgentSpec:
    actor: ActorRef
    tool_name: str
    description: str
    prompt: str
    revision: int = 1

    def snapshot(self) -> dict[str, Any]:
        """因为在途任务不能被人物编辑改变，需要保存不含凭据的定义快照。"""
        # 1、只包含身份、任务说明和提示配置，不包含客户端、路径或真实模型参数。
        return asdict(self)

    @classmethod
    def restore(cls, value: dict[str, Any]) -> "AgentSpec":
        """因为人工等待后需要恢复原定义，需要从产品快照重建普通数据对象。"""
        # 1、不从快照导入 Python 类或执行代码。
        return cls(
            ActorRef(**value["actor"]),
            value["tool_name"],
            value["description"],
            value["prompt"],
            int(value["revision"]),
        )
