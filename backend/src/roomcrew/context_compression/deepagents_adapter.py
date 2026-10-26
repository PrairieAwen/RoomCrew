"""通过公开工厂替换 Deep Agents 的同名摘要槽位。"""

from typing import Any

from deepagents.backends.protocol import BackendProtocol
from deepagents.middleware.summarization import create_summarization_middleware
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models import BaseChatModel

from roomcrew.context_compression.policy import CompressionPolicy


def build_compression(
    model: BaseChatModel, backend: BackendProtocol, policy: CompressionPolicy
) -> AgentMiddleware[Any, Any, Any]:
    """因为压缩需要独立调整且不能叠加两次，需要用 SDK 公共工厂建立一个同名替换实例。"""
    # 1、触发/保留阈值继续由 SDK 根据模型能力确定；输入裁剪不是触发阈值或输出长度。
    options: dict[str, Any] = {"trim_tokens_to_summarize": policy.trim_tokens_to_summarize}
    if policy.summary_prompt is not None:
        options["summary_prompt"] = policy.summary_prompt
    # 2、返回 SDK 的默认槽位名称，create_deep_agent 会按名称替换而不是重复执行。
    return create_summarization_middleware(model, backend, **options)
