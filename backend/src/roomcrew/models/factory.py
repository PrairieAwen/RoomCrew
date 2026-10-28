"""可信模型工厂：真实 SDK 参数只在此处读取使用。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from roomcrew.config.schema import ModelProfile
from roomcrew.middleware.limits import ModelCallBudget
from roomcrew.models.private_chat import PrivateChatModel


def create_model(profile: ModelProfile, budget: ModelCallBudget | None = None) -> PrivateChatModel:
    """因为 Agent 不应读取本地配置，需要由可信工厂显式注入参数并关闭环境凭据兜底。"""
    # 1、首版采用 Chat Completions，关闭 SDK 自动重试和隐式代理，明确单请求超时。
    sync_client = httpx.Client(
        trust_env=False, timeout=profile.timeout, proxy=profile.proxy or None
    )
    async_client = httpx.AsyncClient(
        trust_env=False, timeout=profile.timeout, proxy=profile.proxy or None
    )
    client = ChatOpenAI(
        model=profile.model,
        api_key=SecretStr(profile.api_key),
        base_url=profile.base_url,
        timeout=profile.timeout,
        max_retries=0,
        use_responses_api=False,
        disable_streaming=True,
        http_socket_options=(),
        http_client=sync_client,
        http_async_client=async_client,
    )
    # 2、只有本方法能看到完整配置；调用层只持有通用模型代理。
    model = PrivateChatModel(client, profile.api_key, profile.context_window, budget)
    model._clients = (sync_client, async_client)
    return model


@asynccontextmanager
async def model_session(
    profile: ModelProfile, budget: ModelCallBudget | None = None
) -> AsyncIterator[PrivateChatModel]:
    """因为探测与辅助调用都会临时创建模型，需要共用成功、异常和取消时的连接释放规则。

    仅可信应用层传入私有配置；调用方只获得通用代理，退出作用域后不能继续使用它。
    """
    # 1、仍经过同一模型工厂，不另设厂商入口、重试策略或环境密钥兜底。
    model = create_model(profile, budget)
    try:
        yield model
    finally:
        # 2、无论模型返回、格式校验失败还是协程取消，都结束本次连接生命周期。
        await model.close()
