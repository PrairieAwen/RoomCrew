"""模型私有代理，统一预算、标准输出和错误边界。"""

from collections.abc import Sequence
from typing import Any, cast

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from pydantic import PrivateAttr

from roomcrew.middleware.limits import ModelCallBudget
from roomcrew.models.errors import sanitized_error
from roomcrew.security.redaction import redact_value


class PrivateChatModel(BaseChatModel):
    model_name: str = "roomcrew:private"
    _delegate: Runnable[Any, Any] = PrivateAttr()
    _key: str = PrivateAttr()
    _budget: ModelCallBudget = PrivateAttr()
    _clients: tuple[httpx.Client, httpx.AsyncClient] | None = PrivateAttr(default=None)

    def __init__(
        self,
        delegate: Runnable[Any, Any],
        key: str,
        context_window: int = 32768,
        budget: ModelCallBudget | None = None,
    ) -> None:
        """因为框架会序列化模型标识和回调，需要用不含配置的代理封装真实 SDK 客户端。"""
        # 1、公开字段只提供通用名称和能力信息，真实客户端与密钥保持为私有属性。
        super().__init__(
            name="RoomCrewModel", profile={"max_input_tokens": context_window, "tool_calling": True}
        )
        self._delegate = delegate
        self._key = key
        self._budget = budget if budget is not None else ModelCallBudget()

    @property
    def _llm_type(self) -> str:
        """因为框架需要模型类型标识，需要返回固定产品名称而不是底层模型或端点。"""
        # 1、固定标识不透露用户配置。
        return "roomcrew-private-model"

    def bind_tools(
        self, tools: Sequence[Any], *, tool_choice: Any = None, **kwargs: Any
    ) -> "PrivateChatModel":
        """因为 Deep Agents 会绑定不同工具集合，需要保留代理边界并转交真实客户端绑定。"""
        # 1、只把工具协议交给私有客户端，返回新的代理，避免修改其他 Agent 的绑定。
        bound = cast(Any, self._delegate).bind_tools(tools, tool_choice=tool_choice, **kwargs)
        return PrivateChatModel(
            bound, self._key, (self.profile or {}).get("max_input_tokens", 32768), self._budget
        )

    def _clean(self, message: AIMessage) -> ChatResult:
        """因为厂商响应元数据可能含模型名和端点，需要只保留任务内容、工具请求及用量。"""
        # 1、重建消息，去掉厂商响应元数据和附加认证字段；保留标准工具调用语义。
        cleaned = AIMessage(
            content=redact_value(message.content, self._key),
            tool_calls=redact_value(message.tool_calls, self._key),
            invalid_tool_calls=redact_value(message.invalid_tool_calls, self._key),
            usage_metadata=message.usage_metadata,
            id=redact_value(message.id, self._key),
        )
        # 2、只返回标准结果；厂商原始响应不进入框架状态。
        return ChatResult(generations=[ChatGeneration(message=cleaned)])

    async def close(self) -> None:
        """因为每轮创建独立模型连接，需要在任务结束后关闭 HTTP 连接池，避免累积句柄。"""
        # 1、只有工厂返回的根代理拥有连接，工具绑定副本不重复关闭共享客户端。
        clients, self._clients = self._clients, None
        if clients:
            try:
                clients[0].close()
            finally:
                # 2、同步关闭失败也释放异步连接；先移除所有权，重复关闭不再次操作同一连接池。
                await clients[1].aclose()

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        """因为摘要等框架扩展可能同步调用模型，需要提供同样隐藏配置的同步适配。"""
        # 1、内层调用不继承框架回调，外层代理统一产生产品可观察事件。
        self._budget.consume()
        try:
            message = self._delegate.invoke(messages, config={"callbacks": []}, stop=stop, **kwargs)
            return self._clean(message)
        except Exception as error:
            raise sanitized_error(error) from None

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        """因为会话和子 Agent 并发运行，需要通过真实 SDK 异步调用并统一隐藏错误细节。"""
        # 1、保留 SDK 的真实工具调用，不生成本地替代答案；异常只返回稳定分类。
        self._budget.consume()
        try:
            message = await self._delegate.ainvoke(
                messages, config={"callbacks": []}, stop=stop, **kwargs
            )
            return self._clean(message)
        except Exception as error:
            raise sanitized_error(error) from None

    def redact(self, value: Any) -> Any:
        """因为轨迹适配器不能接收原始 Key，需要提供只脱敏、不返回凭据的过滤方法。"""
        # 1、调用者只能提交待过滤数据，不能从该接口取得原始秘密。
        return redact_value(value, self._key)
