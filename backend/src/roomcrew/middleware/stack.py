"""集中组装当前 Run 的中间件，调用者不拼装框架私有栈。"""

from typing import Any

from deepagents.backends.protocol import BackendProtocol
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models import BaseChatModel

from roomcrew.context_compression.deepagents_adapter import build_compression
from roomcrew.context_compression.policy import CompressionPolicy


def build_middleware(
    model: BaseChatModel, backend: BackendProtocol, compression: CompressionPolicy
) -> list[AgentMiddleware[Any, Any, Any]]:
    """因为主 Agent 与子 Agent 需要相同策略但独立实例，需要每次构图时组装新的中间件。"""
    # 1、目前只替换摘要槽位，SDK 的文件、工具修复和规划机制保持由其自身管理。
    return [build_compression(model, backend, compression)]
